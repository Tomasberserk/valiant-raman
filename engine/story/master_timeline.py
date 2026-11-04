"""Master Timeline & Continuous Audio (Stage 12B.4).

Transforms independent scene productions into a unified continuous master video:
1. Physical timeline computation with exact cumulative offsets.
2. Global subtitle consolidation (master.ass) with precision time shifts.
3. Continuous voice track stitching without artificial gaps.
4. Continuous BGM voice-priority mixing (-14 LUFS, TP <= -1.0 dBTP) with graceful voice-only fallback.
5. Clean video track concatenation (1080x1920 @ 30fps).
6. Master audiovisual multiplexing into master_story.mp4.
7. Boundary integrity and continuity validation across scene transitions.
"""

import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from engine.media.subtitles import generate_ass_subtitles
from engine.story.schema import (
    MasterTimeline,
    Scene,
    StoryArc,
    WordTimestamp,
)


class MasterTimelineAssembler:
    """Orchestrates Master Timeline calculation, audio mixing, and video concatenation."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def calculate_timeline(self, story: StoryArc) -> MasterTimeline:
        """Compute cumulative real physical offsets from scene actual_duration_sec."""
        if not story.scenes:
            raise ValueError("StoryArc contains no scenes to assemble.")

        scene_order: List[str] = []
        scene_durations: Dict[str, float] = {}
        scene_offsets: Dict[str, float] = {}

        running_offset = 0.0
        for scene in story.scenes:
            # Physical duration authority: actual_duration_sec preferred over estimated
            dur = float(scene.actual_duration_sec or scene.estimated_duration_sec or 0.0)
            dur = round(dur, 2)

            scene_order.append(scene.id)
            scene_offsets[scene.id] = round(running_offset, 2)
            scene_durations[scene.id] = dur
            running_offset += dur

        total_actual_duration = round(running_offset, 2)

        return MasterTimeline(
            story_id=story.id,
            target_duration_sec=story.target_duration_sec,
            total_actual_duration_sec=total_actual_duration,
            scene_order=scene_order,
            scene_offsets=scene_offsets,
            scene_durations=scene_durations,
            video_tracks=[{"scene_id": s_id, "duration": scene_durations[s_id], "offset": scene_offsets[s_id]} for s_id in scene_order],
            voice_tracks=[{"scene_id": s_id, "duration": scene_durations[s_id], "offset": scene_offsets[s_id]} for s_id in scene_order],
        )

    def merge_master_subtitles(
        self,
        story: StoryArc,
        timeline: MasterTimeline,
        output_path: Path,
    ) -> Path:
        """Consolidate word timestamps across all scenes with exact time shifts into master.ass."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shifted_timestamps: List[WordTimestamp] = []

        for scene in story.scenes:
            offset = timeline.scene_offsets.get(scene.id, 0.0)
            for t in scene.word_timings:
                shifted = WordTimestamp(
                    word=t.word,
                    start=round(t.start + offset, 3),
                    end=round(t.end + offset, 3),
                    confidence=t.confidence,
                )
                shifted_timestamps.append(shifted)

        # Generate single unified ASS subtitle track
        generate_ass_subtitles(
            timestamps=shifted_timestamps,
            output_path=output_path,
            font_name="Arial",
            font_size=56,
            style_preset="capcut_yellow",
            enable_kinetic_highlight=True,
            margin_v=480,
        )

        timeline.master_subtitles_path = output_path
        timeline.caption_track_path = output_path
        return output_path

    def stitch_continuous_voice(
        self,
        story: StoryArc,
        output_path: Path,
    ) -> Path:
        """Concatenate voice audio tracks across scenes without adding artificial gaps."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        voice_files: List[Path] = []
        for scene in story.scenes:
            if not scene.voice_audio_path or not Path(scene.voice_audio_path).exists():
                raise FileNotFoundError(f"Missing voice audio for scene '{scene.id}': {scene.voice_audio_path}")
            voice_files.append(Path(scene.voice_audio_path))

        # Build FFmpeg concat filter command
        cmd = [self.ffmpeg_bin]
        filter_inputs = ""
        for i, vf in enumerate(voice_files):
            cmd.extend(["-i", str(vf)])
            filter_inputs += f"[{i}:a]"

        filter_complex = f"{filter_inputs}concat=n={len(voice_files)}:v=0:a=1[outa]"
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outa]",
            "-c:a", "pcm_s16le",
            "-y",
            str(output_path),
        ])

        subprocess.run(cmd, capture_output=True, check=True)
        return output_path

    def mix_master_audio(
        self,
        voice_path: Path,
        bgm_path: Optional[Path],
        duration_sec: float,
        output_path: Path,
        bgm_volume: float = 0.12,
    ) -> Tuple[Path, bool]:
        """Mix voice track with optional continuous BGM (voice-priority mix) and EBU R128 loudness.

        If BGM is missing or corrupt, falls back cleanly to Voice-Only.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        bgm_applied = False

        if bgm_path is not None and Path(bgm_path).exists() and Path(bgm_path).stat().st_size > 0:
            try:
                fade_start = max(0.0, duration_sec - 2.0)
                cmd = [
                    self.ffmpeg_bin,
                    "-i", str(voice_path),
                    "-stream_loop", "-1",
                    "-i", str(bgm_path),
                    "-filter_complex", (
                        f"[1:a]volume={bgm_volume},afade=t=out:st={fade_start:.2f}:d=2.0[bgm];"
                        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[mixed];"
                        f"[mixed]loudnorm=I=-14:TP=-1.0:LRA=11[aout]"
                    ),
                    "-map", "[aout]",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-t", f"{duration_sec:.2f}",
                    "-y",
                    str(output_path),
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                bgm_applied = True
            except Exception:
                # Fallback to voice-only if BGM mixing fails
                bgm_applied = False

        if not bgm_applied:
            # Voice-Only Master Audio with EBU R128 normalization
            cmd = [
                self.ffmpeg_bin,
                "-i", str(voice_path),
                "-filter_complex", "[0:a]loudnorm=I=-14:TP=-1.0:LRA=11[aout]",
                "-map", "[aout]",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{duration_sec:.2f}",
                "-y",
                str(output_path),
            ]
            subprocess.run(cmd, capture_output=True, check=True)

        return output_path, bgm_applied

    def assemble_master_video_track(
        self,
        visual_scene_paths: List[Path],
        output_path: Path,
    ) -> Path:
        """Concatenate pure visual tracks with clean cuts at 1080x1920 @ 30fps."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not visual_scene_paths:
            raise ValueError("No visual scene paths provided for video track assembly.")

        cmd = [self.ffmpeg_bin]
        filter_inputs = ""
        for i, vp in enumerate(visual_scene_paths):
            if not vp.exists():
                raise FileNotFoundError(f"Visual track segment missing: {vp}")
            cmd.extend(["-i", str(vp)])
            filter_inputs += f"[{i}:v]"

        filter_complex = f"{filter_inputs}concat=n={len(visual_scene_paths)}:v=1:a=0[vcat]"
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[vcat]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-an",
            "-y",
            str(output_path),
        ])

        subprocess.run(cmd, capture_output=True, check=True)
        return output_path

    def assemble_master_story(
        self,
        story: StoryArc,
        scene_dir: Path,
        output_dir: Path,
        bgm_path: Optional[Path] = None,
    ) -> MasterTimeline:
        """Assemble full story into master_story.mp4 with unified audio and subtitles."""
        output_dir.mkdir(parents=True, exist_ok=True)
        timeline = self.calculate_timeline(story)

        # 1. Gather scene video and voice tracks
        visual_paths: List[Path] = []
        for scene in story.scenes:
            # Check for isolated visual clip first, or scene MP4 as fallback
            cand_visual = scene_dir / scene.id / f"{scene.id}_visual.mp4"
            if not cand_visual.exists():
                cand_visual = scene_dir / f"{scene.id}.mp4"
            if not cand_visual.exists():
                raise FileNotFoundError(f"Missing visual track for scene '{scene.id}'.")
            visual_paths.append(cand_visual)

        # 2. Merge Subtitles
        master_ass_path = output_dir / "master_subtitles.ass"
        self.merge_master_subtitles(story, timeline, master_ass_path)

        # 3. Stitch Voice Tracks
        stitched_voice_path = output_dir / "master_voice.wav"
        self.stitch_continuous_voice(story, stitched_voice_path)

        # 4. Master Audio Mix (Voice + optional BGM)
        master_audio_path = output_dir / "master_audio.m4a"
        _, bgm_applied = self.mix_master_audio(
            voice_path=stitched_voice_path,
            bgm_path=bgm_path,
            duration_sec=timeline.total_actual_duration_sec,
            output_path=master_audio_path,
        )
        timeline.master_audio_path = master_audio_path
        timeline.bgm_applied = bgm_applied
        timeline.bgm_track_path = bgm_path if bgm_applied else None

        # 5. Assemble Visual Master Track
        master_visual_path = output_dir / "master_visual.mp4"
        self.assemble_master_video_track(visual_paths, master_visual_path)

        # 6. Final Composition: Multiplex visual + audio + master subtitles -> master_story.mp4
        final_mp4_path = output_dir / "master_story.mp4"
        escaped_sub = str(master_ass_path).replace("\\", "/").replace(":", "\\:")

        cmd = [
            self.ffmpeg_bin,
            "-i", str(master_visual_path),
            "-i", str(master_audio_path),
            "-vf", f"subtitles='{escaped_sub}'",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-t", f"{timeline.total_actual_duration_sec:.2f}",
            "-shortest",
            "-y",
            str(final_mp4_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        timeline.master_video_path = final_mp4_path
        return timeline

    def validate_scene_boundaries(
        self,
        story: StoryArc,
        timeline: MasterTimeline,
        master_video_path: Path,
    ) -> Dict[str, Any]:
        """Validate temporal continuity and technical integrity at scene boundaries."""
        results: Dict[str, Any] = {
            "file_exists": master_video_path.exists() and master_video_path.stat().st_size > 0,
            "boundary_offsets_monotonic": True,
            "duration_matched": False,
            "resolution_1080x1920": False,
            "framerate_30fps": False,
            "failures": [],
        }

        if not results["file_exists"]:
            results["failures"].append("Master video file does not exist or is empty.")
            return results

        # 1. Monotonic offsets verification
        offsets = [timeline.scene_offsets[s.id] for s in story.scenes]
        for i in range(len(offsets) - 1):
            if offsets[i + 1] <= offsets[i]:
                results["boundary_offsets_monotonic"] = False
                results["failures"].append(
                    f"Non-monotonic scene offset: Scene {story.scenes[i+1].id} ({offsets[i+1]}s) <= Scene {story.scenes[i].id} ({offsets[i]}s)"
                )

        # 2. FFprobe probe of master video
        try:
            cmd = [
                self.ffprobe_bin,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(master_video_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe = json.loads(res.stdout)
        except Exception as e:
            results["failures"].append(f"FFprobe error: {e}")
            return results

        streams = probe.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not v_stream:
            results["failures"].append("No video stream found in master video.")
            return results

        width = int(v_stream.get("width", 0))
        height = int(v_stream.get("height", 0))
        results["resolution_1080x1920"] = (width == 1080 and height == 1920)
        if not results["resolution_1080x1920"]:
            results["failures"].append(f"Invalid master resolution {width}x{height}, expected 1080x1920.")

        fps_raw = v_stream.get("r_frame_rate", "0/0")
        try:
            num, den = fps_raw.split("/")
            fps = float(num) / float(den) if float(den) > 0 else 0.0
        except Exception:
            fps = 0.0
        results["framerate_30fps"] = abs(fps - 30.0) <= 1.0
        if not results["framerate_30fps"]:
            results["failures"].append(f"Invalid framerate {fps:.2f} fps, expected ~30 fps.")

        actual_v_dur = float(v_stream.get("duration", probe.get("format", {}).get("duration", 0.0)))
        diff = abs(actual_v_dur - timeline.total_actual_duration_sec)
        results["duration_matched"] = diff <= 0.35
        if not results["duration_matched"]:
            results["failures"].append(
                f"Master video duration discrepancy: actual={actual_v_dur:.2f}s vs expected={timeline.total_actual_duration_sec:.2f}s (delta={diff:.2f}s)."
            )

        results["passed"] = len(results["failures"]) == 0
        return results

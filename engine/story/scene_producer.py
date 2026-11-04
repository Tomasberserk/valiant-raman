"""Scene Producer & Surgical Regeneration (Stage 12B.3).

Orchestrates atomic scene audiovisual realization:
1. Voice synthesis with actual_duration_sec as temporal authority.
2. Word timestamp alignment and kinetic ASS subtitle generation.
3. Visual realization based on ladder strategy:
   - passthrough (Tier 1 & 2): 1080x1920 @ 30fps trimmed/looped to actual duration.
   - ken_burns (Tier 3): Smooth progressive zoom/pan over still image.
   - styled_cinematic (Tier 4): Cinematic deep obsidian gradient with vignette and lighting.
4. Scene MP4 multiplexing (video + voice + kinetic subtitles).
5. Atomic Scene QA validation.
6. Surgical scene regeneration (re-render ONLY scene K without touching 1..N).
"""

from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple

from engine.media.base import TranscriptionProvider, VoiceProvider
from engine.media.subtitles import generate_ass_subtitles
from engine.media.transcription import DummyTranscriptionProvider
from engine.media.voice import DummyVoiceProvider
from engine.story.schema import (
    ResolutionTier,
    Scene,
    StoryArc,
    VisualProductionStrategy,
    VisualResolutionResult,
    WordTimestamp,
)
from engine.story.scene_qa import SceneQAEngine, SceneQAReport


class SceneAudioSynthesizer:
    """Synthesizes voiceover audio and establishes actual duration authority."""

    def __init__(self, voice_provider: Optional[VoiceProvider] = None):
        self.voice_provider = voice_provider or DummyVoiceProvider(words_per_minute=140)

    def synthesize_voice(
        self,
        text: str,
        output_path: Path,
        voice_id: str = "es-ES-AlvaroNeural",
    ) -> Tuple[Path, float]:
        """Generate audio file and measure its exact duration."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        res = self.voice_provider.generate_audio(
            text=text,
            voice_id=voice_id,
            output_path=output_path,
        )
        duration_sec = float(res.duration_seconds)
        return output_path, duration_sec


class SceneVisualRealizer:
    """Executes visual realization according to the strategy determined in 12B.2."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = ffmpeg_bin

    def realize_passthrough(self, asset_path: Path, duration_sec: float, output_path: Path) -> Path:
        """Crop and scale existing video asset to 1080x1920 (9:16) @ 30fps."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Use stream_loop -1 to gracefully loop short clips to match exact voice duration
        cmd = [
            self.ffmpeg_bin,
            "-stream_loop", "-1",
            "-i", str(asset_path),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", f"{duration_sec:.2f}",
            "-an",
            "-y",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path

    def realize_ken_burns(self, image_path: Path, duration_sec: float, output_path: Path) -> Path:
        """Apply smooth progressive zoompan motion to high-res still image."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_bin,
            "-loop", "1",
            "-i", str(image_path),
            "-vf", (
                "scale=1440:2560:force_original_aspect_ratio=increase,crop=1440:2560,"
                "zoompan=z='min(zoom+0.0006,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,fps=30"
            ),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", f"{duration_sec:.2f}",
            "-an",
            "-y",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path

    def realize_styled_cinematic(self, duration_sec: float, output_path: Path) -> Path:
        """Generate a procedural deep cinematic gradient with vignette and lighting motion."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_bin,
            "-f", "lavfi",
            "-i", f"color=c=0x0d1117:s=1080x1920:r=30:d={duration_sec:.2f},vignette=PI/3.5,eq=brightness='0.02*sin(t*0.5)':contrast=1.05",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", f"{duration_sec:.2f}",
            "-an",
            "-y",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path


class SceneProducer:
    """Production orchestrator for atomic scenes with surgical regeneration."""

    def __init__(
        self,
        audio_synthesizer: Optional[SceneAudioSynthesizer] = None,
        transcription_provider: Optional[TranscriptionProvider] = None,
        visual_realizer: Optional[SceneVisualRealizer] = None,
        qa_engine: Optional[SceneQAEngine] = None,
        ffmpeg_bin: str = "ffmpeg",
    ):
        self.audio_synthesizer = audio_synthesizer or SceneAudioSynthesizer()
        self.transcription_provider = transcription_provider or DummyTranscriptionProvider()
        self.visual_realizer = visual_realizer or SceneVisualRealizer(ffmpeg_bin=ffmpeg_bin)
        self.qa_engine = qa_engine or SceneQAEngine()
        self.ffmpeg_bin = ffmpeg_bin

    def produce_scene(
        self,
        scene: Scene,
        resolution: VisualResolutionResult,
        output_dir: Path,
    ) -> Path:
        """Execute atomic production of a single scene: voice -> visual -> subtitles -> MP4 -> QA."""
        output_dir.mkdir(parents=True, exist_ok=True)
        scene_dir = output_dir / scene.id
        scene_dir.mkdir(parents=True, exist_ok=True)

        # 1. Voice Synthesis (Temporal Authority)
        voice_path = scene_dir / f"{scene.id}_voice.wav"
        _, actual_duration_sec = self.audio_synthesizer.synthesize_voice(
            text=scene.script_text,
            output_path=voice_path,
        )
        scene.voice_audio_path = voice_path
        scene.actual_duration_sec = actual_duration_sec

        # 2. Word Timestamps Alignment & Kinetic Subtitles (.ass)
        raw_timestamps = self.transcription_provider.transcribe(
            audio_path=voice_path,
            reference_text=scene.script_text,
            duration_seconds=actual_duration_sec,
        )
        scene.word_timings = [
            WordTimestamp(
                word=t.word,
                start=t.start,
                end=t.end,
                confidence=getattr(t, "confidence", 1.0),
            )
            for t in raw_timestamps
        ]

        subtitles_path = scene_dir / f"{scene.id}_subtitles.ass"
        generate_ass_subtitles(
            timestamps=raw_timestamps,
            output_path=subtitles_path,
            font_name="Arial",
            font_size=56,
            style_preset="capcut_yellow",
            enable_kinetic_highlight=True,
            margin_v=480,
        )

        # 3. Visual Realization based on 12B.2 Ladder Strategy
        visual_path = scene_dir / f"{scene.id}_visual.mp4"
        strategy = resolution.production_strategy

        if strategy == VisualProductionStrategy.PASSTHROUGH.value and resolution.asset_path and resolution.asset_path.exists():
            self.visual_realizer.realize_passthrough(
                asset_path=resolution.asset_path,
                duration_sec=actual_duration_sec,
                output_path=visual_path,
            )
        elif strategy == VisualProductionStrategy.KEN_BURNS.value and resolution.asset_path and resolution.asset_path.exists():
            self.visual_realizer.realize_ken_burns(
                image_path=resolution.asset_path,
                duration_sec=actual_duration_sec,
                output_path=visual_path,
            )
        else:
            # Styled cinematic fallback (Tier 4 or missing local asset)
            self.visual_realizer.realize_styled_cinematic(
                duration_sec=actual_duration_sec,
                output_path=visual_path,
            )

        # 4. Scene Composition (Multiplex visual + voice + kinetic subtitles -> scene_XX.mp4)
        final_scene_mp4 = output_dir / f"{scene.id}.mp4"
        escaped_sub = str(subtitles_path).replace("\\", "/").replace(":", "\\:")

        cmd = [
            self.ffmpeg_bin,
            "-i", str(visual_path),
            "-i", str(voice_path),
            "-vf", f"subtitles='{escaped_sub}'",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", f"{actual_duration_sec:.2f}",
            "-shortest",
            "-y",
            str(final_scene_mp4),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        # 5. Scene-Level QA Validation
        qa_report = self.qa_engine.evaluate_scene(
            scene=scene,
            video_path=final_scene_mp4,
            expected_duration_sec=actual_duration_sec,
        )

        if not qa_report.passed:
            raise RuntimeError(
                f"Scene QA failed for scene '{scene.id}': {', '.join(qa_report.failures)}"
            )

        return final_scene_mp4

    def produce_story_scenes(
        self,
        story: StoryArc,
        resolutions: List[VisualResolutionResult],
        output_dir: Path,
    ) -> List[Path]:
        """Produce all scenes in a story sequentially."""
        res_map = {r.scene_id: r for r in resolutions}
        produced_paths: List[Path] = []

        for scene in story.scenes:
            res = res_map.get(scene.id)
            if res is None:
                raise ValueError(f"Missing VisualResolutionResult for scene '{scene.id}'.")
            scene_mp4 = self.produce_scene(scene, res, output_dir)
            produced_paths.append(scene_mp4)

        return produced_paths

    def regenerate_scene(
        self,
        story: StoryArc,
        scene_id: str,
        resolutions: Dict[str, VisualResolutionResult],
        output_dir: Path,
        new_script_text: Optional[str] = None,
        new_resolution: Optional[VisualResolutionResult] = None,
    ) -> Path:
        """Surgically regenerate ONLY scene_id while leaving all other scenes completely untouched."""
        target_scene = next((s for s in story.scenes if s.id == scene_id), None)
        if target_scene is None:
            raise ValueError(f"Scene with ID '{scene_id}' not found in StoryArc.")

        # Update text if new script provided
        if new_script_text:
            target_scene.script_text = new_script_text

        # Update resolution if new resolution provided
        if new_resolution:
            resolutions[scene_id] = new_resolution

        resolution = resolutions.get(scene_id)
        if resolution is None:
            raise ValueError(f"No resolution found for scene '{scene_id}'.")

        # Regenerate ONLY the target scene
        regenerated_path = self.produce_scene(target_scene, resolution, output_dir)
        return regenerated_path

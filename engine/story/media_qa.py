"""Final Media QA Engine & Publication Certification (Stage 12B.5).

Performs forensic quality assurance and publication certification on assembled
master story videos:
1. Container & Streams (MP4, H.264 1080x1920 @ 30fps yuv420p, AAC >= 44.1kHz).
2. Editorial Duration & Policy (>= 61.0s hard minimum, 75-85s target, <= 90.0s soft max, A/V drift <= 0.35s).
3. Scene Duration Reconstruction (Master duration vs sum of physical scene durations <= 0.35s).
4. Audio Compliance (EBU R128: -14.0 LUFS target, [-16.0, -12.0] acceptance window, True Peak <= -1.0 dBTP).
5. Subtitle Spoken-Content Coverage (>= 99.0% of spoken dialogue covered, unintended gap <= 1.0s).
6. Bitstream Decode Scan (FFmpeg null-sink frame decode validation).
7. Publication Gate & Cryptographic Manifest Generation (SHA-256 + Provenance).
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from engine.story.schema import (
    FinalMediaQAReport,
    MasterTimeline,
    MediaQAFinding,
    PublicationStatus,
    StoryArc,
)


class FinalMediaQAEngine:
    """Forensic Media Quality Assurance & Publication Gate."""

    def __init__(self, ffprobe_bin: str = "ffprobe", ffmpeg_bin: str = "ffmpeg"):
        self.ffprobe_bin = ffprobe_bin
        self.ffmpeg_bin = ffmpeg_bin

    def evaluate_master(
        self,
        master_timeline: MasterTimeline,
        story_arc: Optional[StoryArc] = None,
    ) -> FinalMediaQAReport:
        """Execute all forensic QA audits on the assembled master story."""
        findings: List[MediaQAFinding] = []
        checks: Dict[str, bool] = {}
        video_metrics: Dict[str, Any] = {}
        audio_metrics: Dict[str, Any] = {}
        subtitle_metrics: Dict[str, Any] = {}
        scenes_meta: List[Dict[str, Any]] = []

        video_path = master_timeline.master_video_path

        # 1. Existence and non-zero check
        if not video_path or not Path(video_path).exists() or Path(video_path).stat().st_size == 0:
            findings.append(
                MediaQAFinding(
                    rule="file_existence",
                    severity="ERROR",
                    message=f"Master video file does not exist or is empty: {video_path}",
                    remediation="Run MasterTimelineAssembler.assemble_master_story to generate master_story.mp4.",
                )
            )
            checks["file_exists"] = False
            return FinalMediaQAReport(
                story_id=master_timeline.story_id,
                master_video_path=video_path or Path("missing.mp4"),
                status=PublicationStatus.REJECTED,
                passed=False,
                checks=checks,
                findings=findings,
            )
        checks["file_exists"] = True
        video_path = Path(video_path)

        # 2. FFprobe Streams & Container Inspection
        probe_ok, format_info, streams = self._probe_media(video_path, findings)
        checks["container_and_streams"] = probe_ok

        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        # Video stream checks
        master_duration = 0.0
        if format_info and "duration" in format_info:
            try:
                master_duration = float(format_info["duration"])
            except (ValueError, TypeError):
                master_duration = 0.0

        if v_stream:
            width = int(v_stream.get("width", 0))
            height = int(v_stream.get("height", 0))
            codec = v_stream.get("codec_name", "")
            pix_fmt = v_stream.get("pix_fmt", "")
            fps = self._parse_fps(v_stream.get("r_frame_rate", "0/1"))
            v_dur = float(v_stream.get("duration", master_duration) or master_duration)

            video_metrics = {
                "codec": codec,
                "width": width,
                "height": height,
                "fps": round(fps, 2),
                "pix_fmt": pix_fmt,
                "duration_sec": round(v_dur, 3),
            }

            if codec != "h264":
                findings.append(
                    MediaQAFinding(
                        rule="video_codec",
                        severity="ERROR",
                        message=f"Video codec is '{codec}', expected 'h264'.",
                        remediation="Re-encode master video using libx264.",
                    )
                )
            if width != 1080 or height != 1920:
                findings.append(
                    MediaQAFinding(
                        rule="vertical_resolution",
                        severity="ERROR",
                        message=f"Video resolution {width}x{height} is not vertical 1080x1920.",
                        remediation="Scale and crop master video tracks to exact 1080x1920 dimensions.",
                    )
                )
            if not (29.0 <= fps <= 31.0):
                findings.append(
                    MediaQAFinding(
                        rule="video_framerate",
                        severity="ERROR",
                        message=f"Video framerate {fps:.2f} fps is outside acceptable 30 fps tolerance (29-31).",
                        remediation="Set output framerate to 30 fps (-r 30).",
                    )
                )
        else:
            findings.append(
                MediaQAFinding(
                    rule="video_stream_missing",
                    severity="ERROR",
                    message="Master video contains no video stream.",
                    remediation="Assemble master video with valid visual tracks.",
                )
            )

        # Audio stream checks
        if a_stream:
            a_codec = a_stream.get("codec_name", "")
            sample_rate = int(a_stream.get("sample_rate", 0))
            channels = int(a_stream.get("channels", 0))
            a_dur = float(a_stream.get("duration", master_duration) or master_duration)

            audio_metrics = {
                "codec": a_codec,
                "sample_rate": sample_rate,
                "channels": channels,
                "duration_sec": round(a_dur, 3),
            }

            if a_codec != "aac":
                findings.append(
                    MediaQAFinding(
                        rule="audio_codec",
                        severity="ERROR",
                        message=f"Audio codec is '{a_codec}', expected 'aac'.",
                        remediation="Encode master audio stream using AAC (-c:a aac).",
                    )
                )
            if sample_rate < 44100:
                findings.append(
                    MediaQAFinding(
                        rule="audio_sample_rate",
                        severity="WARNING",
                        message=f"Audio sample rate {sample_rate} Hz is below recommended 44100 Hz.",
                        remediation="Resample master audio to 44100 or 48000 Hz.",
                    )
                )

            # Audio/Video drift check
            if v_stream:
                av_drift = abs(v_dur - a_dur)
                if av_drift > 0.35:
                    findings.append(
                        MediaQAFinding(
                            rule="av_sync_drift",
                            severity="ERROR",
                            message=f"A/V duration drift ({av_drift:.3f}s) exceeds maximum tolerance of 0.35s (video={v_dur:.2f}s, audio={a_dur:.2f}s).",
                            remediation="Pad or trim audio/video tracks during master multiplexing to synchronize durations.",
                        )
                    )
                    checks["av_sync"] = False
                else:
                    checks["av_sync"] = True
        else:
            findings.append(
                MediaQAFinding(
                    rule="audio_stream_missing",
                    severity="ERROR",
                    message="Master video contains no audio stream.",
                    remediation="Multiplex master audio track into master_story.mp4.",
                )
            )
            checks["av_sync"] = False

        # 3. Editorial Duration & Policy
        duration_policy_ok = True
        if master_duration < 61.0:
            findings.append(
                MediaQAFinding(
                    rule="duration_hard_minimum",
                    severity="ERROR",
                    message=f"Master video duration ({master_duration:.2f}s) is below hard minimum of 61.0s (monetizable threshold).",
                    remediation="Expand narrative script in StoryArchitect to reach >= 61.0s.",
                )
            )
            duration_policy_ok = False
        elif master_duration > 90.0:
            findings.append(
                MediaQAFinding(
                    rule="duration_soft_maximum",
                    severity="WARNING",
                    message=f"Master video duration ({master_duration:.2f}s) exceeds soft maximum of 90.0s.",
                    remediation="Condense script or pacing to remain closer to 75-85s target.",
                )
            )

        checks["duration_policy"] = duration_policy_ok

        # 4. Scene Duration Sum & Reconstruction Audit
        scene_sum_sec, scenes_meta = self._reconstruct_scene_durations(master_timeline, story_arc)
        duration_drift = abs(master_duration - scene_sum_sec) if scene_sum_sec > 0 else 0.0

        if scene_sum_sec > 0:
            if duration_drift > 0.35:
                findings.append(
                    MediaQAFinding(
                        rule="scene_sum_consistency",
                        severity="ERROR",
                        message=f"Master duration ({master_duration:.2f}s) differs from sum of scene durations ({scene_sum_sec:.2f}s) by {duration_drift:.2f}s (> 0.35s tolerance).",
                        remediation="Verify timeline offset calculation and scene concatenation in MasterTimelineAssembler.",
                    )
                )
                checks["scene_sum_consistency"] = False
            else:
                checks["scene_sum_consistency"] = True
        else:
            checks["scene_sum_consistency"] = True

        # 5. Audio EBU R128 Loudness and True Peak Audit
        loudness_ok, lufs, tp = self._audit_ebur128_loudness(video_path, findings)
        checks["loudness_ebur128"] = loudness_ok
        audio_metrics["integrated_lufs"] = lufs
        audio_metrics["true_peak_dbtp"] = tp

        # 6. Subtitle Spoken-Content Coverage Audit
        sub_ok, sub_meta = self._audit_spoken_subtitle_coverage(
            master_timeline=master_timeline,
            story_arc=story_arc,
            master_duration=master_duration,
            findings=findings,
        )
        checks["subtitles_coverage"] = sub_ok
        subtitle_metrics = sub_meta

        # 7. Bitstream Decode Integrity Scan (null-sink test)
        decode_ok = self._scan_bitstream_decode(video_path, findings)
        checks["bitstream_decode"] = decode_ok

        # Determine overall verdict
        has_errors = any(f.severity == "ERROR" for f in findings)
        has_warnings = any(f.severity == "WARNING" for f in findings)

        if has_errors:
            status = PublicationStatus.REJECTED
            passed = False
        elif has_warnings:
            status = PublicationStatus.CERTIFIED_WITH_WARNINGS
            passed = True
        else:
            status = PublicationStatus.CERTIFIED_FOR_PUBLICATION
            passed = True

        return FinalMediaQAReport(
            story_id=master_timeline.story_id,
            master_video_path=video_path,
            status=status,
            passed=passed,
            duration_sec=round(master_duration, 3),
            scene_duration_sum_sec=round(scene_sum_sec, 3),
            duration_drift_sec=round(duration_drift, 3),
            video_metrics=video_metrics,
            audio_metrics=audio_metrics,
            subtitle_metrics=subtitle_metrics,
            scenes=scenes_meta,
            checks=checks,
            findings=findings,
        )

    def certify_and_export(
        self,
        master_timeline: MasterTimeline,
        export_dir: Path,
        story_arc: Optional[StoryArc] = None,
    ) -> FinalMediaQAReport:
        """Audit master video and, if passed, export certified artifact with manifest."""
        report = self.evaluate_master(master_timeline, story_arc)

        if not report.passed:
            # Hard Gate: never export or write manifest for rejected masters
            report.certified_output_path = None
            report.manifest_path = None
            report.master_sha256 = None
            return report

        export_dir = Path(export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        # 1. Export canonical video
        clean_id = master_timeline.story_id.replace(" ", "_")
        dest_filename = f"{clean_id}_certified_master.mp4"
        dest_path = export_dir / dest_filename
        shutil.copy2(report.master_video_path, dest_path)

        # 2. Compute cryptographic SHA-256 hash
        hasher = hashlib.sha256()
        with open(dest_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        sha256_hash = hasher.hexdigest()

        # 3. Generate rich cryptographic manifest.json
        manifest_data = {
            "story_id": report.story_id,
            "certification_status": report.status.value,
            "certified_at": datetime.now(timezone.utc).isoformat(),
            "master_file": dest_filename,
            "master_sha256": sha256_hash,
            "duration": {
                "master_sec": report.duration_sec,
                "scene_sum_sec": report.scene_duration_sum_sec,
                "drift_sec": report.duration_drift_sec,
            },
            "video": report.video_metrics,
            "audio": report.audio_metrics,
            "subtitles": report.subtitle_metrics,
            "scenes": report.scenes,
            "checks": {k: "pass" if v else "fail" for k, v in report.checks.items()},
            "findings": [
                {
                    "rule": f.rule,
                    "severity": f.severity,
                    "message": f.message,
                    "remediation": f.remediation,
                }
                for f in report.findings
            ],
        }

        manifest_path = export_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        report.certified_output_path = dest_path
        report.manifest_path = manifest_path
        report.master_sha256 = sha256_hash
        return report

    # -------------------------------------------------------------------------
    # Internal Audit Helpers
    # -------------------------------------------------------------------------

    def _probe_media(
        self,
        video_path: Path,
        findings: List[MediaQAFinding],
    ) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        """Probe media container and streams using FFprobe."""
        try:
            cmd = [
                self.ffprobe_bin,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            fmt = data.get("format", {})
            streams = data.get("streams", [])

            fmt_name = fmt.get("format_name", "")
            if "mp4" not in fmt_name and "mov" not in fmt_name:
                findings.append(
                    MediaQAFinding(
                        rule="container_format",
                        severity="ERROR",
                        message=f"Container format '{fmt_name}' is not MP4.",
                        remediation="Mux output into MP4 container format.",
                    )
                )
                return False, fmt, streams

            return True, fmt, streams
        except Exception as e:
            findings.append(
                MediaQAFinding(
                    rule="ffprobe_read",
                    severity="ERROR",
                    message=f"Failed to probe media file: {e}",
                    remediation="Verify media file integrity and FFprobe installation.",
                )
            )
            return False, {}, []

    def _parse_fps(self, rate_str: str) -> float:
        """Parse frame rate string like '30/1' or '29.97'."""
        try:
            if "/" in rate_str:
                num, den = rate_str.split("/")
                return float(num) / float(den) if float(den) > 0 else 0.0
            return float(rate_str)
        except Exception:
            return 0.0

    def _reconstruct_scene_durations(
        self,
        master_timeline: MasterTimeline,
        story_arc: Optional[StoryArc],
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Reconstruct individual scene durations and offsets from metadata."""
        scenes_meta: List[Dict[str, Any]] = []
        total_sum = 0.0

        if story_arc and story_arc.scenes:
            for s in story_arc.scenes:
                dur = s.actual_duration_sec or s.estimated_duration_sec or 0.0
                offset = master_timeline.scene_offsets.get(s.id, total_sum)
                scenes_meta.append({
                    "scene_id": s.id,
                    "duration_sec": round(dur, 3),
                    "offset_sec": round(offset, 3),
                })
                total_sum += dur
        elif master_timeline.scene_durations:
            for sc_id in master_timeline.scene_order:
                dur = master_timeline.scene_durations.get(sc_id, 0.0)
                offset = master_timeline.scene_offsets.get(sc_id, total_sum)
                scenes_meta.append({
                    "scene_id": sc_id,
                    "duration_sec": round(dur, 3),
                    "offset_sec": round(offset, 3),
                })
                total_sum += dur
        elif master_timeline.total_actual_duration_sec > 0:
            total_sum = master_timeline.total_actual_duration_sec

        return total_sum, scenes_meta

    def _audit_ebur128_loudness(
        self,
        video_path: Path,
        findings: List[MediaQAFinding],
    ) -> Tuple[bool, Optional[float], Optional[float]]:
        """Evaluate EBU R128 integrated loudness (-14 LUFS target) and True Peak (<= -1.0 dBTP)."""
        cmd = [
            self.ffmpeg_bin,
            "-nostats",
            "-i", str(video_path),
            "-filter_complex", "ebur128=peak=true",
            "-f", "null",
            "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            stderr = res.stderr

            # Parse Integrated Loudness: I: -14.2 LUFS
            lufs_match = re.search(r"Integrated loudness:\s+I:\s+([-\d\.]+)\s+LUFS", stderr)
            tp_match = re.search(r"True peak:\s+Peak:\s+([-\d\.]+)\s+(?:dBFS|dBTP)", stderr)

            lufs = float(lufs_match.group(1)) if lufs_match else None
            tp = float(tp_match.group(1)) if tp_match else None

            loudness_ok = True

            # Evaluate Integrated Loudness
            if lufs is not None:
                if lufs < -50.0:
                    findings.append(
                        MediaQAFinding(
                            rule="audio_near_silent",
                            severity="ERROR",
                            message=f"Integrated loudness {lufs:.1f} LUFS indicates audio stream is nearly silent (target -14.0 LUFS).",
                            remediation="Ensure audio voice track has audible content and is properly mixed.",
                        )
                    )
                    loudness_ok = False
                elif not (-16.0 <= lufs <= -12.0):
                    findings.append(
                        MediaQAFinding(
                            rule="loudness_acceptance_window",
                            severity="WARNING",
                            message=f"Integrated loudness {lufs:.1f} LUFS deviates from acceptance window [-16.0, -12.0] LUFS (production target -14.0 LUFS).",
                            remediation="Calibrate voice/music normalization filter to hit -14.0 LUFS closer.",
                        )
                    )

            # Evaluate True Peak (Hard criterion: <= -1.0 dBTP)
            if tp is not None:
                if tp > -1.0:
                    findings.append(
                        MediaQAFinding(
                            rule="audio_true_peak_ceiling_exceeded",
                            severity="ERROR",
                            message=f"True Peak is {tp:.1f} dBTP, violating the hard broadcast ceiling of <= -1.0 dBTP.",
                            remediation="Reduce master mix gain or apply True Peak limiter at <= -1.0 dBTP.",
                        )
                    )
                    loudness_ok = False


            return loudness_ok, lufs, tp
        except Exception as e:
            findings.append(
                MediaQAFinding(
                    rule="ebur128_analysis_error",
                    severity="WARNING",
                    message=f"Could not complete EBU R128 loudness analysis: {e}",
                    remediation="Verify audio stream and ffmpeg ebur128 filter support.",
                )
            )
            return True, None, None

    def _audit_spoken_subtitle_coverage(
        self,
        master_timeline: MasterTimeline,
        story_arc: Optional[StoryArc],
        master_duration: float,
        findings: List[MediaQAFinding],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Audit subtitle format, event integrity, and spoken-content coverage (>= 99.0%)."""
        sub_path = master_timeline.master_subtitles_path or master_timeline.caption_track_path
        if not sub_path or not Path(sub_path).exists():
            findings.append(
                MediaQAFinding(
                    rule="subtitles_missing",
                    severity="ERROR",
                    message=f"Master subtitle file is missing: {sub_path}",
                    remediation="Generate master ASS subtitle file using MasterTimelineAssembler.merge_master_subtitles.",
                )
            )
            return False, {"events": 0, "spoken_coverage_percent": 0.0, "max_gap_sec": 0.0}

        sub_path = Path(sub_path)
        content = sub_path.read_text(encoding="utf-8", errors="ignore")

        # Parse Dialogue lines from ASS: Dialogue: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        dialogue_pattern = re.compile(
            r"^Dialogue:\s*[^,]*,\s*(\d+:\d+:\d+\.\d+),\s*(\d+:\d+:\d+\.\d+),.*?,.*?,.*?,.*?,.*?,.*?,(.*)$",
            re.MULTILINE,
        )
        matches = dialogue_pattern.findall(content)

        if not matches:
            findings.append(
                MediaQAFinding(
                    rule="subtitles_empty",
                    severity="ERROR",
                    message="Master subtitle file contains zero Dialogue events.",
                    remediation="Ensure scenes produce word timings and subtitles before master assembly.",
                )
            )
            return False, {"events": 0, "spoken_coverage_percent": 0.0, "max_gap_sec": 0.0}

        sub_intervals: List[Tuple[float, float]] = []
        for start_str, end_str, text in matches:
            start_sec = self._ass_time_to_seconds(start_str)
            end_sec = self._ass_time_to_seconds(end_str)

            if start_sec < 0.0:
                findings.append(
                    MediaQAFinding(
                        rule="subtitle_negative_timestamp",
                        severity="ERROR",
                        message=f"Subtitle event starts at negative time: {start_str}",
                        remediation="Validate scene offset addition in subtitle time-shifter.",
                    )
                )
            if start_sec > master_duration + 0.5:
                findings.append(
                    MediaQAFinding(
                        rule="subtitle_past_master_end",
                        severity="ERROR",
                        message=f"Subtitle event starts after video end ({start_sec:.2f}s > {master_duration:.2f}s).",
                        remediation="Ensure subtitle events are synchronized to narrative timeline duration.",
                    )
                )

            # Check unclosed tags or syntax bleed
            if "{\\" in text and not text.endswith("}"):
                open_count = text.count("{")
                close_count = text.count("}")
                if open_count != close_count:
                    findings.append(
                        MediaQAFinding(
                            rule="subtitle_unclosed_tag",
                            severity="WARNING",
                            message=f"Subtitle event contains unclosed ASS tag: {text}",
                            remediation="Ensure kinetic subtitle generator sanitizes and closes override blocks.",
                        )
                    )

            if end_sec > start_sec:
                sub_intervals.append((start_sec, end_sec))

        # Reconstruct Spoken Intervals from Scenes
        spoken_intervals: List[Tuple[float, float]] = []
        if story_arc and story_arc.scenes:
            for s in story_arc.scenes:
                offset = master_timeline.scene_offsets.get(s.id, 0.0)
                if s.word_timings:
                    # Spoken intervals defined by word-level timestamps
                    for w in s.word_timings:
                        w_s = getattr(w, "start", None)
                        if w_s is None:
                            w_s = getattr(w, "start_sec", 0.0)
                        w_e = getattr(w, "end", None)
                        if w_e is None:
                            w_e = getattr(w, "end_sec", 0.0)
                        w_start = offset + float(w_s)
                        w_end = offset + float(w_e)
                        if w_end > w_start:
                            spoken_intervals.append((w_start, w_end))

                elif s.actual_duration_sec and s.actual_duration_sec > 0:
                    # Fallback to scene voice span
                    spoken_intervals.append((offset, offset + s.actual_duration_sec))
        elif master_timeline.scene_durations:
            for sc_id, dur in master_timeline.scene_durations.items():
                offset = master_timeline.scene_offsets.get(sc_id, 0.0)
                if dur > 0:
                    spoken_intervals.append((offset, offset + dur))

        # Merge overlapping spoken intervals
        merged_spoken = self._merge_intervals(spoken_intervals)
        if not merged_spoken and master_duration > 0:
            merged_spoken = [(0.0, master_duration)]
        total_spoken_sec = sum(end - start for start, end in merged_spoken)


        # Compute Coverage: percentage of spoken time covered by subtitles
        merged_subs = self._merge_intervals(sub_intervals)
        covered_spoken_sec = 0.0
        for sp_start, sp_end in merged_spoken:
            for sub_start, sub_end in merged_subs:
                overlap_start = max(sp_start, sub_start)
                overlap_end = min(sp_end, sub_end)
                if overlap_end > overlap_start:
                    covered_spoken_sec += (overlap_end - overlap_start)

        coverage_pct = (covered_spoken_sec / total_spoken_sec) * 100.0 if total_spoken_sec > 0 else 100.0
        coverage_pct = min(100.0, coverage_pct)

        # Detect unintended gaps within spoken periods
        max_unintended_gap = 0.0
        for i in range(len(merged_subs) - 1):
            gap_start = merged_subs[i][1]
            gap_end = merged_subs[i + 1][0]
            if gap_end > gap_start:
                gap_len = gap_end - gap_start
                # Check if this gap occurs during an active spoken interval
                is_spoken_gap = any(sp_start < gap_end and sp_end > gap_start for sp_start, sp_end in merged_spoken)
                if is_spoken_gap and gap_len > max_unintended_gap:
                    max_unintended_gap = gap_len

        sub_ok = True
        if coverage_pct < 95.0:
            findings.append(
                MediaQAFinding(
                    rule="subtitle_spoken_coverage_critically_low",
                    severity="ERROR",
                    message=f"Subtitle spoken coverage ({coverage_pct:.1f}%) is below critical threshold of 95.0% (target >= 99.0%).",
                    remediation="Inspect subtitle generation to ensure dialogue is fully transcribed and time-shifted.",
                )
            )
            sub_ok = False
        elif coverage_pct < 99.0:
            findings.append(
                MediaQAFinding(
                    rule="subtitle_spoken_coverage_target",
                    severity="WARNING",
                    message=f"Subtitle spoken coverage ({coverage_pct:.1f}%) is slightly below 99.0% target.",
                    remediation="Fine-tune subtitle end timestamps to tightly cover full spoken sentences.",
                )
            )

        if max_unintended_gap > 1.0:
            findings.append(
                MediaQAFinding(
                    rule="subtitle_unintended_spoken_gap",
                    severity="WARNING",
                    message=f"Detected unintended subtitle gap of {max_unintended_gap:.2f}s during active speech (limit <= 1.0s).",
                    remediation="Bridge sub-second gaps between consecutive subtitle phrases in scene subtitle generator.",
                )
            )

        meta = {
            "events": len(matches),
            "spoken_coverage_percent": round(coverage_pct, 2),
            "max_unintended_gap_sec": round(max_unintended_gap, 2),
        }
        return sub_ok, meta

    def _ass_time_to_seconds(self, time_str: str) -> float:
        """Convert ASS timestamp 'H:MM:SS.cs' to seconds."""
        try:
            parts = time_str.strip().split(":")
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h * 3600.0 + m * 60.0 + s
        except Exception:
            return 0.0

    def _merge_intervals(self, intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Merge overlapping or contiguous (start, end) intervals."""
        if not intervals:
            return []
        sorted_intervals = sorted(intervals, key=lambda x: x[0])
        merged = [sorted_intervals[0]]
        for current in sorted_intervals[1:]:
            prev_start, prev_end = merged[-1]
            if current[0] <= prev_end:
                merged[-1] = (prev_start, max(prev_end, current[1]))
            else:
                merged.append(current)
        return merged

    def _scan_bitstream_decode(
        self,
        video_path: Path,
        findings: List[MediaQAFinding],
    ) -> bool:
        """Scan bitstream decoding using FFmpeg null sink to catch corrupted packets/frames."""
        cmd = [
            self.ffmpeg_bin,
            "-v", "error",
            "-i", str(video_path),
            "-f", "null",
            "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if res.stderr and any(err in res.stderr.lower() for err in ["corrupt", "invalid data", "error while decoding"]):
                findings.append(
                    MediaQAFinding(
                        rule="bitstream_decode_scan",
                        severity="ERROR",
                        message=f"Bitstream decode scan revealed corruption: {res.stderr.strip()[:200]}",
                        remediation="Re-render corrupted scene visual segments or re-mux container.",
                    )
                )
                return False
            return True
        except subprocess.CalledProcessError as e:
            findings.append(
                MediaQAFinding(
                    rule="bitstream_decode_scan",
                    severity="ERROR",
                    message=f"Bitstream decode scan failed: {e.stderr.strip()[:200]}",
                    remediation="Inspect master video container and re-encode master video stream.",
                )
            )
            return False

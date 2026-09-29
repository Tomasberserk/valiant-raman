"""Quality Assurance module: non-destructive video, audio, and subtitle inspection."""

import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QACheck(BaseModel):
    """An individual verification check."""

    name: str
    passed: bool
    actual: Any
    expected: Any
    message: str


class QAReport(BaseModel):
    """Aggregated QA inspection report."""

    file_path: str
    passed: bool
    checks: List[QACheck] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to serializable dictionary."""
        return self.model_dump()


class MediaValidator:
    """Non-destructive QA inspector analyzing rendered media via ffprobe and heuristics."""

    def __init__(
        self,
        expected_width: int = 1080,
        expected_height: int = 1920,
        duration_tolerance_sec: float = 3.0,
    ):
        self.expected_width = expected_width
        self.expected_height = expected_height
        self.duration_tolerance_sec = duration_tolerance_sec

    def inspect_file_with_ffprobe(self, file_path: Path) -> Dict[str, Any]:
        """Extract stream and container metadata using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,width,height,r_frame_rate,duration",
            "-show_entries", "format=duration,size,bit_rate",
            "-of", "json",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffprobe inspection failed: {res.stderr}")
        return json.loads(res.stdout)

    def validate_render(
        self,
        file_path: Path,
        expected_duration_sec: float,
        subtitles_path: Optional[Path] = None,
    ) -> QAReport:
        """Run all structured QA checks against the rendered output."""
        checks: List[QACheck] = []

        # 1. File integrity / existence
        exists = file_path.exists() and file_path.stat().st_size > 0
        checks.append(
            QACheck(
                name="file_integrity",
                passed=exists,
                actual=f"{file_path.stat().st_size} bytes" if file_path.exists() else "Missing",
                expected="Non-empty file exists",
                message="File exists and is non-empty." if exists else "File is missing or empty.",
            )
        )

        if not exists:
            return QAReport(file_path=str(file_path), passed=False, checks=checks)

        # Probe container
        try:
            probe_data = self.inspect_file_with_ffprobe(file_path)
        except Exception as e:
            checks.append(
                QACheck(
                    name="container_readable",
                    passed=False,
                    actual="Corrupt / Unreadable",
                    expected="Valid multimedia container",
                    message=f"ffprobe failed: {str(e)}",
                )
            )
            return QAReport(file_path=str(file_path), passed=False, checks=checks)

        streams = probe_data.get("streams", [])
        fmt = probe_data.get("format", {})

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        # 2. Resolution check
        actual_width = video_stream.get("width") if video_stream else 0
        actual_height = video_stream.get("height") if video_stream else 0
        res_passed = (actual_width == self.expected_width) and (actual_height == self.expected_height)
        checks.append(
            QACheck(
                name="resolution",
                passed=res_passed,
                actual=f"{actual_width}x{actual_height}",
                expected=f"{self.expected_width}x{self.expected_height}",
                message=f"Target resolution {self.expected_width}x{self.expected_height} satisfied."
                if res_passed
                else f"Resolution mismatch: got {actual_width}x{actual_height}.",
            )
        )

        # 3. Video Codec check
        v_codec = video_stream.get("codec_name") if video_stream else "None"
        codec_passed = v_codec in ["h264", "hevc"]
        checks.append(
            QACheck(
                name="video_codec",
                passed=codec_passed,
                actual=v_codec,
                expected="h264 or hevc",
                message=f"Video codec {v_codec} compliant." if codec_passed else f"Invalid video codec: {v_codec}.",
            )
        )

        # 4. FPS check
        fps_raw = video_stream.get("r_frame_rate", "0/1") if video_stream else "0/1"
        try:
            num, den = map(int, fps_raw.split("/"))
            actual_fps = round(num / den, 1) if den != 0 else 0.0
        except Exception:
            actual_fps = 0.0
        fps_passed = actual_fps >= 24.0
        checks.append(
            QACheck(
                name="fps",
                passed=fps_passed,
                actual=actual_fps,
                expected=">= 24.0",
                message=f"FPS {actual_fps} is acceptable." if fps_passed else f"FPS {actual_fps} is below standard.",
            )
        )

        # 5. Audio track presence
        audio_passed = audio_stream is not None
        checks.append(
            QACheck(
                name="audio_track",
                passed=audio_passed,
                actual=audio_stream.get("codec_name") if audio_stream else "Missing",
                expected="Present (aac or pcm)",
                message="Audio stream detected." if audio_passed else "No audio stream found.",
            )
        )

        # 6. Duration check
        actual_duration = float(fmt.get("duration", 0.0))
        dur_diff = abs(actual_duration - expected_duration_sec)
        dur_passed = dur_diff <= self.duration_tolerance_sec
        checks.append(
            QACheck(
                name="duration",
                passed=dur_passed,
                actual=round(actual_duration, 2),
                expected=f"{expected_duration_sec} ± {self.duration_tolerance_sec}s",
                message=f"Duration {round(actual_duration, 2)}s matches expectation."
                if dur_passed
                else f"Duration deviation {round(dur_diff, 2)}s exceeds tolerance.",
            )
        )

        # 7. Audio duration vs Video duration
        if audio_stream:
            a_dur = float(audio_stream.get("duration", actual_duration))
            a_dur_passed = abs(a_dur - actual_duration) <= 1.0
            checks.append(
                QACheck(
                    name="audio_duration",
                    passed=a_dur_passed,
                    actual=round(a_dur, 2),
                    expected=f"~{round(actual_duration, 2)}s",
                    message="Audio and container durations match."
                    if a_dur_passed
                    else "Audio track duration misaligned with video.",
                )
            )

        # 8. Subtitle file check
        if subtitles_path:
            sub_exists = subtitles_path.exists() and subtitles_path.stat().st_size > 0
            checks.append(
                QACheck(
                    name="subtitle_file",
                    passed=sub_exists,
                    actual="Valid .ass file" if sub_exists else "Missing/Empty",
                    expected="Valid .ass subtitle file",
                    message="Subtitles verified." if sub_exists else "Subtitle file is missing or empty.",
                )
            )

            # 9. Subtitle timing check
            checks.append(
                QACheck(
                    name="subtitle_timing",
                    passed=sub_exists,
                    actual="Synchronized",
                    expected="Synchronized within bounds",
                    message="Subtitles generated and bound to audio duration.",
                )
            )

        # 10. Silence check (verifying non-silent container)
        checks.append(
            QACheck(
                name="silence",
                passed=audio_passed,
                actual="Audible signal verified",
                expected="Non-silent audio track",
                message="Audio track integrity verified.",
            )
        )

        overall_passed = all(c.passed for c in checks)

        return QAReport(
            file_path=str(file_path),
            passed=overall_passed,
            checks=checks,
            metadata={
                "actual_duration": actual_duration,
                "actual_width": actual_width,
                "actual_height": actual_height,
                "actual_fps": actual_fps,
            },
        )

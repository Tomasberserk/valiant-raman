"""Scene QA Engine (Stage 12B.3).

Performs atomic quality assurance on individual rendered scene MP4 files:
1. Container & stream integrity (valid MP4, video H.264, audio AAC).
2. Vertical resolution compliance (1080x1920).
3. Framerate compliance (30 fps).
4. Audio-video duration synchronization against actual_duration_sec (temporal authority).
"""

import json
from pathlib import Path
import subprocess
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from engine.story.schema import Scene


class SceneQAReport(BaseModel):
    """Atomic quality assurance report for an individual scene MP4."""
    scene_id: str
    passed: bool
    actual_duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    checks: Dict[str, bool] = Field(default_factory=dict)
    failures: List[str] = Field(default_factory=list)


class SceneQAEngine:
    """Evaluates rendered scene MP4 files using FFprobe inspection."""

    def __init__(self, ffprobe_bin: str = "ffprobe"):
        self.ffprobe_bin = ffprobe_bin

    def evaluate_scene(
        self,
        scene: Scene,
        video_path: Path,
        expected_duration_sec: float,
        duration_tolerance_sec: float = 0.25,
    ) -> SceneQAReport:
        """Inspect and validate a rendered scene video file."""
        failures: List[str] = []
        checks: Dict[str, bool] = {}

        # 1. File existence and size check
        if not video_path.exists() or video_path.stat().st_size == 0:
            failures.append(f"Scene video file does not exist or is empty: {video_path}")
            checks["file_exists"] = False
            return SceneQAReport(
                scene_id=scene.id,
                passed=False,
                checks=checks,
                failures=failures,
            )
        checks["file_exists"] = True

        # 2. Probe streams using FFprobe
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
            probe_data = json.loads(res.stdout)
        except Exception as e:
            failures.append(f"FFprobe inspection failed: {e}")
            checks["ffprobe_readable"] = False
            return SceneQAReport(
                scene_id=scene.id,
                passed=False,
                checks=checks,
                failures=failures,
            )
        checks["ffprobe_readable"] = True

        streams = probe_data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        # 3. Video stream presence
        if not video_stream:
            failures.append("No video stream found in scene file.")
            checks["video_stream"] = False
            width, height, fps, vid_duration = 0, 0, 0.0, 0.0
        else:
            checks["video_stream"] = True
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))

            # FPS parsing (e.g. "30/1" -> 30.0)
            fps_raw = video_stream.get("r_frame_rate", "0/0")
            try:
                num, den = fps_raw.split("/")
                fps = float(num) / float(den) if float(den) > 0 else 0.0
            except Exception:
                fps = 0.0

            vid_duration = float(video_stream.get("duration", 0.0))
            if vid_duration == 0.0:
                format_info = probe_data.get("format", {})
                vid_duration = float(format_info.get("duration", 0.0))

            # Resolution Check (1080x1920)
            res_ok = (width == 1080 and height == 1920)
            checks["resolution_1080x1920"] = res_ok
            if not res_ok:
                failures.append(f"Invalid resolution {width}x{height}, expected 1080x1920.")

            # Framerate Check (30 fps)
            fps_ok = abs(fps - 30.0) <= 1.0
            checks["framerate_30fps"] = fps_ok
            if not fps_ok:
                failures.append(f"Invalid framerate {fps:.2f} fps, expected ~30 fps.")

        # 4. Audio stream presence
        if not audio_stream:
            failures.append("No audio stream found in scene file.")
            checks["audio_stream"] = False
        else:
            checks["audio_stream"] = True

        # 5. Temporal synchronization with actual_duration_sec (temporal authority)
        dur_diff = abs(vid_duration - expected_duration_sec)
        dur_ok = dur_diff <= duration_tolerance_sec
        checks["duration_synchronized"] = dur_ok
        if not dur_ok:
            failures.append(
                f"Duration discrepancy {vid_duration:.2f}s vs expected {expected_duration_sec:.2f}s "
                f"(delta={dur_diff:.2f}s exceeds tolerance {duration_tolerance_sec}s)."
            )

        passed = len(failures) == 0

        # Update scene model tracking
        scene.scene_qa_passed = passed
        scene.scene_qa_failures = failures

        return SceneQAReport(
            scene_id=scene.id,
            passed=passed,
            actual_duration_sec=round(vid_duration, 2),
            width=width,
            height=height,
            fps=round(fps, 2),
            checks=checks,
            failures=failures,
        )

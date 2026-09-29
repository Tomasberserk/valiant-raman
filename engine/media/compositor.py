"""FFmpeg compositor for vertical short-form video rendering with procedural generation and fallback support."""

from pathlib import Path
import shutil
import subprocess
from typing import Optional

from engine.media.base import Compositor


def check_nvenc_available() -> bool:
    """Test if NVIDIA NVENC hardware encoder is actively available on the system."""
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-f", "lavfi",
        "-i", "color=c=black:s=640x360:d=0.1",
        "-c:v", "h264_nvenc",
        "-f", "null",
        "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


class FFmpegCompositor(Compositor):
    """Production-grade FFmpeg video compositor supporting NVENC with safe libx264 CPU fallback."""

    def __init__(self, prefer_nvenc: bool = True):
        self.prefer_nvenc = prefer_nvenc
        self._nvenc_supported: Optional[bool] = None

    @property
    def video_codec(self) -> str:
        """Resolve the optimal video codec based on runtime hardware detection."""
        if self._nvenc_supported is None:
            if self.prefer_nvenc:
                self._nvenc_supported = check_nvenc_available()
            else:
                self._nvenc_supported = False
        return "h264_nvenc" if self._nvenc_supported else "libx264"

    def generate_procedural_background(
        self,
        output_path: Path,
        duration_seconds: float,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> Path:
        """Create a procedural, high-definition vertical background without downloading external assets."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        codec = self.video_codec

        # Use an elegant dark minimalist slate gradient with subtle grid geometry
        lavfi_graph = (
            f"color=c=0x0f172a:s={width}x{height}:r={fps}:d={duration_seconds},"
            f"drawgrid=w=120:h=120:t=1:c=0x1e293b@0.4,"
            f"format=yuv420p"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", lavfi_graph,
            "-c:v", codec,
        ]

        if codec == "libx264":
            cmd.extend(["-preset", "veryfast", "-crf", "22"])

        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-t", str(duration_seconds),
            str(output_path),
        ])

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Procedural background generation failed: {res.stderr}")

        return output_path

    def compose_video(
        self,
        background_path: Path,
        audio_path: Path,
        subtitles_path: Optional[Path],
        output_path: Path,
        duration_seconds: float,
    ) -> Path:
        """Compose background, audio narrative, and burned-in subtitles into the final MP4."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        codec = self.video_codec

        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1",
            "-i", str(background_path),
            "-i", str(audio_path),
        ]

        video_filter = ""
        # Handle Windows subtitle path escaping by using a relative path in output directory
        work_dir = output_path.parent
        sub_temp_name = None

        if subtitles_path and subtitles_path.exists():
            # Copy or reference subtitles in work_dir to avoid drive-letter colon escaping bugs on Windows
            sub_temp_path = work_dir / f"temp_{output_path.stem}.ass"
            shutil.copyfile(subtitles_path, sub_temp_path)
            sub_temp_name = sub_temp_path.name
            video_filter = f"ass={sub_temp_name}"

        if video_filter:
            cmd.extend(["-vf", video_filter])

        cmd.extend([
            "-c:v", codec,
        ])

        if codec == "libx264":
            cmd.extend(["-preset", "veryfast", "-crf", "20"])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(duration_seconds),
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_path.name),
        ])

        try:
            res = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg composition failed: {res.stderr}")
        finally:
            if sub_temp_name:
                temp_file = work_dir / sub_temp_name
                if temp_file.exists():
                    temp_file.unlink()

        return output_path

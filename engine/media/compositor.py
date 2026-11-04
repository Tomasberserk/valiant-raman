import logging
from pathlib import Path
import shutil
import subprocess
from typing import Any, Optional

from engine.media.base import Compositor

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        prefer_nvenc: bool = True,
        visual_provider: Optional[Any] = None,
    ):
        self.prefer_nvenc = prefer_nvenc
        self._nvenc_supported: Optional[bool] = None
        if visual_provider is None:
            try:
                from engine.media.visuals import get_default_visual_provider
                self.visual_provider = get_default_visual_provider()
            except ImportError:
                self.visual_provider = None
        else:
            self.visual_provider = visual_provider

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
        topic: str = "",
    ) -> Path:
        """Create a procedural, high-definition vertical background without downloading external assets."""
        if self.visual_provider is not None:
            try:
                return self.visual_provider.generate_background(
                    output_path=output_path,
                    duration_seconds=duration_seconds,
                    topic=topic,
                    width=width,
                    height=height,
                    fps=fps,
                    codec=self.video_codec,
                )
            except Exception:
                pass  # Fall back to builtin lavfi graph below

        output_path.parent.mkdir(parents=True, exist_ok=True)
        codec = self.video_codec

        # Use an elegant dark minimalist slate gradient with subtle grid geometry and dynamic continuous zoom
        lavfi_graph = (
            f"color=c=0x0f172a:s={width}x{height}:r={fps}:d={duration_seconds},"
            f"drawgrid=w=120:h=120:t=1:c=0x1e293b@0.4,"
            f"zoompan=z='min(zoom+0.0006,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps},"
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
        bgm_path: Optional[Path] = None,
        bgm_volume: float = 0.12,
    ) -> Path:
        """Compose background, audio narrative, burned-in subtitles, and optional BGM into the final MP4 with EBU R128 normalization."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        codec = self.video_codec
        work_dir = output_path.parent
        sub_temp_name = None

        # Ensure absolute paths for FFmpeg execution when running in work_dir
        bg_resolved = Path(background_path).resolve()
        audio_resolved = Path(audio_path).resolve()
        bgm_resolved = Path(bgm_path).resolve() if bgm_path is not None else None

        if subtitles_path and subtitles_path.exists():
            # Copy or reference subtitles in work_dir to avoid drive-letter colon escaping bugs on Windows
            sub_temp_path = work_dir / f"temp_{output_path.stem}.ass"
            shutil.copyfile(subtitles_path, sub_temp_path)
            sub_temp_name = sub_temp_path.name

        try:
            # Check if valid BGM audio track is provided
            use_bgm = False
            if bgm_resolved is not None and bgm_resolved.exists() and bgm_resolved.is_file() and bgm_resolved.stat().st_size > 0:
                use_bgm = True

            if use_bgm:
                # 3-input composition: [0:v] bg, [1:a] voice, [2:a] bgm
                cmd_bgm = [
                    "ffmpeg",
                    "-y",
                    "-stream_loop", "-1",
                    "-i", str(bg_resolved),
                    "-i", str(audio_resolved),
                    "-stream_loop", "-1",
                    "-i", str(bgm_resolved),
                ]

                v_filter = f"ass={sub_temp_name}" if sub_temp_name else "null"
                filter_complex = (
                    f"[0:v]{v_filter}[vout];"
                    f"[1:a]volume=1.0[voice];"
                    f"[2:a]volume={bgm_volume:.3f}[bgm];"
                    f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,"
                    f"loudnorm=I=-14:LRA=7:tp=-1.0[aout]"
                )

                cmd_bgm.extend([
                    "-filter_complex", filter_complex,
                    "-map", "[vout]",
                    "-map", "[aout]",
                    "-c:v", codec,
                ])
                if codec == "libx264":
                    cmd_bgm.extend(["-preset", "veryfast", "-crf", "20"])

                cmd_bgm.extend([
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-t", str(duration_seconds),
                    "-pix_fmt", "yuv420p",
                    "-shortest",
                    str(output_path.name),
                ])

                res = subprocess.run(cmd_bgm, cwd=str(work_dir), capture_output=True, text=True)
                if res.returncode == 0:
                    return output_path
                logger.warning(f"BGM audio mix failed: {res.stderr}. Gracefully falling back to voice-only.")

            # Standard voice-only composition (also serves as fallback if BGM failed)
            cmd = [
                "ffmpeg",
                "-y",
                "-stream_loop", "-1",
                "-i", str(bg_resolved),
                "-i", str(audio_resolved),
            ]

            if sub_temp_name:
                cmd.extend(["-vf", f"ass={sub_temp_name}"])

            cmd.extend([
                "-c:v", codec,
            ])
            if codec == "libx264":
                cmd.extend(["-preset", "veryfast", "-crf", "20"])

            cmd.extend([
                "-af", "loudnorm=I=-14:LRA=7:tp=-1.0",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", str(duration_seconds),
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(output_path.name),
            ])

            res = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg composition failed: {res.stderr}")

            return output_path
        finally:
            if sub_temp_name:
                temp_file = work_dir / sub_temp_name
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass

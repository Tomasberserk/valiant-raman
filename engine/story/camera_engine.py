"""Camera Motion Engine (Phase 1 Thin-Slice).

Transforms still images into dynamic 9:16 vertical video shots using smooth,
jitter-free FFmpeg Ken-Burns camera transforms (Push in, Pull out, Pan, Tilt, Static).
Incorporates Claude's anti-jitter upscale pipeline (2160x3840 internal canvas).
"""

import logging
from pathlib import Path
import subprocess

from engine.story.storyboard import CameraMove

logger = logging.getLogger(__name__)


class CameraEngine:
    """Renders smooth 2.5D camera motion onto still images with anti-jitter scaling."""

    @classmethod
    def render_shot_motion(
        cls,
        image_path: Path,
        output_path: Path,
        duration_sec: float,
        camera_move: CameraMove = CameraMove.PUSH_IN,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        codec: str = "libx264",
    ) -> Path:
        """Render a smooth vertical video from an image applying camera motion."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        total_frames = int(duration_sec * fps)

        # Anti-jitter zoompan filter curves
        # Step rate per frame: zoom delta = 0.18 / total_frames
        zoom_step = round(0.18 / max(total_frames, 1), 5)

        if camera_move == CameraMove.PUSH_IN:
            # Smoothly zoom into the center from 1.0 to 1.18
            zoompan_expr = (
                f"zoompan=z='min(zoom+{zoom_step},1.18)':"
                f"x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif camera_move == CameraMove.PULL_OUT:
            # Start zoomed at 1.18 and pull back to 1.0
            zoompan_expr = (
                f"zoompan=z='max(1.18-{zoom_step}*on,1.0)':"
                f"x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif camera_move == CameraMove.PAN_LEFT:
            # Zoom slightly and pan from right to left
            pan_step = round(200.0 / max(total_frames, 1), 2)
            zoompan_expr = (
                f"zoompan=z=1.15:"
                f"x='min(iw-(iw/zoom), (iw/2-(iw/zoom/2)) + {pan_step}*on)':"
                f"y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif camera_move == CameraMove.PAN_RIGHT:
            # Zoom slightly and pan from left to right
            pan_step = round(200.0 / max(total_frames, 1), 2)
            zoompan_expr = (
                f"zoompan=z=1.15:"
                f"x='max(0, (iw/2-(iw/zoom/2)) - {pan_step}*on)':"
                f"y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif camera_move == CameraMove.TILT_UP:
            # Zoom slightly and tilt camera upwards
            tilt_step = round(250.0 / max(total_frames, 1), 2)
            zoompan_expr = (
                f"zoompan=z=1.15:"
                f"x='iw/2-(iw/zoom/2)':"
                f"y='min(ih-(ih/zoom), (ih/2-(ih/zoom/2)) + {tilt_step}*on)':"
                f"d={total_frames}:s={width}x{height}:fps={fps}"
            )
        else:  # STATIC
            zoompan_expr = f"zoompan=z=1.0:x=0:y=0:d={total_frames}:s={width}x{height}:fps={fps}"

        # 2x internal canvas upscale (2160x3840) to eradicate subpixel jitter, then zoompan to 1080x1920
        vf_pipeline = (
            f"scale=2160:3840:force_original_aspect_ratio=increase,"
            f"crop=2160:3840,"
            f"{zoompan_expr},"
            f"format=yuv420p"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-t", str(duration_sec),
            "-vf", vf_pipeline,
            "-an",
            "-c:v", codec,
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            logger.error(f"Camera motion rendering failed: {res.stderr}")
            raise RuntimeError(f"FFmpeg camera motion rendering failed: {res.stderr}")

        return output_path

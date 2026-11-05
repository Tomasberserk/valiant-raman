"""Mock Visual Renderer (Phase 1 Thin-Slice).

Generates high-contrast vertical canvas keyframes with shot metadata overlays,
and renders smooth camera motion clips. Enables 100% offline testing of the complete
timeline, shot assembly, audio ducking, and FSM lifecycle without consuming cloud API credits.
"""

import hashlib
import logging
from pathlib import Path
import subprocess
from typing import List, Optional

from engine.story.camera_engine import CameraEngine
from engine.story.storyboard import (
    CharacterAnchor,
    RenderTier,
    ShotRenderResult,
    StyleBible,
    VisualShot,
)

logger = logging.getLogger(__name__)


class MockVisualRenderer:
    """Offline test renderer producing diagnostic 9:16 keyframes and camera-animated video shots."""

    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir is None:
            from config.settings import STORAGE_DIR
            self.output_dir = STORAGE_DIR / "thin_slice_shots"
        else:
            self.output_dir = Path(output_dir)

    def render_shot(
        self,
        shot: VisualShot,
        style_bible: StyleBible,
        characters: list[CharacterAnchor],
        scene_id: str = "scene_01",
    ) -> ShotRenderResult:
        """Render a single atomic VisualShot into a keyframe image and camera-animated MP4."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        shot_hash = hashlib.sha256(
            f"{shot.shot_id}_{shot.action_prompt_en}_{shot.duration_sec}".encode()
        ).hexdigest()[:12]

        image_path = self.output_dir / f"{scene_id}_{shot.shot_id}_{shot_hash}.png"
        video_path = self.output_dir / f"{scene_id}_{shot.shot_id}_{shot_hash}.mp4"

        # 1. Generate diagnostic keyframe via FFmpeg lavfi canvas
        # Alternate background palette tones across shots
        palette = style_bible.color_palette or ["#07090E", "#1E1035", "#0E1E2E"]
        bg_color = palette[abs(hash(shot.shot_id)) % len(palette)].replace("#", "0x")

        title_text = f"SHOT: {shot.shot_id.upper()} | {shot.camera_move.value.upper()}"
        action_clean = shot.action_prompt_en[:80].replace("'", "").replace(":", "-")

        vf_canvas = (
            f"color=c={bg_color}:s=1080x1920:r=1:d=1,"
            f"drawbox=x=40:y=40:w=1000:h=1840:color=white@0.15:t=2,"
            f"drawtext=text='{title_text}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=200,"
            f"drawtext=text='DUR: {shot.duration_sec:.1f}s | TIER: {shot.preferred_tier.value}':fontcolor=yellow:fontsize=36:x=(w-text_w)/2:y=280,"
            f"drawtext=text='{action_clean}':fontcolor=cyan:fontsize=32:x=(w-text_w)/2:y=500"
        )

        cmd_img = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", vf_canvas,
            "-frames:v", "1",
            str(image_path),
        ]
        res_img = subprocess.run(cmd_img, capture_output=True, text=True)
        if res_img.returncode != 0:
            # Fallback simple solid color without text if font rendering issues occur
            cmd_img_simple = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"color=c={bg_color}:s=1080x1920:r=1:d=1",
                "-frames:v", "1", str(image_path)
            ]
            subprocess.run(cmd_img_simple, check=True)

        # 2. Animate camera motion on the keyframe
        CameraEngine.render_shot_motion(
            image_path=image_path,
            output_path=video_path,
            duration_sec=shot.duration_sec,
            camera_move=shot.camera_move,
            width=1080,
            height=1920,
            fps=30,
        )

        return ShotRenderResult(
            shot_id=shot.shot_id,
            image_path=str(image_path),
            video_path=str(video_path),
            duration_seconds=shot.duration_sec,
            width=1080,
            height=1920,
            fps=30.0,
            provider_name="MockVisualRenderer",
            model_version="1.0-thin-slice",
            render_tier=shot.preferred_tier,
            cache_hash=shot_hash,
            qa_passed=True,
        )

"""Visual Orchestrator: Drives multi-shot visual asset generation and camera motion.

Coordinates:
1. Prompt composition per VisualShot (anchoring characters and StyleBible).
2. Keyframe generation via ImageProvider with disk-backed caching.
3. 2.5D Ken-Burns camera motion rendering via CameraEngine.
4. Production of canonical ShotRenderResult records.
"""

import logging
from pathlib import Path
from typing import List, Optional

from engine.story.camera_engine import CameraEngine
from engine.story.storyboard import ShotRenderResult, Storyboard, VisualShot
from engine.visual.cache import VisualAssetCache
from engine.visual.providers import ImageProvider, MockImageProvider

logger = logging.getLogger(__name__)


class VisualOrchestrator:
    """Orchestrates asset generation and camera animation across all shots of a Storyboard."""

    def __init__(
        self,
        image_provider: Optional[ImageProvider] = None,
        cache: Optional[VisualAssetCache] = None,
    ):
        self.image_provider = image_provider or MockImageProvider()
        self.cache = cache or VisualAssetCache()

    def orchestrate_storyboard(
        self,
        storyboard: Storyboard,
        output_dir: Path,
        fps: int = 30,
        width: int = 1080,
        height: int = 1920,
    ) -> List[ShotRenderResult]:
        """Render all shots defined in the Storyboard into animated video clips.

        Returns a list of ShotRenderResult records containing the paths to both
        the still keyframe and the rendered video file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        shots_dir = output_dir / "shots"
        keyframes_dir = output_dir / "keyframes"
        shots_dir.mkdir(parents=True, exist_ok=True)
        keyframes_dir.mkdir(parents=True, exist_ok=True)

        results: List[ShotRenderResult] = []

        total_shots = sum(len(scene.shots) for scene in storyboard.scenes)
        logger.info(
            f"Orchestrating {total_shots} shots across {len(storyboard.scenes)} scenes for storyboard {storyboard.id}"
        )

        for scene in storyboard.scenes:
            for shot in scene.shots:
                shot_result = self.render_shot(
                    shot=shot,
                    storyboard=storyboard,
                    keyframes_dir=keyframes_dir,
                    shots_dir=shots_dir,
                    fps=fps,
                    width=width,
                    height=height,
                )
                results.append(shot_result)

        logger.info(f"Successfully rendered all {len(results)} shots for storyboard {storyboard.id}")
        return results

    def render_shot(
        self,
        shot: VisualShot,
        storyboard: Storyboard,
        keyframes_dir: Path,
        shots_dir: Path,
        fps: int = 30,
        width: int = 1080,
        height: int = 1920,
    ) -> ShotRenderResult:
        """Render a single VisualShot into a keyframe and animated MP4 clip."""
        # 1. Compose full action prompt with style bible and character anchors
        full_prompt = shot.compose_full_prompt(
            style_bible=storyboard.style_bible,
            characters=storyboard.characters,
        )
        negative_prompt = storyboard.style_bible.negative_global

        provider_name = self.image_provider.__class__.__name__
        shot_hash = self.cache.compute_shot_hash(
            prompt=full_prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            provider_name=provider_name,
        )

        keyframe_path = keyframes_dir / f"{shot.shot_id}.png"
        video_path = shots_dir / f"{shot.shot_id}.mp4"

        # 2. Check cache or generate keyframe
        cached_img = self.cache.get_cached_keyframe(shot_hash)
        if cached_img and cached_img.exists():
            keyframe_path.write_bytes(cached_img.read_bytes())
        else:
            self.image_provider.generate_keyframe(
                prompt=full_prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                output_path=keyframe_path,
            )
            self.cache.store_cached_keyframe(shot_hash, keyframe_path)

        # 3. Render camera motion
        CameraEngine.render_shot_motion(
            image_path=keyframe_path,
            output_path=video_path,
            duration_sec=shot.duration_sec,
            camera_move=shot.camera_move,
            width=width,
            height=height,
            fps=fps,
        )

        return ShotRenderResult(
            shot_id=shot.shot_id,
            image_path=str(keyframe_path),
            video_path=str(video_path),
            duration_seconds=shot.duration_sec,
            width=width,
            height=height,
            fps=float(fps),
            provider_name=provider_name,
            model_version="1.0",
            render_tier=shot.preferred_tier,
            cache_hash=shot_hash,
            qa_passed=True,
        )

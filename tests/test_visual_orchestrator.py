"""Tests for Phase 2 Visual Orchestrator, Providers, and Asset Cache."""

from pathlib import Path
import pytest
from PIL import Image

from engine.story.storyboard import (
    AudioTrackPlan,
    BeatRole,
    CameraMove,
    CharacterAnchor,
    RenderTier,
    ResolvedContentMode,
    Scene,
    Storyboard,
    StyleBible,
    VisualShot,
)
from engine.story.storyboard_planner import StoryboardPlanner
from engine.visual.cache import VisualAssetCache
from engine.visual.orchestrator import VisualOrchestrator
from engine.visual.providers import (
    MockImageProvider,
    OpenAIImageProvider,
    ProceduralCanvasProvider,
    ProviderUnavailableError,
)


def test_mock_image_provider_generates_valid_keyframe(tmp_path: Path):
    provider = MockImageProvider(watermark_text="TEST KEYFRAME")
    out_file = tmp_path / "test_shot.png"

    res = provider.generate_keyframe(
        prompt="A lone hero gripping a celestial sword in a dark rainy forest",
        negative_prompt="blurry, ugly",
        width=540,
        height=960,
        seed=42,
        output_path=out_file,
    )

    assert res.exists()
    assert res.stat().st_size > 0
    with Image.open(res) as img:
        assert img.size == (540, 960)
        assert img.format == "PNG"


def test_procedural_canvas_provider(tmp_path: Path):
    provider = ProceduralCanvasProvider()
    out_file = tmp_path / "proc_shot.png"

    res = provider.generate_keyframe(
        prompt="Cosmic nebula with glowing stars",
        width=540,
        height=960,
        output_path=out_file,
    )

    assert res.exists()
    assert res.stat().st_size > 0


def test_openai_provider_fails_loud_without_key():
    provider = OpenAIImageProvider(api_key=None)
    with pytest.raises(ProviderUnavailableError, match="requires OPENAI_API_KEY"):
        provider.generate_keyframe(prompt="A mystical sword")


def test_visual_asset_cache(tmp_path: Path):
    cache = VisualAssetCache(cache_dir=tmp_path / "cache")
    shot_hash = cache.compute_shot_hash(
        prompt="Hero with sword",
        negative_prompt="",
        width=1080,
        height=1920,
    )

    # Cache miss
    assert cache.get_cached_keyframe(shot_hash) is None

    # Create dummy source and store
    src_file = tmp_path / "source.png"
    src_file.write_bytes(b"dummy_png_bytes_content")
    stored = cache.store_cached_keyframe(shot_hash, src_file)

    # Cache hit
    hit = cache.get_cached_keyframe(shot_hash)
    assert hit is not None
    assert hit.exists()
    assert hit.read_bytes() == b"dummy_png_bytes_content"


def test_visual_orchestrator_renders_storyboard(tmp_path: Path):
    planner = StoryboardPlanner()
    storyboard = planner.plan_storyboard(
        raw_prompt="un chico encuentra una espada sagrada en un bosque oscuro y relámpagos",
        target_duration_sec=25.0,
    )

    orchestrator = VisualOrchestrator(
        image_provider=MockImageProvider(),
        cache=VisualAssetCache(tmp_path / "cache"),
    )

    results = orchestrator.orchestrate_storyboard(
        storyboard=storyboard,
        output_dir=tmp_path / "render_out",
        width=540,
        height=960,
        fps=24,
    )

    assert len(results) >= 6
    for r in results:
        assert Path(r.image_path).exists()
        assert Path(r.video_path).exists()
        assert r.duration_seconds >= 2.0
        assert r.qa_passed is True

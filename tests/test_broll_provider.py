"""Unit tests for Stage 11 Thematic B-Roll Visual Provider."""

import os
from pathlib import Path
import pytest

from engine.media.visuals import (
    ThematicBrollVisualProvider,
    ProceduralVisualProvider,
    LocalAssetVisualProvider,
    get_default_visual_provider,
)


def test_category_detection_tech():
    """Test 1: Tech keywords map to 'tech' category."""
    for phrase in ["Inteligencia artificial y algoritmos", "New software AI technology", "Aprender a programar"]:
        assert ThematicBrollVisualProvider.detect_category(phrase) == "tech"


def test_category_detection_space():
    """Test 2: Space keywords map to 'space' category."""
    for phrase in ["El universo y las galaxias", "NASA deep space exploration", "Telescopio James Webb"]:
        assert ThematicBrollVisualProvider.detect_category(phrase) == "space"


def test_category_detection_history():
    """Test 3: History keywords map to 'history' category."""
    for phrase in ["El imperio romano antiguo", "Misterios de la historia antigua", "Guerra y civilizaciones"]:
        assert ThematicBrollVisualProvider.detect_category(phrase) == "history"


def test_category_detection_nature():
    """Test 4: Nature keywords map to 'nature' category."""
    for phrase in ["Animales de la selva y el oceano", "Climate and earth nature", "Fauna salvaje"]:
        assert ThematicBrollVisualProvider.detect_category(phrase) == "nature"


def test_category_detection_general_fallback():
    """Test 5: Unrecognized phrases fall back to 'general'."""
    for phrase in ["Algo completamente aleatorio", "Xyz 123", "Reflexiones cotidianas"]:
        assert ThematicBrollVisualProvider.detect_category(phrase) == "general"


def test_empty_folder_falls_back_to_procedural(tmp_path: Path):
    """Test 6 & 7: Empty assets folder transparently renders procedural background without exception."""
    empty_broll_dir = tmp_path / "empty_broll"
    empty_broll_dir.mkdir(parents=True)

    provider = ThematicBrollVisualProvider(assets_dir=empty_broll_dir)
    out_video = tmp_path / "bg_fallback.mp4"

    # Must complete without error (generating a 1.0 second procedural test clip)
    result = provider.generate_background(
        output_path=out_video,
        duration_seconds=1.0,
        topic="Universo y estrellas",
        width=360,
        height=640,
        fps=24,
    )
    assert result.exists()
    assert result.stat().st_size > 0


def test_visual_provider_env_resolution_broll(monkeypatch):
    """Test 8: VISUAL_PROVIDER=broll resolves to ThematicBrollVisualProvider."""
    monkeypatch.setenv("VISUAL_PROVIDER", "broll")
    provider = get_default_visual_provider()
    assert isinstance(provider, ThematicBrollVisualProvider)


def test_visual_provider_env_resolution_local(monkeypatch):
    """Test 9: VISUAL_PROVIDER=local resolves to ThematicBrollVisualProvider / LocalAssetVisualProvider."""
    monkeypatch.setenv("VISUAL_PROVIDER", "local")
    provider = get_default_visual_provider()
    assert isinstance(provider, ThematicBrollVisualProvider)


def test_visual_provider_env_resolution_procedural(monkeypatch):
    """VISUAL_PROVIDER=procedural resolves to ProceduralVisualProvider."""
    monkeypatch.setenv("VISUAL_PROVIDER", "procedural")
    provider = get_default_visual_provider()
    assert isinstance(provider, ProceduralVisualProvider)


def test_single_clip_broll_assembly(tmp_path: Path):
    """Test 10: When a valid clip exists, it is loaded, looped and scaled to 9:16 target."""
    broll_dir = tmp_path / "broll"
    tech_dir = broll_dir / "tech"
    tech_dir.mkdir(parents=True)

    # Generate a small 1-second sample clip in tech folder
    sample_clip = tech_dir / "sample_tech.mp4"
    procedural = ProceduralVisualProvider()
    procedural.generate_background(
        output_path=sample_clip,
        duration_seconds=1.0,
        topic="tecnologia",
        width=360,
        height=640,
        fps=24,
    )

    provider = ThematicBrollVisualProvider(assets_dir=broll_dir)
    out_video = tmp_path / "assembled_broll.mp4"

    result = provider.generate_background(
        output_path=out_video,
        duration_seconds=2.0,
        topic="Inteligencia artificial",
        width=360,
        height=640,
        fps=24,
    )
    assert result.exists()
    assert result.stat().st_size > 0

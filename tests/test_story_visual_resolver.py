"""Unit tests for Visual Resolver & Asset Ladder (Stage 12B.2).

Validates:
1. AssetCatalog indexing, provenance, and licensing metadata.
2. Strict priority of prohibited_mismatches filter over scoring.
3. Prohibited candidate rejection logging in rejection_reasons.
4. Tier 1 Exact Match resolution.
5. Tier 2 Thematic B-Roll resolution.
6. Tier 3 Kinetic Motion (still image + ken_burns strategy) resolution.
7. Tier 4 Styled Fallback decision (decision only, zero rendering).
8. Deterministic reproducibility across multiple resolver executions.
9. Full Golden Case visual resolution with synthetic fixtures across all 5 scenes.
"""

from pathlib import Path
import pytest

from engine.story import (
    AssetCatalog,
    ContinuityRequirement,
    ResolutionTier,
    Scene,
    StoryArchitect,
    VisualAssetMetadata,
    VisualBrief,
    VisualProductionStrategy,
    VisualResolutionResult,
    VisualResolver,
)


@pytest.fixture
def empty_catalog() -> AssetCatalog:
    return AssetCatalog()


@pytest.fixture
def sample_catalog() -> AssetCatalog:
    cat = AssetCatalog()
    # 1. Patent Motorwagen 1886 (Tier 1 candidate for scene 1)
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_benz_1886_video",
            path=Path("storage/fixtures/benz_1886.mp4"),
            type="video",
            era="1886",
            visual_period="Pioneering Automotive (1886-1890)",
            tags=["Benz Patent-Motorwagen 1886", "first car", "motor carriage", "tricycle", "1886"],
            description="Carruaje motorizado de tres ruedas rudimentario avanzando despacio por calle adoquinada.",
            aspect_ratio="9:16",
            width=1080,
            height=1920,
            duration_sec=8.5,
            source="Mercedes-Benz Classic Archive",
            license="Public Domain / Educational",
            provenance="Archive accession #1886-MB-001",
        )
    )
    # 2. Bertha Benz historic journey (Tier 3 image candidate)
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_bertha_1888_image",
            path=Path("storage/fixtures/bertha_1888.jpg"),
            type="image",
            era="1888",
            visual_period="Pioneering Automotive",
            tags=["Bertha Benz historic journey", "Wiesloch pharmacy 1888", "antique car country road"],
            description="Fotografía de época de Bertha Benz con sus hijos en el Patent-Motorwagen frente a una botica.",
            aspect_ratio="9:16",
            width=1080,
            height=1920,
            source="Wiesloch Historic Archive",
            license="CC-BY-SA",
            provenance="Baden-Württemberg Historical Society",
        )
    )
    # 3. Vintage factory generic B-Roll (Tier 2 video candidate)
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_factory_1915_thematic",
            path=Path("storage/fixtures/vintage_factory.mp4"),
            type="video",
            era="1913-1915",
            visual_period="Early Industrial Mass Production",
            tags=["vintage car production", "moving assembly line", "industrial factory"],
            description="Nave industrial con correas de transmisión y obreros ensamblando maquinaria.",
            aspect_ratio="9:16",
            width=1080,
            height=1920,
            duration_sec=12.0,
            source="Library of Congress",
            license="Public Domain",
        )
    )
    # 4. Modern supercar (Prohibited trap for historical scenes!)
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_modern_ferrari",
            path=Path("storage/fixtures/modern_ferrari.mp4"),
            type="video",
            era="2024",
            visual_period="Modern Contemporary",
            tags=["car", "automóviles modernos con cuatro ruedas de caucho sintético", "asfalto contemporáneo", "fast"],
            description="Automóvil moderno de alta gama circulando sobre asfalto contemporáneo con líneas pintadas.",
            aspect_ratio="9:16",
            width=1080,
            height=1920,
            duration_sec=6.0,
            source="Contemporary Stock",
            license="Royalty-Free",
        )
    )
    return cat


def test_asset_catalog_indexing():
    """Verify AssetCatalog registers, retrieves, and sorts assets deterministically."""
    cat = AssetCatalog()
    assert len(cat.list_assets()) == 0

    asset = VisualAssetMetadata(
        asset_id="asset_test_01",
        path=Path("storage/test.mp4"),
        type="video",
        era="1900",
        tags=["vintage", "steam"],
        description="Steam engine test",
        source="Test Source",
        license="CC0",
        provenance="Test Collection #1",
    )
    cat.add_asset(asset)

    retrieved = cat.get_asset("asset_test_01")
    assert retrieved is not None
    assert retrieved.license == "CC0"
    assert retrieved.provenance == "Test Collection #1"
    assert len(cat.list_assets()) == 1


def test_prohibited_mismatch_filtering(sample_catalog):
    """Verify assets with prohibited elements are filtered out and reasons recorded."""
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")
    scene_01 = story.scenes[0]  # Era 1886, prohibited: "automóviles modernos...", "asfalto contemporáneo..."

    resolver = VisualResolver()
    result = resolver.resolve_scene(scene_01, sample_catalog)

    # Modern Ferrari contains prohibited tags
    assert "asset_modern_ferrari" in result.rejected_candidates
    assert "asset_modern_ferrari" in result.rejection_reasons
    assert any("prohibited:" in r for r in result.rejection_reasons["asset_modern_ferrari"])


def test_prohibited_mismatch_has_priority_over_high_score():
    """Mandatory Audit Check: Prohibited element MUST cause rejection before scoring."""
    cat = AssetCatalog()

    # Asset with 100% keyword match but an explicit prohibited element in tags
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_trap_high_score",
            path=Path("storage/trap.mp4"),
            type="video",
            era="1886",
            tags=["Benz Patent-Motorwagen 1886", "first motor carriage", "asfalto contemporáneo con líneas pintadas"],
            description="Carruaje antiguo 1886 rodando sobre asfalto contemporáneo con líneas pintadas.",
            source="Trap Source",
            license="Royalty-Free",
        )
    )

    brief = VisualBrief(
        subject="Carruaje motorizado de tres ruedas",
        era="1886",
        environment="Calle adoquinada de época",
        action="Vehículo avanzando",
        mood="Histórico",
        search_keywords=["Benz Patent-Motorwagen 1886", "first motor carriage"],
        prohibited_mismatches=["asfalto contemporáneo con líneas pintadas"],
    )

    scene = Scene(
        id="scene_trap_test",
        scene_index=0,
        narrative_role="hook",
        script_text="Test narration",
        word_count=2,
        estimated_duration_sec=0.8,
        visual_brief=brief,
    )

    resolver = VisualResolver()
    result = resolver.resolve_scene(scene, cat)

    # It must be rejected despite perfect keywords, triggering Tier 4 fallback
    assert result.tier == ResolutionTier.TIER4_STYLED_FALLBACK
    assert "asset_trap_high_score" in result.rejected_candidates
    assert "asset_trap_high_score" in result.rejection_reasons
    assert any("asfalto contemporáneo" in r for r in result.rejection_reasons["asset_trap_high_score"])


def test_tier1_exact_match_resolution(sample_catalog):
    """Verify curated exact match resolves to Tier 1 with passthrough strategy."""
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")
    scene_01 = story.scenes[0]  # Benz Patent-Motorwagen 1886

    resolver = VisualResolver()
    result = resolver.resolve_scene(scene_01, sample_catalog)

    assert result.tier == ResolutionTier.TIER1_EXACT
    assert result.asset_path == Path("storage/fixtures/benz_1886.mp4")
    assert result.production_strategy == VisualProductionStrategy.PASSTHROUGH.value
    assert result.score >= 0.75
    assert scene_01.resolution_tier == "tier1_exact"
    assert scene_01.resolved_asset_path == Path("storage/fixtures/benz_1886.mp4")


def test_tier2_thematic_broll_resolution(sample_catalog):
    """Verify compatible video asset resolves to Tier 2 Thematic B-Roll."""
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")
    scene_03 = story.scenes[2]  # Assembly line 1913-1915

    resolver = VisualResolver()
    result = resolver.resolve_scene(scene_03, sample_catalog)

    assert result.tier == ResolutionTier.TIER2_THEMATIC
    assert result.asset_path == Path("storage/fixtures/vintage_factory.mp4")
    assert result.production_strategy == VisualProductionStrategy.PASSTHROUGH.value
    assert result.score >= 0.50


def test_tier3_kinetic_motion_resolution(sample_catalog):
    """Verify still image resolves to Tier 3 Kinetic Motion with ken_burns strategy."""
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")
    scene_02 = story.scenes[1]  # Bertha Benz 1888

    resolver = VisualResolver()
    result = resolver.resolve_scene(scene_02, sample_catalog)

    assert result.tier == ResolutionTier.TIER3_KINETIC_MOTION
    assert result.asset_path == Path("storage/fixtures/bertha_1888.jpg")
    assert result.production_strategy == VisualProductionStrategy.KEN_BURNS.value
    assert result.score >= 0.50


def test_tier4_styled_fallback_decision(empty_catalog):
    """Verify empty catalog yields Tier 4 decision without attempting to render."""
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")
    scene_01 = story.scenes[0]

    resolver = VisualResolver()
    result = resolver.resolve_scene(scene_01, empty_catalog)

    assert result.tier == ResolutionTier.TIER4_STYLED_FALLBACK
    assert result.asset_path is None
    assert result.production_strategy == VisualProductionStrategy.STYLED_CINEMATIC.value
    assert result.score == 0.0
    assert "styled cinematic" in result.rationale.lower()
    assert scene_01.resolution_tier == "tier4_styled_fallback"
    assert scene_01.resolved_asset_path is None


def test_visual_resolver_determinism(sample_catalog):
    """Mandatory Audit Check: Resolver must be 100% deterministic on identical input."""
    architect = StoryArchitect()
    story1 = architect.synthesize_story("La evolución del automóvil")
    story2 = architect.synthesize_story("La evolución del automóvil")

    resolver = VisualResolver()
    res1 = resolver.resolve_scene(story1.scenes[0], sample_catalog)
    res2 = resolver.resolve_scene(story2.scenes[0], sample_catalog)

    assert res1.tier == res2.tier
    assert res1.asset_path == res2.asset_path
    assert res1.production_strategy == res2.production_strategy
    assert res1.score == res2.score
    assert res1.rationale == res2.rationale
    assert res1.rejected_candidates == res2.rejected_candidates
    assert res1.rejection_reasons == res2.rejection_reasons


def test_golden_case_visual_resolution_with_fixtures():
    """Verify all 5 scenes of the automotive Golden Case are resolved against controlled fixtures."""
    cat = AssetCatalog()
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_s1",
            path=Path("storage/fixtures/patent_motorwagen.mp4"),
            type="video",
            era="1886",
            tags=["Benz Patent-Motorwagen 1886", "first motor carriage", "19th century street"],
            description="Carruaje motorizado de tres ruedas de 1886 en calle adoquinada con bruma matinal.",
        )
    )
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_s2",
            path=Path("storage/fixtures/bertha_benz.mp4"),
            type="video",
            era="1888",
            tags=["Bertha Benz historic journey", "Wiesloch pharmacy 1888", "antique car country road"],
            description="Bertha Benz conduciendo en camino rural entre Mannheim y Pforzheim en 1888.",
        )
    )
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_s3",
            path=Path("storage/fixtures/ford_assembly.mp4"),
            type="video",
            era="1913-1915",
            tags=["Ford Model T moving assembly line", "Highland Park 1913 factory", "vintage car production"],
            description="Línea de ensamblaje móvil del Modelo T en planta industrial de Highland Park.",
        )
    )
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_s4",
            path=Path("storage/fixtures/auto_ecu.mp4"),
            type="video",
            era="1980-2010",
            tags=["automotive ECU microchip", "car telemetry sensor testing", "modern car engineering"],
            description="Transición electrónica de tableros y microchips en laboratorio de telemetría automotriz.",
        )
    )
    cat.add_asset(
        VisualAssetMetadata(
            asset_id="asset_s5",
            path=Path("storage/fixtures/lidar_autonomous.mp4"),
            type="video",
            era="Presente",
            tags=["autonomous vehicle night city", "lidar point cloud drive", "smart mobility street"],
            description="Vehículo autónomo navegando avenida nocturna con nube de puntos LiDAR y visualización sensorial.",
        )
    )

    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")

    resolver = VisualResolver()
    results = resolver.resolve_story(story, cat)

    assert len(results) == 5
    # Every scene should achieve Tier 1 or Tier 2
    for r in results:
        assert r.tier in (ResolutionTier.TIER1_EXACT, ResolutionTier.TIER2_THEMATIC)
        assert r.asset_path is not None
        assert r.production_strategy == "passthrough"
        assert r.score >= 0.70

    # Ensure scenes were properly updated
    assert all(scene.resolved_asset_path is not None for scene in story.scenes)
    assert all(scene.resolution_tier in ("tier1_exact", "tier2_thematic") for scene in story.scenes)

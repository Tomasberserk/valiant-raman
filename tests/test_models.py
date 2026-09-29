"""Unit tests for Phase A: database models, relationships, and provenance constraints."""

import pytest
from engine.experiments.repository import ExperimentRepository


@pytest.fixture
def repo():
    """Create an isolated in-memory SQLite database repository."""
    repository = ExperimentRepository(db_url="sqlite:///:memory:")
    repository.init_db()
    return repository


def test_experiment_creation(repo):
    """Verify creating an experiment and retrieving it."""
    exp = repo.create_experiment(
        name="Hook Optimization Test",
        description="Testing question vs statement hooks on science trivia",
    )
    assert exp.id is not None
    assert exp.name == "Hook Optimization Test"
    assert exp.status == "active"


def test_hypothesis_and_variants(repo):
    """Verify linking hypotheses and variants to an experiment."""
    exp = repo.create_experiment("Retention Test", "Comparing 3 hook types")

    hyp = repo.create_hypothesis(
        experiment_id=exp.id,
        statement="A question hook increases 3s retention by 20% over a statement",
        independent_variable="hook_type",
        primary_metric="retention_at_3s",
        success_criterion="retention_at_3s > 0.65",
        baseline_description="Statement hook averages 0.45 retention",
    )

    assert hyp.experiment_id == exp.id

    var_a = repo.create_variant(
        hypothesis_id=hyp.id,
        name="Question Hook",
        variant_code="A",
        hook_type="QUESTION",
        parameters={"speed": 1.0, "pitch": "medium"},
    )
    var_b = repo.create_variant(
        hypothesis_id=hyp.id,
        name="Statement Hook",
        variant_code="B",
        hook_type="STATEMENT",
    )

    assert var_a.variant_code == "A"
    assert var_a.get_parameters()["speed"] == 1.0
    assert var_b.variant_code == "B"

    fetched_exp = repo.get_experiment(exp.id)
    assert len(fetched_exp.hypotheses) == 1
    assert len(fetched_exp.hypotheses[0].variants) == 2


def test_asset_provenance_enforcement(repo):
    """Asset registration MUST reject assets without clear source, license, or creator."""
    with pytest.raises(ValueError, match="Asset source is required"):
        repo.register_asset(
            asset_type="video",
            source="",
            license_name="CC-BY-4.0",
            creator="Alice",
        )

    with pytest.raises(ValueError, match="Asset license is required"):
        repo.register_asset(
            asset_type="video",
            source="procedural_generator_v1",
            license_name="  ",
            creator="Alice",
        )

    with pytest.raises(ValueError, match="Asset creator is required"):
        repo.register_asset(
            asset_type="video",
            source="procedural_generator_v1",
            license_name="CC0",
            creator="",
        )

    valid_asset = repo.register_asset(
        asset_type="video",
        source="internal_procedural_gradient",
        license_name="Proprietary-Internal",
        creator="Valiant Engine",
        allowed_platforms="all",
        attribution_required=False,
    )
    assert valid_asset.id is not None
    assert valid_asset.creator == "Valiant Engine"


def test_render_and_asset_association(repo):
    """Verify render registration, linking assets via RenderAsset, and publication/metrics."""
    exp = repo.create_experiment("E2E Test", "Test render workflow")
    hyp = repo.create_hypothesis(
        exp.id, "Hypothesis 1", "hook", "views", "views > 100", "baseline"
    )
    var_a = repo.create_variant(hyp.id, "Variant A", "A", "QUESTION")

    run = repo.create_run(
        experiment_id=exp.id,
        pipeline_version="0.1.0-mvp",
        config_hash="abc123hash",
    )
    assert run.status == "running"

    asset = repo.register_asset(
        asset_type="audio",
        source="edge-tts/es-MX-JorgeNeural",
        license_name="Microsoft Azure Cognitive Services ToS",
        creator="Microsoft",
    )

    render = repo.register_render(
        experiment_run_id=run.id,
        variant_id=var_a.id,
        file_path="/storage/output/variant_a.mp4",
        duration_seconds=32.5,
        width=1080,
        height=1920,
        fps=30.0,
        codec="h264",
        file_size_bytes=1024000,
        render_time_seconds=2.8,
        qa_passed=True,
        qa_report={"checks": [{"name": "resolution", "passed": True}]},
    )

    repo.link_asset_to_render(render_id=render.id, asset_id=asset.id, role="voiceover")
    repo.complete_run(run.id, status="completed")

    pub = repo.register_publication(render_id=render.id, platform="youtube_shorts")
    metric = repo.record_metric(
        publication_id=pub.id,
        views=1500,
        retention_at_3s=0.72,
        completion_rate=0.48,
    )

    assert metric.views == 1500
    assert metric.retention_at_3s == 0.72

    # Verify run completion
    fetched_run = repo.get_run(run.id)
    assert fetched_run.status == "completed"
    assert len(fetched_run.renders) == 1
    assert fetched_run.renders[0].qa_passed is True

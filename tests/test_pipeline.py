"""Unit tests for Phase F: end-to-end pipeline execution, rendering, QA, and provenance."""

from pathlib import Path
import pytest

from engine.experiments.repository import ExperimentRepository
from engine.media.compositor import FFmpegCompositor
from engine.media.transcription import DummyTranscriptionProvider
from engine.media.voice import DummyVoiceProvider
from engine.pipeline import ContentEnginePipeline
from engine.qa.validator import MediaValidator
from engine.scripting.schema import HookType, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider


@pytest.fixture
def test_setup(tmp_path: Path):
    """Setup isolated repository and output directory for pipeline test."""
    db_file = tmp_path / "test_pipeline.db"
    repo = ExperimentRepository(db_url=f"sqlite:///{db_file.as_posix()}")
    repo.init_db()

    pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=DummyScriptProvider(),
        voice_provider=DummyVoiceProvider(words_per_minute=200),
        transcription_provider=DummyTranscriptionProvider(),
        compositor=FFmpegCompositor(prefer_nvenc=False),
        validator=MediaValidator(expected_width=1080, expected_height=1920, duration_tolerance_sec=4.0),
    )
    return repo, pipeline, tmp_path


def test_full_pipeline_run_three_variants(test_setup):
    """Execute complete deterministic pipeline generating 3 variants without external network."""
    repo, pipeline, tmp_path = test_setup

    exp = repo.create_experiment(
        name="Offline Demo Experiment",
        description="Testing deterministic offline variant generation",
    )

    hyp = repo.create_hypothesis(
        experiment_id=exp.id,
        statement="Question hooks generate higher 3s retention than statements or surprises",
        independent_variable="hook_type",
        primary_metric="retention_at_3s",
        success_criterion="retention_at_3s > 0.60",
        baseline_description="Standard baseline is 0.40",
    )

    plans = [
        VariantPlan(variant_code="A", hook_type=HookType.QUESTION, target_duration_sec=3.0, topic="el Universo"),
        VariantPlan(variant_code="B", hook_type=HookType.STATEMENT, target_duration_sec=3.0, topic="el Universo"),
        VariantPlan(variant_code="C", hook_type=HookType.SURPRISE, target_duration_sec=3.0, topic="el Universo"),
    ]

    out_dir = tmp_path / "renders"
    result = pipeline.run_experiment_variants(
        experiment_id=exp.id,
        hypothesis_id=hyp.id,
        variant_plans=plans,
        output_dir=out_dir,
    )

    # 1. Run status verification
    assert result.run.status == "completed"
    assert len(result.renders) == 3

    # 2. Verify all 3 MP4 files exist and passed QA
    for render in result.renders:
        video_path = Path(render.file_path)
        assert video_path.exists()
        assert video_path.stat().st_size > 0
        assert render.width == 1080
        assert render.height == 1920
        assert render.qa_passed is True

        # 3. Verify provenance linkages in SQLite
        with repo.get_session() as session:
            from engine.experiments.models import RenderAsset
            from sqlalchemy import select
            links = session.execute(
                select(RenderAsset).where(RenderAsset.render_id == render.id)
            ).scalars().all()
            assert len(links) in (3, 4)  # background_video, voiceover, subtitle_font, (optional background_music)

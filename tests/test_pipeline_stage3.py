"""Tests for Stage 3: ContentEnginePipeline adaptation (existing_run_id and on_progress)."""

from pathlib import Path
from typing import List
import pytest

from engine.experiments.models import ExperimentRun
from engine.experiments.repository import ExperimentRepository
from engine.media.base import Compositor
from engine.media.compositor import FFmpegCompositor
from engine.media.transcription import DummyTranscriptionProvider
from engine.media.voice import DummyVoiceProvider
from engine.pipeline import ContentEnginePipeline, ProgressUpdate
from engine.qa.validator import MediaValidator
from engine.scripting.schema import HookType, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider


@pytest.fixture
def stage3_setup(tmp_path: Path):
    """Setup isolated repository and pipeline for Stage 3 tests."""
    db_file = tmp_path / "test_stage3.db"
    repo = ExperimentRepository(db_url=f"sqlite:///{db_file.as_posix()}")
    repo.init_db()

    pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=DummyScriptProvider(),
        voice_provider=DummyVoiceProvider(words_per_minute=300),
        transcription_provider=DummyTranscriptionProvider(),
        compositor=FFmpegCompositor(prefer_nvenc=False),
        validator=MediaValidator(expected_width=1080, expected_height=1920, duration_tolerance_sec=4.0),
    )

    exp = repo.create_experiment(name="Exp Stage 3", description="Testing Stage 3 pipeline integration")
    hypo = repo.create_hypothesis(
        experiment_id=exp.id,
        statement="Evaluating hook retention",
        independent_variable="hook_type",
        primary_metric="RETENTION_3S",
        success_criterion="retention > 0.35",
        baseline_description="Standard short-form baseline",
    )

    plans = [
        VariantPlan(variant_code="A", hook_type=HookType.QUESTION, target_duration_sec=0.5, topic="el cosmos"),
        VariantPlan(variant_code="B", hook_type=HookType.STATEMENT, target_duration_sec=0.5, topic="el cosmos"),
        VariantPlan(variant_code="C", hook_type=HookType.SURPRISE, target_duration_sec=0.5, topic="el cosmos"),
    ]

    return repo, pipeline, exp, hypo, plans, tmp_path


def test_existing_run_adoption_single_identity(stage3_setup):
    """Test 1: Verify pipeline adopts an existing ExperimentRun without creating a duplicate run."""
    repo, pipeline, exp, hypo, plans, tmp_path = stage3_setup
    out_dir = tmp_path / "renders_adopt"

    # Pre-create a run in 'queued' status (simulating RunDispatcher creation)
    pre_run = repo.create_run(
        experiment_id=exp.id,
        pipeline_version="0.1.0-pre",
        config_hash="pre_hash",
        status="queued",
    )
    pre_run_id = pre_run.id

    # Count runs before pipeline
    with repo.get_session() as session:
        count_before = session.query(ExperimentRun).count()
    assert count_before == 1

    # Execute pipeline passing existing_run_id
    result = pipeline.run_experiment_variants(
        experiment_id=exp.id,
        hypothesis_id=hypo.id,
        variant_plans=plans,
        output_dir=out_dir,
        existing_run_id=pre_run_id,
    )

    # Count runs after pipeline: MUST REMAIN EXACTLY 1 (No duplicate Run!)
    with repo.get_session() as session:
        count_after = session.query(ExperimentRun).count()
        db_run = session.get(ExperimentRun, pre_run_id)

    assert count_after == 1
    assert result.run.id == pre_run_id
    assert db_run.status == "completed"
    assert len(result.renders) == 3
    for r in result.renders:
        assert r.experiment_run_id == pre_run_id


def test_ownership_mismatch_raises_and_prevents_rendering(stage3_setup):
    """Test 2: If existing_run_id belongs to another experiment, pipeline fails immediately without renders."""
    repo, pipeline, exp, hypo, plans, tmp_path = stage3_setup
    out_dir = tmp_path / "renders_mismatch"

    # Create a foreign experiment and a run belonging to it
    foreign_exp = repo.create_experiment(name="Foreign Exp", description="Different owner")
    foreign_run = repo.create_run(
        experiment_id=foreign_exp.id,
        pipeline_version="0.1.0",
        config_hash="foreign_hash",
        status="queued",
    )

    # Invoke pipeline with mismatched experiment_id vs existing_run_id
    with pytest.raises(ValueError, match="belongs to experiment"):
        pipeline.run_experiment_variants(
            experiment_id=exp.id,
            hypothesis_id=hypo.id,
            variant_plans=plans,
            output_dir=out_dir,
            existing_run_id=foreign_run.id,
        )

    # Confirm no renders exist and foreign run status is untouched
    with repo.get_session() as session:
        re_foreign_run = session.get(ExperimentRun, foreign_run.id)
        assert re_foreign_run.status == "queued"
        assert len(re_foreign_run.renders) == 0


def test_legacy_behavior_creates_run_when_existing_run_id_none(stage3_setup):
    """Test 3: When existing_run_id is None, pipeline creates ExperimentRun as in Phase 1."""
    repo, pipeline, exp, hypo, plans, tmp_path = stage3_setup
    out_dir = tmp_path / "renders_legacy"

    with repo.get_session() as session:
        count_before = session.query(ExperimentRun).count()

    result = pipeline.run_experiment_variants(
        experiment_id=exp.id,
        hypothesis_id=hypo.id,
        variant_plans=plans,
        output_dir=out_dir,
        existing_run_id=None,
    )

    with repo.get_session() as session:
        count_after = session.query(ExperimentRun).count()

    assert count_after == count_before + 1
    assert result.run.status == "completed"
    assert len(result.renders) == 3


def test_progress_sequence_and_real_milestones(stage3_setup):
    """Test 4: Capture all progress callback events and verify coherent sequence and percentages."""
    repo, pipeline, exp, hypo, plans, tmp_path = stage3_setup
    out_dir = tmp_path / "renders_progress"

    events: List[ProgressUpdate] = []

    def on_progress(update: ProgressUpdate):
        events.append(update)

    result = pipeline.run_experiment_variants(
        experiment_id=exp.id,
        hypothesis_id=hypo.id,
        variant_plans=plans,
        output_dir=out_dir,
        on_progress=on_progress,
    )

    assert len(events) >= 8  # starting + 3*(variant_started, rendering, variant_completed) + completed

    # Verify first and last events
    assert events[0].stage == "starting"
    assert events[0].progress_percent == 0
    assert events[0].status == "running"

    last_event = events[-1]
    assert last_event.stage == "completed"
    assert last_event.progress_percent == 100
    assert last_event.completed_variants == 3
    assert last_event.status == "completed"

    # Verify all variants appear in order
    variants_seen = [e.current_variant for e in events if e.current_variant is not None]
    assert "A" in variants_seen
    assert "B" in variants_seen
    assert "C" in variants_seen

    # Verify non-decreasing progress percentage
    percentages = [e.progress_percent for e in events]
    assert percentages == sorted(percentages)


def test_callback_failure_does_not_break_rendering(stage3_setup):
    """Test 5: If on_progress raises an exception, pipeline catches it and render completes successfully."""
    repo, pipeline, exp, hypo, plans, tmp_path = stage3_setup
    out_dir = tmp_path / "renders_cb_err"

    def faulty_callback(update: ProgressUpdate):
        raise RuntimeError("Simulated UI callback failure or network disconnect")

    result = pipeline.run_experiment_variants(
        experiment_id=exp.id,
        hypothesis_id=hypo.id,
        variant_plans=plans,
        output_dir=out_dir,
        on_progress=faulty_callback,
    )

    # Pipeline MUST complete without aborting
    assert result.run.status == "completed"
    assert len(result.renders) == 3


def test_failure_reporting_on_exception(stage3_setup):
    """Test 6: Simulated pipeline failure records status 'failed' and notifies on_progress."""
    repo, pipeline, exp, hypo, plans, tmp_path = stage3_setup
    out_dir = tmp_path / "renders_fail"

    # Inject a failing compositor to simulate rendering failure
    class FailingCompositor(Compositor):
        def compose_video(self, *args, **kwargs):
            raise IOError("Disk full or FFmpeg encoding error")

    failing_pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=pipeline.script_provider,
        voice_provider=pipeline.voice_provider,
        transcription_provider=pipeline.transcription_provider,
        compositor=FailingCompositor(),
        validator=pipeline.validator,
    )

    captured_events: List[ProgressUpdate] = []

    def on_progress(update: ProgressUpdate):
        captured_events.append(update)

    with pytest.raises(IOError, match="FFmpeg encoding error"):
        failing_pipeline.run_experiment_variants(
            experiment_id=exp.id,
            hypothesis_id=hypo.id,
            variant_plans=plans,
            output_dir=out_dir,
            on_progress=on_progress,
        )

    # Verify run marked as failed in DB
    with repo.get_session() as session:
        runs = session.query(ExperimentRun).filter(ExperimentRun.experiment_id == exp.id).all()
        failed_run = runs[-1]
        assert failed_run.status == "failed"
        assert "FFmpeg encoding error" in failed_run.error_message

    # Verify callback received stage = 'failed'
    failed_events = [e for e in captured_events if e.stage == "failed"]
    assert len(failed_events) == 1
    assert failed_events[0].status == "failed"
    assert "FFmpeg encoding error" in failed_events[0].message

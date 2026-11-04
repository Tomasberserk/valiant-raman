"""Tests for Stage 4: LocalRunDispatcher background orchestration and single-run identity."""

from pathlib import Path
import threading
import time
from typing import List, Optional
import pytest

from engine.creative.run_dispatcher import LocalRunDispatcher, RunDispatcher
from engine.experiments.models import ExperimentRun, Render
from engine.experiments.repository import ExperimentRepository
from engine.media.base import Compositor, TranscriptionProvider, VoiceProvider, AudioResult, WordTimestamp
from engine.pipeline import ContentEnginePipeline, ProgressUpdate
from engine.qa.validator import MediaValidator, QAReport
from engine.scripting.schema import HookType, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider


class FastDummyVoiceProvider(VoiceProvider):
    """Instant voice provider creating dummy audio without external calls."""
    def generate_audio(self, text: str, voice_id: str, output_path: Path, rate: str = "+0%", pitch: str = "+0Hz") -> AudioResult:
        output_path.write_bytes(b"RIFF_DUMMY_AUDIO_DATA")
        return AudioResult(file_path=output_path, duration_seconds=1.0, voice_id=voice_id, provider="dummy")


class FastDummyTranscriptionProvider(TranscriptionProvider):
    """Instant word-timestamp provider."""
    def transcribe(self, audio_path: Path, reference_text: Optional[str] = None) -> List[WordTimestamp]:
        return [WordTimestamp(word="test", start=0.0, end=1.0)]


class FastDummyCompositor(Compositor):
    """Instant compositor writing a small dummy MP4 file."""
    def compose_video(self, background_path: Path, audio_path: Path, subtitles_path: Optional[Path], output_path: Path, duration_seconds: float) -> Path:
        output_path.write_bytes(b"DUMMY_MP4_VIDEO_BYTES")
        return output_path


class FastDummyValidator(MediaValidator):
    """Instant QA validator."""
    def validate_render(self, file_path: Path, expected_duration_sec: float, subtitles_path: Optional[Path] = None) -> QAReport:
        return QAReport(file_path=str(file_path), passed=True, checks=[], metadata={"dummy": True})


@pytest.fixture
def dispatcher_setup(tmp_path: Path):
    """Setup isolated repository, fast pipeline, and LocalRunDispatcher."""
    db_file = tmp_path / "test_dispatcher.db"
    repo = ExperimentRepository(db_url=f"sqlite:///{db_file.as_posix()}")
    repo.init_db()

    pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=DummyScriptProvider(),
        voice_provider=FastDummyVoiceProvider(),
        transcription_provider=FastDummyTranscriptionProvider(),
        compositor=FastDummyCompositor(),
        validator=FastDummyValidator(),
    )

    dispatcher = LocalRunDispatcher(repository=repo, pipeline=pipeline, max_workers=1)

    exp = repo.create_experiment(name="Exp Dispatcher Test", description="Testing background execution")
    hypo = repo.create_hypothesis(
        experiment_id=exp.id,
        statement="Testing background dispatching",
        independent_variable="hook_type",
        primary_metric="RETENTION_3S",
        success_criterion="retention > 0.35",
        baseline_description="Standard baseline",
    )

    plans = [
        VariantPlan(variant_code="A", hook_type=HookType.QUESTION, target_duration_sec=1.0, topic="el cosmos"),
        VariantPlan(variant_code="B", hook_type=HookType.STATEMENT, target_duration_sec=1.0, topic="el cosmos"),
        VariantPlan(variant_code="C", hook_type=HookType.SURPRISE, target_duration_sec=1.0, topic="el cosmos"),
    ]

    yield repo, pipeline, dispatcher, exp, hypo, plans, tmp_path
    dispatcher.shutdown(wait=True)


def test_basic_dispatch_lifecycle(dispatcher_setup):
    """Test 1: Verify dispatch returns immediately, creates queued run, and worker completes it."""
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup
    out_dir = tmp_path / "renders_basic"

    progress_events: List[ProgressUpdate] = []
    completion_event = threading.Event()

    def on_progress(update: ProgressUpdate):
        progress_events.append(update)
        if update.status in ("completed", "failed"):
            completion_event.set()

    run_id = dispatcher.dispatch(
        experiment_id=exp.id,
        hypothesis_id=hypo.id,
        variant_plans=plans,
        output_dir=out_dir,
        on_progress=on_progress,
    )

    # 1. Assert run_id returned immediately
    assert run_id is not None
    assert len(run_id) == 36

    # 2. Wait for background execution to complete
    finished = completion_event.wait(timeout=10.0)
    assert finished is True, "Background execution did not finish within timeout."

    # 3. Verify final state in SQLite database
    with repo.get_session() as session:
        db_run = session.get(ExperimentRun, run_id)
        assert db_run is not None
        assert db_run.status == "completed"
        assert len(db_run.renders) == 3

    # 4. Verify progress events and cached progress
    cached_progress = dispatcher.get_progress(run_id)
    assert cached_progress is not None
    assert cached_progress.status == "completed"
    assert cached_progress.progress_percent == 100
    assert any(e.stage == "queued" for e in progress_events)
    assert any(e.stage == "completed" for e in progress_events)


def test_single_run_identity_guarantee(dispatcher_setup):
    """Test 2: Assert Dispatcher-created Run ID == Pipeline-used Run ID == Render.experiment_run_id."""
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup
    out_dir = tmp_path / "renders_identity"

    completion_event = threading.Event()

    def on_progress(update: ProgressUpdate):
        if update.status in ("completed", "failed"):
            completion_event.set()

    run_id = dispatcher.dispatch(
        experiment_id=exp.id,
        hypothesis_id=hypo.id,
        variant_plans=plans,
        output_dir=out_dir,
        on_progress=on_progress,
    )
    completion_event.wait(timeout=10.0)

    with repo.get_session() as session:
        runs = session.query(ExperimentRun).filter(ExperimentRun.experiment_id == exp.id).all()
        # Exactly ONE ExperimentRun must exist for this experiment
        assert len(runs) == 1
        assert runs[0].id == run_id

        # All renders must reference this exact run_id
        renders = session.query(Render).filter(Render.experiment_run_id == run_id).all()
        assert len(renders) == 3
        for r in renders:
            assert r.experiment_run_id == run_id


def test_concurrency_serialization_two_jobs(dispatcher_setup):
    """Test 3: Verify max_workers=1 executes two jobs sequentially via deterministic barrier."""
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup

    job1_entered = threading.Event()
    job1_can_proceed = threading.Event()
    job2_entered = threading.Event()

    class BlockingCompositor(Compositor):
        def compose_video(self, background_path: Path, audio_path: Path, subtitles_path: Optional[Path], output_path: Path, duration_seconds: float) -> Path:
            output_path.write_bytes(b"DUMMY")
            # If this is job 1's first call, block until released
            if not job1_entered.is_set():
                job1_entered.set()
                job1_can_proceed.wait(timeout=5.0)
            else:
                job2_entered.set()
            return output_path

    blocking_pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=pipeline.script_provider,
        voice_provider=pipeline.voice_provider,
        transcription_provider=pipeline.transcription_provider,
        compositor=BlockingCompositor(),
        validator=FastDummyValidator(),
    )

    test_dispatcher = LocalRunDispatcher(repository=repo, pipeline=blocking_pipeline, max_workers=1)

    exp2 = repo.create_experiment(name="Exp 2", description="Second experiment")
    hypo2 = repo.create_hypothesis(
        experiment_id=exp2.id,
        statement="Hypo 2",
        independent_variable="hook_type",
        primary_metric="RETENTION_3S",
        success_criterion="pass",
        baseline_description="base",
    )

    # 1. Dispatch Job 1
    run1_id = test_dispatcher.dispatch(exp.id, hypo.id, plans, output_dir=tmp_path / "job1")

    # 2. Wait until Job 1 has actually entered its composition stage
    assert job1_entered.wait(timeout=5.0) is True

    # 3. Dispatch Job 2 while Job 1 is still blocked in compositor
    run2_id = test_dispatcher.dispatch(exp2.id, hypo2.id, plans, output_dir=tmp_path / "job2")

    # 4. Verify Job 2 has NOT entered execution (it is queued in executor)
    assert not job2_entered.is_set()
    prog2 = test_dispatcher.get_progress(run2_id)
    assert prog2.status == "queued"

    # 5. Release Job 1 and wait for both to complete
    job1_can_proceed.set()
    test_dispatcher.shutdown(wait=True)

    # Verify both completed sequentially
    with repo.get_session() as session:
        r1 = session.get(ExperimentRun, run1_id)
        r2 = session.get(ExperimentRun, run2_id)
        assert r1.status == "completed"
        assert r2.status == "completed"


def test_failure_isolation_between_jobs(dispatcher_setup):
    """Test 4: Verify that a failing job leaves Run in failed status without breaking the dispatcher for subsequent jobs."""
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup

    exp_failing = repo.create_experiment(name="Failing Exp", description="Will fail")
    hypo_failing = repo.create_hypothesis(
        experiment_id=exp_failing.id,
        statement="Failing hypo",
        independent_variable="hook_type",
        primary_metric="RETENTION_3S",
        success_criterion="fail",
        baseline_description="base",
    )

    class OneShotFailCompositor(Compositor):
        def __init__(self):
            self.failed_once = False
        def compose_video(self, background_path: Path, audio_path: Path, subtitles_path: Optional[Path], output_path: Path, duration_seconds: float) -> Path:
            if not self.failed_once:
                self.failed_once = True
                raise IOError("Controlled disk failure for Job A")
            output_path.write_bytes(b"DUMMY_MP4")
            return output_path

    fail_pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=pipeline.script_provider,
        voice_provider=pipeline.voice_provider,
        transcription_provider=pipeline.transcription_provider,
        compositor=OneShotFailCompositor(),
        validator=FastDummyValidator(),
    )

    test_dispatcher = LocalRunDispatcher(repository=repo, pipeline=fail_pipeline, max_workers=1)

    # 1. Dispatch Job A (Fails)
    run_a_id = test_dispatcher.dispatch(exp_failing.id, hypo_failing.id, plans, output_dir=tmp_path / "out_a")

    # 2. Dispatch Job B (Succeeds)
    run_b_id = test_dispatcher.dispatch(exp.id, hypo.id, plans, output_dir=tmp_path / "out_b")

    test_dispatcher.shutdown(wait=True)

    # 3. Assert Job A is marked failed and Job B completed successfully
    with repo.get_session() as session:
        run_a = session.get(ExperimentRun, run_a_id)
        run_b = session.get(ExperimentRun, run_b_id)

        assert run_a.status == "failed"
        assert "Controlled disk failure for Job A" in (run_a.error_message or "")

        assert run_b.status == "completed"
        assert len(run_b.renders) == 3


def test_no_duplicate_run_in_database(dispatcher_setup):
    """Test 5: Explicitly verify that dispatch + pipeline(existing_run_id) creates exactly 1 run."""
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup

    with repo.get_session() as session:
        initial_count = session.query(ExperimentRun).count()

    run_id = dispatcher.dispatch(exp.id, hypo.id, plans, output_dir=tmp_path / "renders_count")
    dispatcher.shutdown(wait=True)

    with repo.get_session() as session:
        final_count = session.query(ExperimentRun).count()
        run = session.get(ExperimentRun, run_id)

    assert final_count == initial_count + 1
    assert run is not None
    assert run.status == "completed"


def test_session_isolation(dispatcher_setup):
    """Test 6: Background execution runs independently without caller session coupling."""
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup

    # Caller opens a transaction session, creates a temporary entity, but DOES NOT commit yet
    with repo.get_session() as caller_session:
        temp_exp = repo.create_experiment(name="Uncommitted Experiment", description="Holder")
        assert temp_exp.id is not None

        # Dispatch real experiment
        run_id = dispatcher.dispatch(exp.id, hypo.id, plans, output_dir=tmp_path / "session_iso")

        # Caller can perform queries without blocking or conflicting
        assert caller_session.get(ExperimentRun, run_id) is not None

    # Wait for dispatcher to finish
    dispatcher.shutdown(wait=True)

    # Confirm run succeeded in DB
    with repo.get_session() as session:
        completed_run = session.get(ExperimentRun, run_id)
        assert completed_run.status == "completed"


def test_shutdown_lifecycle(dispatcher_setup):
    """Test 7: Verify shutdown terminates executor and rejects further dispatch calls."""
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup

    dispatcher.shutdown(wait=True)

    with pytest.raises(RuntimeError, match="already shut down"):
        dispatcher.dispatch(exp.id, hypo.id, plans)


def test_creative_service_launch_experiment_integration(dispatcher_setup):
    """Test 8: Verify CreativeService.launch_experiment compiles and dispatches via LocalRunDispatcher."""
    from engine.creative.service import CreativeService
    repo, pipeline, dispatcher, exp, hypo, plans, tmp_path = dispatcher_setup

    service = CreativeService(repository=repo, dispatcher=dispatcher)
    idea = service.capture_idea(raw_text="El telescopio James Webb detecta galaxias primitivas imposibles")
    concepts = service.analyze_idea(idea.id)
    service.select_concept(concepts[0].id)

    run_id = service.launch_experiment(concepts[0].id)
    assert run_id is not None
    assert len(run_id) == 36

    dispatcher.shutdown(wait=True)

    with repo.get_session() as session:
        run = session.get(ExperimentRun, run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.experiment.source_concept_id == concepts[0].id


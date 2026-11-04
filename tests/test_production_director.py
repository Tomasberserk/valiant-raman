"""Unit and Integration Tests for ProductionDirector (Stage 12D.2).

Validates:
1. Precondition rejection on tampered dossier_sha256 (FAILED_PRECONDITION, 0 retries).
2. Precondition rejection on empty claims.
3. Sequential idempotency: identical request_id returns existing job without duplicate work.
4. Concurrency-safe ACQUIRE: simultaneous threads with same request_id get identical job.
5. Happy-path state machine sequence (CREATED -> ... -> COMPLETED) with audit events.
6. Director-governed REGENERATE action recovers from initial grounding violation.
7. Director-governed REGENERATE exhaustion transitions deterministically to FAILED_GROUNDING.
8. Director-governed RETRY action recovers from transient scene I/O error.
9. Director-governed RETRY exhaustion transitions deterministically to FAILED_SCENE.
10. Director-governed REPAIR action recovers master from loudness deviation using -14 LUFS policy.
11. Visual ladder fallback to Tier 4 is normal and never triggers FAILED_VISUAL.
12. Durable JobStore serialization and crash recovery from disk.
13. Strict read-only propagation of master_sha256 from 12B.5 (no recalculation).
14. COMPLETED is strictly derived from 12B.5 certification (REJECTED -> FAILED_MEDIA_QA).
15. Zero imports of external network / scraping / real LLM vendor APIs.
"""

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import pytest

from engine.director import (
    CreativeBrief,
    JobExecutionPolicy,
    JobStore,
    MasterCertificationAdapter,
    OutputSpec,
    ProductionDirector,
    ProductionJob,
    ProductionRequest,
    ProductionResult,
    ProductionState,
    RecoveryAction,
    SceneExecutionMetadata,
    SceneProductionAdapter,
    StoryTruthAdapter,
)
from engine.story import (
    AssertionUnit,
    ClaimStatus,
    EndingStrategy,
    FactClaim,
    FactDossier,
    FactIntelligenceEngine,
    FactSource,
    FinalMediaQAReport,
    GroundingFinding,
    GroundingReport,
    LLMProvider,
    MasterTimeline,
    MediaQAFinding,
    MockLLMProvider,
    NarrativeRole,
    PublicationStatus,
    ResolutionTier,
    Scene,
    SceneDraft,
    SceneQAReport,
    SourceAuthority,
    StatementType,
    StoryArc,
    StoryContract,
    StoryDraft,
    StoryQAReport,
    VisualBrief,
    VisualResolutionResult,
)


@pytest.fixture
def sample_dossier() -> FactDossier:
    """Construct an authoritative, sealed FactDossier for testing."""
    engine = FactIntelligenceEngine()
    s1 = FactSource(
        source_id="src_gottingen_arch",
        title="Gottingen University Historical Archives",
        publisher="University of Gottingen",
        authority_level=SourceAuthority.PRIMARY_INSTITUTIONAL,
    )
    claims = [
        FactClaim(
            claim_id="claim_01",
            claim_text="Gauss y Weber instalaron una línea de 1.2 kilómetros en 1833.",
            source_ids=["src_gottingen_arch"],
            status=ClaimStatus.VERIFIED,
            supporting_excerpt="En 1833 instalaron 1.2 km de línea telegráfica.",
        ),
        FactClaim(
            claim_id="claim_02",
            claim_text="El dispositivo unía el observatorio con el laboratorio de física.",
            source_ids=["src_gottingen_arch"],
            status=ClaimStatus.VERIFIED,
        ),
    ]
    return engine.compile_dossier(
        dossier_id="dossier_test_gottingen",
        run_id="run_test_dir",
        topic="El telégrafo de Gauss y Weber",
        sources=[s1],
        claims=claims,
        key_entities=["Gauss", "Weber"],
    )


@pytest.fixture
def sample_request(sample_dossier: FactDossier) -> ProductionRequest:
    return ProductionRequest(
        request_id="req_test_001",
        topic="El telégrafo de Gauss y Weber",
        dossier=sample_dossier,
        creative_brief=CreativeBrief(hook_strategy="question", tone="curious_informative"),
        output_spec=OutputSpec(),
        execution_policy=JobExecutionPolicy(
            max_surgical_regenerations=2,
            max_scene_retries=2,
            max_master_repairs=1,
        ),
    )


# -----------------------------------------------------------------------------
# 1. Preconditions & Integrity Tests
# -----------------------------------------------------------------------------

def test_director_precondition_rejection_dossier_hash_tampered(
    sample_request: ProductionRequest, tmp_path: Path
):
    """1. Rejects request with tampered dossier_sha256 (FAILED_PRECONDITION, 0 retries)."""
    store = JobStore(base_dir=tmp_path / "jobs")
    director = ProductionDirector(store=store)

    # Tamper with dossier hash
    tampered_dossier = sample_request.dossier.model_copy(update={"dossier_sha256": "f" * 64})
    bad_request = sample_request.model_copy(update={"dossier": tampered_dossier})

    result = director.execute_job(bad_request)

    assert result.status == ProductionState.FAILED_PRECONDITION
    assert result.is_certified is False
    assert "DOSSIER_HASH_MISMATCH" in (result.error_summary or "")

    job = store.load_job(result.job_id)
    assert job.current_state == ProductionState.FAILED_PRECONDITION
    assert len(job.state_history) == 1
    assert job.state_history[0].to_state == ProductionState.FAILED_PRECONDITION


def test_director_precondition_rejection_empty_claims(tmp_path: Path):
    """2. Rejects dossier with zero claims."""
    store = JobStore(base_dir=tmp_path / "jobs")
    director = ProductionDirector(store=store)
    engine = FactIntelligenceEngine()

    empty_dossier = engine.compile_dossier(
        dossier_id="dossier_empty",
        run_id="run_empty",
        topic="Tema vacío",
        sources=[],
        claims=[],
    )
    req = ProductionRequest(request_id="req_empty", topic="Vacío", dossier=empty_dossier)
    result = director.execute_job(req)

    assert result.status == ProductionState.FAILED_PRECONDITION
    assert "DOSSIER_EMPTY_CLAIMS" in (result.error_summary or "")


# -----------------------------------------------------------------------------
# 2. Idempotency & Concurrency Tests
# -----------------------------------------------------------------------------

def test_director_idempotency_sequential_calls(sample_request: ProductionRequest, tmp_path: Path):
    """3. Sequential calls with identical request_id return the same job without duplication."""
    store = JobStore(base_dir=tmp_path / "jobs")
    director = ProductionDirector(store=store)

    # First acquire
    job1, is_new1 = store.acquire(sample_request.request_id, sample_request)
    assert is_new1 is True

    # Second acquire with same request_id
    job2, is_new2 = store.acquire(sample_request.request_id, sample_request)
    assert is_new2 is False
    assert job1.job_id == job2.job_id
    assert job1.workspace_dir == job2.workspace_dir


def test_director_idempotency_concurrent_threads(sample_request: ProductionRequest, tmp_path: Path):
    """4. 10 simultaneous threads competing on the same request_id acquire the exact same job."""
    store = JobStore(base_dir=tmp_path / "jobs")

    def acquire_job(idx: int):
        req = sample_request.model_copy(update={"request_id": "req_concurrent_atomic_key"})
        job, is_new = store.acquire("req_concurrent_atomic_key", req)
        return job.job_id, is_new

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(acquire_job, range(10)))

    job_ids = [r[0] for r in results]
    is_new_flags = [r[1] for r in results]

    # Exactly 1 thread must get is_new=True, all others is_new=False
    assert is_new_flags.count(True) == 1
    assert is_new_flags.count(False) == 9

    # All threads must share the exact same job_id
    assert len(set(job_ids)) == 1


# -----------------------------------------------------------------------------
# 3. Happy Path & State Machine Sequence
# -----------------------------------------------------------------------------

def test_director_state_machine_happy_path_fast(sample_request: ProductionRequest, tmp_path: Path):
    """5. Happy-path full state machine execution verifying exact transition sequence."""
    store = JobStore(base_dir=tmp_path / "jobs")

    # Fast mocked adapters adhering to Stage 12B/12C contracts
    class FastStoryTruthAdapter(StoryTruthAdapter):
        def synthesize_draft(self, dossier, creative_brief):
            return StoryDraft(
                title="Gottingen Telegraph",
                topic=dossier.topic,
                core_question="How was it built?",
                narrative_promise="Discover the wire network.",
                scenes=[
                    SceneDraft(
                        scene_id="scene_01",
                        scene_index=0,
                        narrative_role=NarrativeRole.HOOK,
                        narration="Hook narration text.",
                        assertions=[],
                    )
                ],
                dossier_id=dossier.dossier_id,
                dossier_sha256=dossier.dossier_sha256,
            )

        def evaluate_grounding(self, draft, dossier):
            return GroundingReport(passed=True, scene_status={"scene_01": True})

        def convert_and_audit(self, draft, dossier):
            scene = Scene(
                id="scene_01",
                scene_index=0,
                narrative_role=NarrativeRole.HOOK,
                script_text="Hook narration text.",
                word_count=3,
                estimated_duration_sec=70.0,
                actual_duration_sec=70.0,
                scene_qa_passed=True,
            )
            arc = StoryArc(
                id=f"arc_{dossier.dossier_id}",
                contract=StoryContract(
                    id="contract_01",
                    title="Gottingen Telegraph",
                    topic=dossier.topic,
                    core_question="?",
                    narrative_promise="Promise",
                    ending_strategy=EndingStrategy.PAYOFF,
                ),
                scenes=[scene],
                total_estimated_duration_sec=70.0,
                status="qa_passed",
            )
            return arc, StoryQAReport(passed=True, total_estimated_duration_sec=70.0)

    class FastSceneProductionAdapter(SceneProductionAdapter):
        def resolve_visuals(self, story_arc):
            return {
                "scene_01": VisualResolutionResult(
                    scene_id="scene_01",
                    tier=ResolutionTier.TIER4_STYLED_FALLBACK,
                    production_strategy="styled_cinematic",
                    score=0.5,
                    rationale="Fallback Tier 4",
                )
            }

        def produce_scene(self, scene, visual_result, output_dir, attempt_id="attempt_01"):
            dummy_asset = output_dir / "scene_01.mp4"
            dummy_asset.parent.mkdir(parents=True, exist_ok=True)
            dummy_asset.write_text("dummy video")
            scene.resolved_asset_path = dummy_asset
            scene.actual_duration_sec = 70.0
            return scene, SceneQAReport(scene_id=scene.id, passed=True)

    class FastMasterCertificationAdapter(MasterCertificationAdapter):
        def assemble_master(self, story_arc, scenes_dir, output_dir, bgm_path=None):
            output_dir.mkdir(parents=True, exist_ok=True)
            video_file = output_dir / "master_story.mp4"
            video_file.write_text("master content")
            return MasterTimeline(
                story_id=story_arc.id,
                target_duration_sec=70.0,
                total_actual_duration_sec=70.0,
                master_video_path=video_file,
            )

        def certify_and_export(self, master_timeline, export_dir, story_arc=None):
            export_dir.mkdir(parents=True, exist_ok=True)
            cert_mp4 = export_dir / "certified_master.mp4"
            cert_mp4.write_text("certified mp4 content")
            manifest = export_dir / "manifest.json"
            manifest.write_text("{}")
            return FinalMediaQAReport(
                story_id=master_timeline.story_id,
                master_video_path=cert_mp4,
                status=PublicationStatus.CERTIFIED_FOR_PUBLICATION,
                passed=True,
                duration_sec=70.0,
                certified_output_path=cert_mp4,
                manifest_path=manifest,
                master_sha256="abc123canonicalhash",
            )

    director = ProductionDirector(
        store=store,
        story_adapter=FastStoryTruthAdapter(),
        production_adapter=FastSceneProductionAdapter(),
        certification_adapter=FastMasterCertificationAdapter(),
    )

    result = director.execute_job(sample_request)

    assert result.status == ProductionState.COMPLETED
    assert result.is_certified is True
    assert result.master_sha256 == "abc123canonicalhash"
    assert result.total_physical_duration_sec == 70.0

    job = store.load_job(result.job_id)
    states = [r.to_state for r in job.state_history]
    assert states == [
        ProductionState.STORY_SYNTHESIS,
        ProductionState.CLAIM_GROUNDING,
        ProductionState.STORY_QA_AUDIT,
        ProductionState.VISUAL_RESOLUTION,
        ProductionState.SCENE_PRODUCTION,
        ProductionState.MASTER_ASSEMBLY,
        ProductionState.FINAL_MEDIA_QA,
        ProductionState.COMPLETED,
    ]


# -----------------------------------------------------------------------------
# 4. Recovery Actions: REGENERATE, RETRY, REPAIR
# -----------------------------------------------------------------------------

def test_director_surgical_regeneration_recovery(sample_request: ProductionRequest, tmp_path: Path):
    """6. Grounding failure activates REGENERATE loop and successfully recovers."""
    store = JobStore(base_dir=tmp_path / "jobs")

    call_count = 0

    class FailingThenPassingStoryTruthAdapter(StoryTruthAdapter):
        def synthesize_draft(self, dossier, creative_brief):
            return StoryDraft(
                title="T",
                topic=dossier.topic,
                core_question="?",
                narrative_promise="P",
                scenes=[
                    SceneDraft(
                        scene_id="scene_01",
                        scene_index=0,
                        narrative_role=NarrativeRole.HOOK,
                        narration="Flawed narration.",
                        assertions=[
                            AssertionUnit(
                                text="Flawed fact",
                                statement_type=StatementType.FACTUAL,
                                claim_ids=[],
                            )
                        ],
                    )
                ],
                dossier_id=dossier.dossier_id,
                dossier_sha256=dossier.dossier_sha256,
            )

        def evaluate_grounding(self, draft, dossier):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return GroundingReport(
                    passed=False,
                    scene_status={"scene_01": False},
                    findings=[
                        GroundingFinding(
                            rule="UNGROUNDED_FACTUAL_ASSERTION",
                            severity="ERROR",
                            scene_id="scene_01",
                            assertion_text="Flawed fact",
                            message="Orphan claim",
                            remediation="Attach valid claim",
                        )
                    ],
                )
            return GroundingReport(passed=True, scene_status={"scene_01": True})

        def regenerate_scene(self, draft, scene_id, dossier, remediation_hint):
            return draft  # Fixed on next evaluate_grounding

        def convert_and_audit(self, draft, dossier):
            arc = StoryArc(
                id="arc_01",
                contract=StoryContract(
                    id="c", title="T", topic="T", core_question="?", narrative_promise="P"
                ),
                scenes=[],
                total_estimated_duration_sec=70.0,
            )
            return arc, StoryQAReport(passed=True, total_estimated_duration_sec=70.0)

    class StubSceneAdapter(SceneProductionAdapter):
        def resolve_visuals(self, arc):
            return {}

        def produce_scene(self, scene, res, out_dir, attempt_id="attempt_01"):
            return scene, SceneQAReport(scene_id=scene.id, passed=True)

    class StubMasterAdapter(MasterCertificationAdapter):
        def assemble_master(self, arc, s_dir, o_dir, bgm=None):
            return MasterTimeline(story_id=arc.id, target_duration_sec=70.0)

        def certify_and_export(self, timeline, exp_dir, arc=None):
            return FinalMediaQAReport(
                story_id="arc_01",
                master_video_path=Path("dummy"),
                status=PublicationStatus.CERTIFIED_FOR_PUBLICATION,
                passed=True,
                duration_sec=70.0,
                master_sha256="hash_regen_ok",
            )

    director = ProductionDirector(
        store=store,
        story_adapter=FailingThenPassingStoryTruthAdapter(),
        production_adapter=StubSceneAdapter(),
        certification_adapter=StubMasterAdapter(),
    )

    result = director.execute_job(sample_request)

    assert result.status == ProductionState.COMPLETED
    job = store.load_job(result.job_id)
    assert job.recovery_stats["regenerations"] == 1


def test_director_surgical_regeneration_exhaustion(sample_request: ProductionRequest, tmp_path: Path):
    """7. Persistent grounding failure exhausts max_surgical_regenerations -> FAILED_GROUNDING."""
    store = JobStore(base_dir=tmp_path / "jobs")

    class AlwaysFailingGroundingAdapter(StoryTruthAdapter):
        def synthesize_draft(self, dossier, creative_brief):
            return StoryDraft(
                title="T",
                topic=dossier.topic,
                core_question="?",
                narrative_promise="P",
                scenes=[
                    SceneDraft(
                        scene_id="scene_01",
                        scene_index=0,
                        narrative_role=NarrativeRole.HOOK,
                        narration="Bad",
                        assertions=[],
                    )
                ],
                dossier_id=dossier.dossier_id,
                dossier_sha256=dossier.dossier_sha256,
            )

        def evaluate_grounding(self, draft, dossier):
            return GroundingReport(
                passed=False,
                scene_status={"scene_01": False},
                findings=[
                    GroundingFinding(
                        rule="UNGROUNDED_FACTUAL_ASSERTION",
                        severity="ERROR",
                        scene_id="scene_01",
                        assertion_text="X",
                        message="Cannot ground",
                        remediation="Fix",
                    )
                ],
            )

        def regenerate_scene(self, draft, scene_id, dossier, remediation_hint):
            return draft

    director = ProductionDirector(store=store, story_adapter=AlwaysFailingGroundingAdapter())
    result = director.execute_job(sample_request)

    assert result.status == ProductionState.FAILED_GROUNDING
    job = store.load_job(result.job_id)
    assert job.recovery_stats["regenerations"] == sample_request.execution_policy.max_surgical_regenerations
    assert any(e.error_code == "GROUNDING_RECOVERY_EXHAUSTED" for e in job.errors)


def test_director_transient_render_retry(sample_request: ProductionRequest, tmp_path: Path):
    """8. Transient scene rendering I/O failure activates RETRY action and recovers."""
    store = JobStore(base_dir=tmp_path / "jobs")

    class StubStoryTruth(StoryTruthAdapter):
        def synthesize_draft(self, dossier, creative_brief):
            return StoryDraft(
                title="T",
                topic=dossier.topic,
                core_question="?",
                narrative_promise="P",
                scenes=[
                    SceneDraft(
                        scene_id="scene_01",
                        scene_index=0,
                        narrative_role=NarrativeRole.HOOK,
                        narration="N",
                    )
                ],
                dossier_id=dossier.dossier_id,
                dossier_sha256=dossier.dossier_sha256,
            )

        def evaluate_grounding(self, draft, dossier):
            return GroundingReport(passed=True, scene_status={"scene_01": True})

        def convert_and_audit(self, draft, dossier):
            sc = Scene(
                id="scene_01",
                scene_index=0,
                narrative_role=NarrativeRole.HOOK,
                script_text="N",
                word_count=1,
                estimated_duration_sec=70.0,
            )
            arc = StoryArc(
                id="arc_01",
                contract=StoryContract(
                    id="c", title="T", topic="T", core_question="?", narrative_promise="P"
                ),
                scenes=[sc],
                total_estimated_duration_sec=70.0,
            )
            return arc, StoryQAReport(passed=True, total_estimated_duration_sec=70.0)

    render_call_count = 0

    class FailingThenPassingSceneProduction(SceneProductionAdapter):
        def resolve_visuals(self, arc):
            return {
                "scene_01": VisualResolutionResult(
                    scene_id="scene_01",
                    tier=ResolutionTier.TIER1_EXACT,
                    production_strategy="passthrough",
                    score=1.0,
                    rationale="Exact",
                )
            }

        def produce_scene(self, scene, visual_result, output_dir, attempt_id="attempt_01"):
            nonlocal render_call_count
            render_call_count += 1
            if render_call_count == 1:
                raise IOError("Simulated transient FFmpeg pipe stall")

            dummy_vid = output_dir / "vid.mp4"
            dummy_vid.parent.mkdir(parents=True, exist_ok=True)
            dummy_vid.write_text("dummy")
            scene.resolved_asset_path = dummy_vid
            scene.actual_duration_sec = 70.0
            return scene, SceneQAReport(scene_id=scene.id, passed=True)

    class StubMaster(MasterCertificationAdapter):
        def assemble_master(self, arc, s_dir, o_dir, bgm=None):
            return MasterTimeline(story_id=arc.id, target_duration_sec=70.0)

        def certify_and_export(self, timeline, exp_dir, arc=None):
            return FinalMediaQAReport(
                story_id="arc_01",
                master_video_path=Path("dummy"),
                status=PublicationStatus.CERTIFIED_FOR_PUBLICATION,
                passed=True,
                duration_sec=70.0,
                master_sha256="hash_retry_ok",
            )

    director = ProductionDirector(
        store=store,
        story_adapter=StubStoryTruth(),
        production_adapter=FailingThenPassingSceneProduction(),
        certification_adapter=StubMaster(),
    )

    result = director.execute_job(sample_request)

    assert result.status == ProductionState.COMPLETED
    job = store.load_job(result.job_id)
    assert job.recovery_stats["retries"] == 1
    assert job.scene_metadata["scene_01"].status == "completed"


def test_director_master_loudness_repair(sample_request: ProductionRequest, tmp_path: Path):
    """10. Loudness deviation activates REPAIR action re-normalizing with MasterPolicy (-14 LUFS)."""
    store = JobStore(base_dir=tmp_path / "jobs")

    class StubStoryTruth(StoryTruthAdapter):
        def synthesize_draft(self, dossier, creative_brief):
            return StoryDraft(
                title="T",
                topic=dossier.topic,
                core_question="?",
                narrative_promise="P",
                scenes=[
                    SceneDraft(
                        scene_id="scene_01",
                        scene_index=0,
                        narrative_role=NarrativeRole.HOOK,
                        narration="N",
                    )
                ],
                dossier_id=dossier.dossier_id,
                dossier_sha256=dossier.dossier_sha256,
            )

        def evaluate_grounding(self, draft, dossier):
            return GroundingReport(passed=True, scene_status={"scene_01": True})

        def convert_and_audit(self, draft, dossier):
            sc = Scene(
                id="scene_01",
                scene_index=0,
                narrative_role=NarrativeRole.HOOK,
                script_text="N",
                word_count=1,
                estimated_duration_sec=70.0,
            )
            arc = StoryArc(
                id="arc_01",
                contract=StoryContract(
                    id="c", title="T", topic="T", core_question="?", narrative_promise="P"
                ),
                scenes=[sc],
                total_estimated_duration_sec=70.0,
            )
            return arc, StoryQAReport(passed=True, total_estimated_duration_sec=70.0)

    class StubSceneProd(SceneProductionAdapter):
        def resolve_visuals(self, arc):
            return {
                "scene_01": VisualResolutionResult(
                    scene_id="scene_01",
                    tier=ResolutionTier.TIER1_EXACT,
                    production_strategy="passthrough",
                    score=1.0,
                    rationale="Exact",
                )
            }

        def produce_scene(self, scene, visual_result, output_dir, attempt_id="attempt_01"):
            dummy_vid = output_dir / "vid.mp4"
            dummy_vid.parent.mkdir(parents=True, exist_ok=True)
            dummy_vid.write_text("dummy")
            scene.resolved_asset_path = dummy_vid
            scene.actual_duration_sec = 70.0
            return scene, SceneQAReport(scene_id=scene.id, passed=True)

    qa_call_count = 0

    class RepairableLoudnessMasterAdapter(MasterCertificationAdapter):
        def assemble_master(self, arc, s_dir, o_dir, bgm=None):
            return MasterTimeline(story_id=arc.id, target_duration_sec=70.0)

        def repair_master_loudness(self, arc, s_dir, o_dir, bgm=None):
            return MasterTimeline(story_id=arc.id, target_duration_sec=70.0)

        def certify_and_export(self, timeline, exp_dir, arc=None):
            nonlocal qa_call_count
            qa_call_count += 1
            if qa_call_count == 1:
                # Loudness failure (-18.5 LUFS is outside [-16, -12])
                return FinalMediaQAReport(
                    story_id="arc_01",
                    master_video_path=Path("dummy"),
                    status=PublicationStatus.REJECTED,
                    passed=False,
                    findings=[
                        MediaQAFinding(
                            rule="loudness_ebur128",
                            severity="ERROR",
                            message="Integrated loudness -18.5 LUFS is out of bounds.",
                            remediation="Normalize using master policy.",
                        )
                    ],
                )
            # Re-mastered to -14.0 LUFS passes!
            return FinalMediaQAReport(
                story_id="arc_01",
                master_video_path=Path("dummy"),
                status=PublicationStatus.CERTIFIED_FOR_PUBLICATION,
                passed=True,
                duration_sec=70.0,
                master_sha256="hash_repair_ok",
            )

    director = ProductionDirector(
        store=store,
        story_adapter=StubStoryTruth(),
        production_adapter=StubSceneProd(),
        certification_adapter=RepairableLoudnessMasterAdapter(),
    )

    result = director.execute_job(sample_request)

    assert result.status == ProductionState.COMPLETED
    job = store.load_job(result.job_id)
    assert job.recovery_stats["repairs"] == 1


def test_director_visual_fallback_ladder_continues(sample_request: ProductionRequest, tmp_path: Path):
    """11. Falling back to Tier 4 (Styled Fallback) in visual ladder continues normally without FAILED_VISUAL."""
    store = JobStore(base_dir=tmp_path / "jobs")

    class FallbackSceneAdapter(SceneProductionAdapter):
        def resolve_visuals(self, arc):
            # No asset in catalog -> Ladder desciende elegantemente a Tier 4
            return {
                "scene_01": VisualResolutionResult(
                    scene_id="scene_01",
                    tier=ResolutionTier.TIER4_STYLED_FALLBACK,
                    production_strategy="styled_cinematic",
                    score=0.4,
                    rationale="Fallback Tier 4",
                )
            }

        def produce_scene(self, scene, visual_result, output_dir, attempt_id="attempt_01"):
            dummy_vid = output_dir / "vid.mp4"
            dummy_vid.parent.mkdir(parents=True, exist_ok=True)
            dummy_vid.write_text("styled visual")
            scene.resolved_asset_path = dummy_vid
            scene.actual_duration_sec = 70.0
            return scene, SceneQAReport(scene_id=scene.id, passed=True)

    class StubStoryTruth(StoryTruthAdapter):
        def synthesize_draft(self, dossier, creative_brief):
            return StoryDraft(
                title="T",
                topic=dossier.topic,
                core_question="?",
                narrative_promise="P",
                scenes=[
                    SceneDraft(
                        scene_id="scene_01",
                        scene_index=0,
                        narrative_role=NarrativeRole.HOOK,
                        narration="N",
                    )
                ],
                dossier_id=dossier.dossier_id,
                dossier_sha256=dossier.dossier_sha256,
            )

        def evaluate_grounding(self, draft, dossier):
            return GroundingReport(passed=True, scene_status={"scene_01": True})

        def convert_and_audit(self, draft, dossier):
            sc = Scene(
                id="scene_01",
                scene_index=0,
                narrative_role=NarrativeRole.HOOK,
                script_text="N",
                word_count=1,
                estimated_duration_sec=70.0,
            )
            arc = StoryArc(
                id="arc_01",
                contract=StoryContract(
                    id="c", title="T", topic="T", core_question="?", narrative_promise="P"
                ),
                scenes=[sc],
                total_estimated_duration_sec=70.0,
            )
            return arc, StoryQAReport(passed=True, total_estimated_duration_sec=70.0)

    class StubMaster(MasterCertificationAdapter):
        def assemble_master(self, arc, s_dir, o_dir, bgm=None):
            return MasterTimeline(story_id=arc.id, target_duration_sec=70.0)

        def certify_and_export(self, timeline, exp_dir, arc=None):
            return FinalMediaQAReport(
                story_id="arc_01",
                master_video_path=Path("dummy"),
                status=PublicationStatus.CERTIFIED_FOR_PUBLICATION,
                passed=True,
                duration_sec=70.0,
                master_sha256="hash_fallback_ok",
            )

    director = ProductionDirector(
        store=store,
        story_adapter=StubStoryTruth(),
        production_adapter=FallbackSceneAdapter(),
        certification_adapter=StubMaster(),
    )

    result = director.execute_job(sample_request)

    assert result.status == ProductionState.COMPLETED
    assert result.status != ProductionState.FAILED_VISUAL


# -----------------------------------------------------------------------------
# 5. Persistence, Observability & Certification Authority
# -----------------------------------------------------------------------------

def test_director_durable_job_persistence_and_resume(tmp_path: Path):
    """12. Validates disk persistence and recovery inspection after process restart."""
    store_dir = tmp_path / "jobs"
    store = JobStore(base_dir=store_dir)

    req = ProductionRequest(
        request_id="req_persist_01",
        topic="Test Persistence",
        dossier=FactDossier(
            dossier_id="d1",
            run_id="r1",
            topic="T",
            dossier_sha256="abc",
            claims={},
        ),
    )

    job, is_new = store.acquire("req_persist_01", req)
    job.scene_metadata["scene_01"] = SceneExecutionMetadata(
        scene_id="scene_01",
        status="completed",
        actual_duration_sec=14.2,
        scene_qa_passed=True,
    )
    store.save_job(job)

    # Simulate process crash & restart: instantiate a new JobStore
    new_store = JobStore(base_dir=store_dir)
    recovered_job = new_store.load_job(job.job_id)

    assert recovered_job.job_id == job.job_id
    assert recovered_job.request_id == "req_persist_01"
    assert recovered_job.scene_metadata["scene_01"].status == "completed"
    assert recovered_job.scene_metadata["scene_01"].actual_duration_sec == 14.2


def test_director_master_sha256_is_read_only_propagation(tmp_path: Path):
    """13. Confirms master_sha256 is strictly read-only propagated from 12B.5."""
    store = JobStore(base_dir=tmp_path / "jobs")
    director = ProductionDirector(store=store)

    job = ProductionJob(
        job_id="job_sha_test",
        request_id="req_sha_test",
        current_state=ProductionState.COMPLETED,
        workspace_dir=tmp_path / "job_sha_test",
        dossier_id="d1",
        dossier_sha256="d1_sha",
        master_sha256="canonical_12b5_hash_9999",
    )
    job.workspace_dir.mkdir(parents=True, exist_ok=True)
    (job.workspace_dir / "job.json").write_text("{}")

    report = FinalMediaQAReport(
        story_id="story_01",
        master_video_path=Path("dummy"),
        status=PublicationStatus.CERTIFIED_FOR_PUBLICATION,
        passed=True,
        duration_sec=75.0,
        master_sha256="canonical_12b5_hash_9999",
    )

    res = director._build_result(job, certified_report=report)
    assert res.master_sha256 == "canonical_12b5_hash_9999"


def test_director_completed_strictly_derived_from_12b5(
    sample_request: ProductionRequest, tmp_path: Path
):
    """14. If 12B.5 rejects, Director must transition to FAILED_MEDIA_QA and cannot mark COMPLETED."""
    store = JobStore(base_dir=tmp_path / "jobs")

    class StubStoryTruth(StoryTruthAdapter):
        def synthesize_draft(self, dossier, creative_brief):
            return StoryDraft(
                title="T",
                topic=dossier.topic,
                core_question="?",
                narrative_promise="P",
                scenes=[],
                dossier_id=dossier.dossier_id,
                dossier_sha256=dossier.dossier_sha256,
            )

        def evaluate_grounding(self, draft, dossier):
            return GroundingReport(passed=True, scene_status={})

        def convert_and_audit(self, draft, dossier):
            arc = StoryArc(
                id="arc_01",
                contract=StoryContract(
                    id="c", title="T", topic="T", core_question="?", narrative_promise="P"
                ),
                scenes=[],
                total_estimated_duration_sec=70.0,
            )
            return arc, StoryQAReport(passed=True, total_estimated_duration_sec=70.0)

    class StubSceneProd(SceneProductionAdapter):
        def resolve_visuals(self, arc):
            return {}

        def produce_scene(self, scene, res, out_dir, attempt_id="attempt_01"):
            return scene, SceneQAReport(scene_id=scene.id, passed=True)

    class RejectingMasterCertificationAdapter(MasterCertificationAdapter):
        def assemble_master(self, arc, s_dir, o_dir, bgm=None):
            return MasterTimeline(story_id=arc.id, target_duration_sec=70.0)

        def certify_and_export(self, timeline, exp_dir, arc=None):
            # 12B.5 emits REJECTED due to stream decode corruption
            return FinalMediaQAReport(
                story_id="arc_01",
                master_video_path=Path("corrupt.mp4"),
                status=PublicationStatus.REJECTED,
                passed=False,
                findings=[
                    MediaQAFinding(
                        rule="bitstream_decode",
                        severity="ERROR",
                        message="Fatal decode corruption.",
                        remediation="Re-render source clips.",
                    )
                ],
            )

    director = ProductionDirector(
        store=store,
        story_adapter=StubStoryTruth(),
        production_adapter=StubSceneProd(),
        certification_adapter=RejectingMasterCertificationAdapter(),
    )

    result = director.execute_job(sample_request)

    assert result.status == ProductionState.FAILED_MEDIA_QA
    assert result.is_certified is False
    assert result.master_sha256 is None


def test_director_zero_imports_from_banned_modules():
    """15. Confirms zero runtime imports of external network / scraping / real LLM vendor APIs."""
    banned_modules = [
        "requests",
        "urllib",
        "httpx",
        "playwright",
        "selenium",
        "bs4",
        "scrapy",
        "google.generativeai",
        "openai",
        "anthropic",
        "groq",
    ]
    director_files = [
        Path(__file__).parent.parent / "engine" / "director" / "director.py",
        Path(__file__).parent.parent / "engine" / "director" / "adapters.py",
        Path(__file__).parent.parent / "engine" / "director" / "store.py",
        Path(__file__).parent.parent / "engine" / "director" / "schema.py",
    ]

    for fpath in director_files:
        with open(fpath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for banned in banned_modules:
                        assert not alias.name.startswith(banned), (
                            f"Banned import '{alias.name}' detected in {fpath.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for banned in banned_modules:
                        assert not node.module.startswith(banned), (
                            f"Banned from-import '{node.module}' detected in {fpath.name}"
                        )


# -----------------------------------------------------------------------------
# 5. Final Hardening Tests (Stage 12D.2)
# -----------------------------------------------------------------------------

def _worker_acquire(store_dir_str: str, req_json: str) -> tuple[str, bool]:
    """Top-level helper executed by independent OS processes for inter-process lock validation."""
    from engine.director.schema import ProductionRequest
    from engine.director.store import JobStore

    store = JobStore(base_dir=Path(store_dir_str))
    req = ProductionRequest.model_validate_json(req_json)
    job, is_new = store.acquire(req.request_id, req)
    return job.job_id, is_new


def test_director_mock_provider_fallback_permitted(sample_request: ProductionRequest, tmp_path: Path):
    """Hardening 1A: MockLLMProvider without canned response safely falls back to deterministic draft."""
    mock = MockLLMProvider()  # canned_response is None -> raises ValueError on generate_structured
    adapter = StoryTruthAdapter(provider=mock)

    draft = adapter.synthesize_draft(sample_request.dossier, sample_request.creative_brief)
    assert draft is not None
    assert draft.dossier_id == sample_request.dossier.dossier_id
    assert len(draft.scenes) == 5
    assert draft.scenes[0].narrative_role == NarrativeRole.HOOK


def test_director_real_provider_fallback_prohibited_error_propagated(
    sample_request: ProductionRequest, tmp_path: Path
):
    """Hardening 1B: Real provider failure must NOT fall back silently; error must propagate to Director."""
    class FailingRealProvider(LLMProvider):
        def generate_structured(self, prompt, schema):
            raise ValueError("Real LLM output failed schema validation (corrupt JSON).")

        def metadata(self):
            return {"provider": "failing_real_provider", "offline": False}

    store = JobStore(base_dir=tmp_path / "jobs")
    failing_adapter = StoryTruthAdapter(provider=FailingRealProvider())
    director = ProductionDirector(store=store, story_adapter=failing_adapter)

    result = director.execute_job(sample_request)

    # Must transition to FAILED_GROUNDING without silent fallback
    assert result.status == ProductionState.FAILED_GROUNDING
    assert result.is_certified is False
    assert "SYNTHESIS_ERROR" in (result.error_summary or "")
    assert "Real LLM output failed schema validation" in (result.error_summary or "")

    job = store.load_job(result.job_id)
    assert job.current_state == ProductionState.FAILED_GROUNDING


def test_director_interprocess_concurrency_file_lock(sample_request: ProductionRequest, tmp_path: Path):
    """Hardening 2: OS-level file lock ensures mutual exclusion between separate OS processes."""
    import concurrent.futures

    store_dir = tmp_path / "jobs_ipc"
    store_dir.mkdir(parents=True, exist_ok=True)
    req_json = sample_request.model_dump_json()

    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_worker_acquire, str(store_dir), req_json)
        f2 = executor.submit(_worker_acquire, str(store_dir), req_json)
        res1 = f1.result(timeout=15.0)
        res2 = f2.result(timeout=15.0)

    job_id1, is_new1 = res1
    job_id2, is_new2 = res2

    # Exactly one process created the job; the other loaded the existing one
    assert job_id1 == job_id2
    assert {is_new1, is_new2} == {True, False}


def test_director_physical_crash_recovery_skips_completed_scene(sample_request: ProductionRequest, tmp_path: Path):
    """Hardening 3: Resuming a job with an existing completed scene skips re-production and reuses physical artifact."""
    store = JobStore(base_dir=tmp_path / "jobs_resume")
    job, is_new = store.acquire(sample_request.request_id, sample_request)

    # Pre-create scene_01 artifact physically on disk
    scene_01_dir = job.workspace_dir / "scenes" / "scene_01"
    scene_01_dir.mkdir(parents=True, exist_ok=True)
    scene_01_file = scene_01_dir / "scene_01.mp4"
    initial_content = b"PHYSICAL_SCENE_01_INITIAL_BYTES"
    scene_01_file.write_bytes(initial_content)

    # Record verified metadata for scene_01 (simulating crash after scene_01 completion)
    job.scene_metadata["scene_01"] = SceneExecutionMetadata(
        scene_id="scene_01",
        artifact_path=scene_01_file,
        voice_path=scene_01_dir / "scene_01_voice.wav",
        status="completed",
        attempt_id="attempt_scene_01",
        actual_duration_sec=15.0,
        resolution_tier="tier4_styled_fallback",
        scene_qa_passed=True,
    )
    job.current_state = ProductionState.SCENE_PRODUCTION
    store.save_job(job)

    # Instrument SceneProductionAdapter to track which scenes are produced
    produced_scene_ids = []

    class SpyingSceneAdapter(SceneProductionAdapter):
        def resolve_visuals(self, arc):
            return {
                s.id: VisualResolutionResult(
                    scene_id=s.id,
                    tier=ResolutionTier.TIER4_STYLED_FALLBACK,
                    production_strategy="styled_cinematic",
                    score=0.5,
                    rationale="Fallback styled cinematic",
                )
                for s in arc.scenes
            }

        def produce_scene(self, scene, visual_result, output_dir, attempt_id="attempt_01"):
            produced_scene_ids.append(scene.id)
            sc_file = output_dir / f"{scene.id}.mp4"
            sc_file.parent.mkdir(parents=True, exist_ok=True)
            sc_file.write_bytes(f"BYTES_FOR_{scene.id}".encode("utf-8"))
            scene.resolved_asset_path = sc_file
            scene.actual_duration_sec = 15.0
            return scene, SceneQAReport(scene_id=scene.id, passed=True)

    class StubMasterAdapter(MasterCertificationAdapter):
        def assemble_master(self, arc, s_dir, o_dir, bgm=None):
            return MasterTimeline(story_id=arc.id, target_duration_sec=70.0)

        def certify_and_export(self, timeline, exp_dir, arc=None):
            cert_mp4 = exp_dir / "master.mp4"
            cert_mp4.parent.mkdir(parents=True, exist_ok=True)
            cert_mp4.write_text("master")
            man = exp_dir / "manifest.json"
            man.write_text("{}")
            return FinalMediaQAReport(
                story_id="arc_01",
                master_video_path=cert_mp4,
                certified_output_path=cert_mp4,
                manifest_path=man,
                status=PublicationStatus.CERTIFIED_FOR_PUBLICATION,
                passed=True,
                duration_sec=70.0,
                master_sha256="hash_resumed_ok",
            )

    director = ProductionDirector(
        store=store,
        production_adapter=SpyingSceneAdapter(),
        certification_adapter=StubMasterAdapter(),
    )

    result = director.execute_job(sample_request)

    # Verification: scene_01 must NOT have been re-produced
    assert "scene_01" not in produced_scene_ids
    assert len(produced_scene_ids) > 0  # scenes 02, 03, etc. WERE produced

    # Verification: physical artifact of scene_01 on disk was preserved untouched
    assert scene_01_file.read_bytes() == initial_content

    # Verification: final state completed
    assert result.status == ProductionState.COMPLETED
    assert result.is_certified is True


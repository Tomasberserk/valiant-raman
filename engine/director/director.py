"""Production Director Engine (Stage 12D.2).

Orchestrates the entire end-to-end production lifecycle governed by the
Production Orchestration Contract (Stage 12D.1):
1. Precondition verification (dossier_sha256 validation via FactIntelligenceEngine).
2. Pure state machine governance with explicit transitions and audit history.
3. Decision ownership for RETRY (I/O), REPAIR (Loudness), and REGENERATE (Grounding).
4. Crash recovery and resume capabilities leveraging durable JobStore.
5. Strict derived authority: COMPLETED iff 12B.5 issues CERTIFIED_FOR_PUBLICATION.
6. Zero recalculation: master_sha256 is strictly read-only propagated from 12B.5.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.director.adapters import (
    MasterCertificationAdapter,
    SceneProductionAdapter,
    StoryTruthAdapter,
)
from engine.director.schema import (
    ProductionJob,
    ProductionRequest,
    ProductionResult,
    ProductionState,
    RecoveryAction,
    SceneExecutionMetadata,
    StageError,
    StateTransitionRecord,
)
from engine.director.store import JobStore
from engine.story.fact_intelligence import FactIntelligenceEngine
from engine.story.schema import PublicationStatus


class ProductionDirector:
    """Central orchestrator for end-to-end video production runs."""

    def __init__(
        self,
        store: Optional[JobStore] = None,
        story_adapter: Optional[StoryTruthAdapter] = None,
        production_adapter: Optional[SceneProductionAdapter] = None,
        certification_adapter: Optional[MasterCertificationAdapter] = None,
    ):
        self.store = store or JobStore()
        self.story_adapter = story_adapter or StoryTruthAdapter()
        self.production_adapter = production_adapter or SceneProductionAdapter()
        self.certification_adapter = certification_adapter or MasterCertificationAdapter()

    def execute_job(self, request: ProductionRequest) -> ProductionResult:
        """One-Command Execution entrypoint with concurrency-safe idempotency."""
        # 1. Acquire atomic job instance
        job, is_new = self.store.acquire(request.request_id, request)

        # Idempotency return: if already finished or fatal precondition, return immediately
        if not is_new and job.current_state in (
            ProductionState.COMPLETED,
            ProductionState.FAILED_PRECONDITION,
        ):
            return self._build_result(job)

        # 2. Check Preconditions (Strict dossier_sha256 validation)
        if not self._check_preconditions(request, job):
            return self._build_result(job)

        # 3. STORY_SYNTHESIS
        self._transition(job, ProductionState.STORY_SYNTHESIS, trigger="preconditions_verified")
        try:
            draft = self.story_adapter.synthesize_draft(request.dossier, request.creative_brief)
        except Exception as e:
            self._record_error(job, stage="story_synthesis", code="SYNTHESIS_ERROR", message=str(e))
            self._transition(job, ProductionState.FAILED_GROUNDING, trigger="synthesis_exception")
            return self._build_result(job)

        # 4. CLAIM_GROUNDING & Surgical Regeneration (Director-governed REGENERATE)
        self._transition(job, ProductionState.CLAIM_GROUNDING, trigger="draft_synthesized")
        grounding_report = self.story_adapter.evaluate_grounding(draft, request.dossier)

        if not grounding_report.passed:
            regenerations = 0
            while (
                not grounding_report.passed
                and regenerations < request.execution_policy.max_surgical_regenerations
            ):
                regenerations += 1
                job.recovery_stats["regenerations"] += 1
                job.current_attempt_id = f"attempt_regen_{regenerations:02d}"

                failing_scenes = [
                    sid for sid, ok in grounding_report.scene_status.items() if not ok
                ]
                if not failing_scenes:
                    break

                for sid in failing_scenes:
                    hints = "; ".join(
                        f.remediation for f in grounding_report.findings if f.scene_id == sid
                    )
                    draft = self.story_adapter.regenerate_scene(
                        draft=draft,
                        scene_id=sid,
                        dossier=request.dossier,
                        remediation_hint=hints,
                    )

                grounding_report = self.story_adapter.evaluate_grounding(draft, request.dossier)

            if not grounding_report.passed:
                err_msgs = [f.message for f in grounding_report.findings if f.severity == "ERROR"]
                self._record_error(
                    job,
                    stage="claim_grounding",
                    code="GROUNDING_RECOVERY_EXHAUSTED",
                    message="; ".join(err_msgs),
                )
                self._transition(
                    job,
                    ProductionState.FAILED_GROUNDING,
                    trigger="max_regenerations_exceeded",
                    details=f"Failed after {regenerations} regenerations",
                )
                return self._build_result(job)

        # 5. STORY_QA_AUDIT
        self._transition(job, ProductionState.STORY_QA_AUDIT, trigger="grounding_passed")
        try:
            story_arc, qa_report = self.story_adapter.convert_and_audit(draft, request.dossier)
        except Exception as e:
            self._record_error(job, stage="story_qa", code="CONVERSION_FAILURE", message=str(e))
            self._transition(job, ProductionState.FAILED_STORY_QA, trigger="conversion_exception")
            return self._build_result(job)

        if not qa_report.passed:
            qa_errs = [f.message for f in qa_report.findings if f.severity == "ERROR"]
            self._record_error(
                job,
                stage="story_qa",
                code="STORY_QA_FAILED",
                message="; ".join(qa_errs),
            )
            self._transition(job, ProductionState.FAILED_STORY_QA, trigger="contract_invariants_violated")
            return self._build_result(job)

        # Persist StoryArc artifact
        arc_path = job.workspace_dir / "artifacts" / "story_arc.json"
        with open(arc_path, "w", encoding="utf-8") as f:
            f.write(story_arc.model_dump_json(indent=2))
        job.story_arc_path = arc_path

        # 6. VISUAL_RESOLUTION (Graceful ladder fallback to Tier 4)
        self._transition(job, ProductionState.VISUAL_RESOLUTION, trigger="story_qa_passed")
        try:
            visual_results = self.production_adapter.resolve_visuals(story_arc)
        except Exception as e:
            self._record_error(job, stage="visual_resolution", code="CONTRACT_CRASH", message=str(e))
            self._transition(job, ProductionState.FAILED_VISUAL, trigger="visual_resolver_crash")
            return self._build_result(job)

        # 7. SCENE_PRODUCTION (Director-governed RETRY loop)
        self._transition(job, ProductionState.SCENE_PRODUCTION, trigger="visuals_resolved")
        produced_scenes = []

        for scene in story_arc.scenes:
            # Check existing completed scene for crash recovery
            existing_meta = job.scene_metadata.get(scene.id)
            if (
                existing_meta
                and existing_meta.scene_qa_passed
                and existing_meta.artifact_path
                and Path(existing_meta.artifact_path).exists()
            ):
                produced_scenes.append(scene)
                continue

            scene_success = False
            retries = 0

            while (
                not scene_success
                and retries < request.execution_policy.max_scene_retries
            ):
                retries += 1
                job.current_attempt_id = f"attempt_scene_{retries:02d}"

                try:
                    scenes_dir = job.workspace_dir / "scenes"
                    produced_scene, scene_qa = self.production_adapter.produce_scene(
                        scene=scene,
                        visual_result=visual_results[scene.id],
                        output_dir=scenes_dir,
                        attempt_id=job.current_attempt_id,
                    )

                    if scene_qa.passed:
                        scene_success = True
                        produced_scenes.append(produced_scene)

                        # Record verified per-scene operational metadata
                        job.scene_metadata[scene.id] = SceneExecutionMetadata(
                            scene_id=scene.id,
                            artifact_path=produced_scene.resolved_asset_path,
                            voice_path=produced_scene.voice_audio_path,
                            status="completed",
                            attempt_id=job.current_attempt_id,
                            actual_duration_sec=produced_scene.actual_duration_sec,
                            resolution_tier=produced_scene.resolution_tier,
                            scene_qa_passed=True,
                        )
                        job.produced_scenes_count = len(
                            [m for m in job.scene_metadata.values() if m.scene_qa_passed]
                        )
                        self.store.save_job(job)
                    else:
                        job.recovery_stats["retries"] += 1
                except Exception:
                    job.recovery_stats["retries"] += 1

            if not scene_success:
                self._record_error(
                    job,
                    stage="scene_production",
                    code="SCENE_RETRY_EXHAUSTED",
                    message=f"Scene '{scene.id}' failed after {retries} retries.",
                )
                self._transition(job, ProductionState.FAILED_SCENE, trigger="max_scene_retries_exceeded")
                return self._build_result(job)

        # 8. MASTER_ASSEMBLY
        self._transition(job, ProductionState.MASTER_ASSEMBLY, trigger="all_scenes_produced")
        try:
            scenes_dir = job.workspace_dir / "scenes"
            master_dir = job.workspace_dir / "master"
            master_timeline = self.certification_adapter.assemble_master(
                story_arc,
                scenes_dir,
                master_dir,
            )
            job.master_video_path = master_timeline.master_video_path
        except Exception as e:
            self._record_error(job, stage="master_assembly", code="ASSEMBLY_FAILED", message=str(e))
            self._transition(job, ProductionState.FAILED_MASTER, trigger="assembly_exception")
            return self._build_result(job)

        # 9. FINAL_MEDIA_QA (Director-governed REPAIR loop)
        self._transition(job, ProductionState.FINAL_MEDIA_QA, trigger="master_assembled")
        certified_dir = job.workspace_dir / "certified"
        qa_report = self.certification_adapter.certify_and_export(
            master_timeline,
            certified_dir,
            story_arc,
        )

        if not qa_report.passed:
            # Check for recoverable loudness repair
            has_loudness_error = any(f.rule == "loudness_ebur128" for f in qa_report.findings)
            if (
                has_loudness_error
                and job.recovery_stats["repairs"] < request.execution_policy.max_master_repairs
            ):
                job.recovery_stats["repairs"] += 1
                job.current_attempt_id = "attempt_repair_loudness"
                try:
                    repaired_dir = job.workspace_dir / "master_repaired"
                    master_timeline = self.certification_adapter.repair_master_loudness(
                        story_arc,
                        scenes_dir,
                        repaired_dir,
                    )
                    qa_report = self.certification_adapter.certify_and_export(
                        master_timeline,
                        certified_dir,
                        story_arc,
                    )
                except Exception:
                    pass

        # 10. COMPLETED (Derived strictly from 12B.5 certification)
        if qa_report.status == PublicationStatus.CERTIFIED_FOR_PUBLICATION:
            # Read-only propagation from 12B.5
            job.master_video_path = qa_report.certified_output_path
            job.manifest_path = qa_report.manifest_path
            job.master_sha256 = qa_report.master_sha256

            self._transition(job, ProductionState.COMPLETED, trigger="12b5_certified_for_publication")
            return self._build_result(job, certified_report=qa_report)

        # Media QA rejection terminal failure
        err_msgs = [f.message for f in qa_report.findings if f.severity == "ERROR"]
        self._record_error(
            job,
            stage="final_media_qa",
            code="MEDIA_QA_REJECTED",
            message="; ".join(err_msgs) if err_msgs else "Master video rejected by 12B.5.",
        )
        self._transition(job, ProductionState.FAILED_MEDIA_QA, trigger="media_qa_rejection")
        return self._build_result(job, certified_report=qa_report)

    def _check_preconditions(self, request: ProductionRequest, job: ProductionJob) -> bool:
        """Validate input dossier hash against canonical 12C.1 definition without re-inventing hashing."""
        try:
            calculated_hash = FactIntelligenceEngine.compute_dossier_hash(
                request.dossier.model_dump()
            )
        except Exception as e:
            self._record_error(job, stage="precondition", code="DOSSIER_HASH_COMPUTE_ERROR", message=str(e))
            self._transition(job, ProductionState.FAILED_PRECONDITION, trigger="hash_compute_exception")
            return False

        if request.dossier.dossier_sha256 != calculated_hash:
            msg = (
                f"FactDossier hash mismatch. Sealed: '{request.dossier.dossier_sha256}', "
                f"Calculated canonical: '{calculated_hash}'."
            )
            self._record_error(job, stage="precondition", code="DOSSIER_HASH_MISMATCH", message=msg)
            self._transition(job, ProductionState.FAILED_PRECONDITION, trigger="hash_mismatch", details=msg)
            return False

        if not request.dossier.claims:
            msg = "FactDossier has 0 claims."
            self._record_error(job, stage="precondition", code="DOSSIER_EMPTY_CLAIMS", message=msg)
            self._transition(job, ProductionState.FAILED_PRECONDITION, trigger="empty_claims", details=msg)
            return False

        return True

    def _transition(
        self,
        job: ProductionJob,
        to_state: ProductionState,
        trigger: str,
        details: Optional[str] = None,
    ) -> None:
        """Record and persist an explicit state transition."""
        record = StateTransitionRecord(
            from_state=job.current_state,
            to_state=to_state,
            attempt_id=job.current_attempt_id,
            trigger=trigger,
            details=details,
        )
        job.state_history.append(record)
        job.current_state = to_state
        self.store.save_job(job)

    def _record_error(
        self,
        job: ProductionJob,
        stage: str,
        code: str,
        message: str,
        remediation: Optional[str] = None,
    ) -> None:
        """Record an error in the job diagnostic history."""
        err = StageError(
            stage=stage,
            error_code=code,
            message=message,
            remediation_hint=remediation,
            attempt_id=job.current_attempt_id,
        )
        job.errors.append(err)
        self.store.save_job(job)

    def _build_result(
        self,
        job: ProductionJob,
        certified_report: Optional[Any] = None,
    ) -> ProductionResult:
        """Assemble immutable ProductionResult contract."""
        is_certified = (job.current_state == ProductionState.COMPLETED)
        dur = float(certified_report.duration_sec) if certified_report and hasattr(certified_report, "duration_sec") else 0.0

        err_summary = (
            "; ".join(f"[{e.error_code}] {e.stage}: {e.message}" for e in job.errors)
            if job.errors
            else None
        )

        return ProductionResult(
            job_id=job.job_id,
            request_id=job.request_id,
            status=job.current_state,
            is_certified=is_certified,
            certified_master_path=job.master_video_path if is_certified else None,
            manifest_path=job.manifest_path if is_certified else None,
            master_sha256=job.master_sha256 if is_certified else None,
            total_physical_duration_sec=dur,
            error_summary=err_summary,
            job_persisted_path=job.workspace_dir / "job.json",
        )

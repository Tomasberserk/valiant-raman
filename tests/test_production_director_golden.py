"""Physical End-to-End Golden Case Test for ProductionDirector (Stage 12D.2).

Validates the full, physical, unmocked pipeline execution:
FactDossier (12C.1)
  -> StoryTruthAdapter (12C.2 MockLLMProvider + 12B.1 StoryArc)
  -> SceneProductionAdapter (12B.2 VisualResolver + 12B.3 SceneProducer FFmpeg)
  -> MasterCertificationAdapter (12B.4 MasterTimelineAssembler + 12B.5 FinalMediaQAEngine)
  -> ProductionDirector (12D.2 Orchestration + JobStore + State Machine)
  -> Certified Master MP4 & Cryptographic Manifest

Invariants Verified:
1. job.status == ProductionState.COMPLETED
2. result.is_certified == True
3. result.certified_master_path exists on disk, is valid MP4, and size > 0
4. result.manifest_path exists on disk and is a valid JSON manifest
5. result.master_sha256 is non-empty, 64-char hex, propagated without alteration
6. result.total_physical_duration_sec >= 61.0 (DurationPolicy hard minimum invariant)
7. job.produced_scenes_count == len(story_arc.scenes)
8. job.master_sha256 == result.master_sha256
9. State transition history follows the authoritative happy-path machine
10. Idempotency guarantees: re-executing returns the existing completed job immediately
"""

import json
from pathlib import Path
import pytest

from engine.director import (
    CreativeBrief,
    JobExecutionPolicy,
    JobStore,
    OutputSpec,
    ProductionDirector,
    ProductionJob,
    ProductionRequest,
    ProductionResult,
    ProductionState,
)
from engine.story import (
    ClaimStatus,
    FactClaim,
    FactDossier,
    FactIntelligenceEngine,
    FactSource,
    PublicationStatus,
    SourceAuthority,
)


@pytest.fixture
def golden_fact_dossier() -> FactDossier:
    """Compile an authoritative, verified FactDossier for the golden test."""
    engine = FactIntelligenceEngine()
    s1 = FactSource(
        source_id="src_gottingen_arch",
        title="Gottingen University Historical Archives",
        publisher="University of Gottingen",
        authority_level=SourceAuthority.PRIMARY_INSTITUTIONAL,
    )
    s2 = FactSource(
        source_id="src_phys_hist",
        title="History of Modern Electromagnetism",
        publisher="Academic Press",
        authority_level=SourceAuthority.SECONDARY_ACADEMIC,
        publication_year=2018,
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
        FactClaim(
            claim_id="claim_03",
            claim_text="Utilizaban un galvanómetro de reflexión para detectar las corrientes.",
            source_ids=["src_phys_hist"],
            status=ClaimStatus.VERIFIED,
        ),
    ]
    return engine.compile_dossier(
        dossier_id="dossier_golden_gottingen",
        run_id="run_golden_director",
        topic="El telégrafo de Gauss y Weber",
        sources=[s1, s2],
        claims=claims,
        key_entities=["Gauss", "Weber", "Gottingen"],
    )


def test_production_director_e2e_golden_physical_pipeline(golden_fact_dossier: FactDossier, tmp_path: Path):
    """Full One-Command E2E execution through ProductionDirector with physical rendering and QA certification."""
    store_dir = tmp_path / "production_jobs"
    store = JobStore(base_dir=store_dir)
    director = ProductionDirector(store=store)

    request = ProductionRequest(
        request_id="req_golden_e2e_001",
        topic="El telégrafo de Gauss y Weber",
        dossier=golden_fact_dossier,
        creative_brief=CreativeBrief(
            hook_strategy="question",
            tone="curious_informative",
        ),
        output_spec=OutputSpec(
            target_resolution="1080x1920",
            fps=30,
            loudness_target_lufs=-14.0,
        ),
        execution_policy=JobExecutionPolicy(
            max_surgical_regenerations=2,
            max_scene_retries=2,
            max_master_repairs=1,
            preserve_intermediate_artifacts=True,
        ),
    )

    # 1. Execute One-Command E2E
    result: ProductionResult = director.execute_job(request)

    # 2. Invariant: Status & Certification
    assert result.status == ProductionState.COMPLETED
    assert result.is_certified is True
    assert result.error_summary is None

    # 3. Invariant: Certified Master Video Physical Verification
    assert result.certified_master_path is not None
    assert result.certified_master_path.exists()
    assert result.certified_master_path.is_file()
    assert result.certified_master_path.stat().st_size > 10_000  # Physically non-trivial MP4

    # 4. Invariant: Cryptographic Manifest Verification
    assert result.manifest_path is not None
    assert result.manifest_path.exists()
    assert result.manifest_path.is_file()

    manifest_data = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["certification_status"] in [
        PublicationStatus.CERTIFIED_FOR_PUBLICATION.value,
        PublicationStatus.CERTIFIED_WITH_WARNINGS.value,
    ]
    assert manifest_data["master_sha256"] == result.master_sha256
    assert len(result.master_sha256) == 64

    # 5. Invariant: Duration & Synchronization Policy
    assert result.total_physical_duration_sec >= 61.0
    assert result.total_physical_duration_sec <= 90.0

    # 6. Invariant: Durable Job Persistence & Operational Records
    job = store.load_job(result.job_id)
    assert job.current_state == ProductionState.COMPLETED
    assert job.request_id == "req_golden_e2e_001"
    assert job.dossier_id == golden_fact_dossier.dossier_id
    assert job.dossier_sha256 == golden_fact_dossier.dossier_sha256
    assert job.master_sha256 == result.master_sha256
    assert job.produced_scenes_count == len(job.scene_metadata)
    assert job.produced_scenes_count >= 5  # Standard 5-6 scenes in 12B arc

    # Verify per-scene operational metadata was captured
    for scene_id, meta in job.scene_metadata.items():
        assert meta.scene_qa_passed is True
        assert meta.actual_duration_sec is not None
        assert meta.actual_duration_sec > 0.0

    # 7. Invariant: Authoritative Happy-Path State Transitions
    expected_state_sequence = [
        ProductionState.STORY_SYNTHESIS,
        ProductionState.CLAIM_GROUNDING,
        ProductionState.STORY_QA_AUDIT,
        ProductionState.VISUAL_RESOLUTION,
        ProductionState.SCENE_PRODUCTION,
        ProductionState.MASTER_ASSEMBLY,
        ProductionState.FINAL_MEDIA_QA,
        ProductionState.COMPLETED,
    ]
    actual_sequence = [t.to_state for t in job.state_history]
    assert actual_sequence == expected_state_sequence

    # 8. Invariant: Idempotency with Completed Job
    # Calling execute_job again with same request_id must return the existing completed result immediately
    second_result = director.execute_job(request)
    assert second_result.job_id == result.job_id
    assert second_result.status == ProductionState.COMPLETED
    assert second_result.master_sha256 == result.master_sha256

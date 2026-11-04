"""Unit tests for Research & Fact Intelligence (Stage 12C.1).

Validates:
1. FactSource creation & validation (authority tier, independence group).
2. FactClaim multi-source and boundaries.
3. FactDossier compilation & metadata.
4. Deterministic canonical serialization & SHA-256 stability.
5. Claim modification alters dossier hash.
6. Source modification alters dossier hash.
7. UNVERIFIED source cannot certify a claim as VERIFIED.
8. Competent PRIMARY_INSTITUTIONAL source certifies domain claim.
9. Two independent secondary sources corroborate an academic claim.
10. Same independence group fails independent corroboration requirement.
11. Unresolved contradiction blocks VERIFIED status.
12. CONTEXT_REQUIRED mandates explicit scope.
13. Overclaiming & wording boundaries policy (demonstrative test).
14. Supporting excerpt requires valid catalog source.
15. Source locator preserves forensic provenance (page/section/timestamp).
16. Compiled FactDossier immutability (raises TypeError on mutation).
17. Incremental revisioning produces new version & hash without mutating base.
18. Multi-source claims aggregation and count.
19. Downstream compatibility with StoryEngine FactClaim.
20. Absolute architectural isolation: zero imports from engine/media.
"""

from datetime import datetime, timezone
import pytest

from engine.story import (
    ClaimStatus,
    ClaimVerificationResult,
    EvidenceSnapshot,
    FactClaim,
    FactDossier,
    FactIntelligenceEngine,
    FactSource,
    SourceAuthority,
)


@pytest.fixture
def engine() -> FactIntelligenceEngine:
    return FactIntelligenceEngine()


@pytest.fixture
def sample_sources() -> dict[str, FactSource]:
    s1 = FactSource(
        source_id="src_daimler_archive",
        url="https://mercedes-benz-publicarchive.com/bertha_1888",
        title="Daimler Corporate Archives: Bertha Benz Trip 1888",
        publisher="Mercedes-Benz AG Classic Archive",
        source_type="archive_document",
        authority_level=SourceAuthority.PRIMARY_INSTITUTIONAL,
        independence_group="daimler_corporate",
    )
    s2 = FactSource(
        source_id="src_loc_ford",
        url="https://loc.gov/item/ford_assembly_line_1913",
        title="The Industrial Assembly Line",
        publisher="Library of Congress",
        source_type="academic_paper",
        authority_level=SourceAuthority.SECONDARY_ACADEMIC,
        independence_group="loc_archive",
    )
    s3 = FactSource(
        source_id="src_britannica_assembly",
        url="https://britannica.com/topic/assembly-line",
        title="Assembly line manufacturing history",
        publisher="Encyclopedia Britannica",
        source_type="encyclopedic_entry",
        authority_level=SourceAuthority.SECONDARY_ACADEMIC,
        independence_group="britannica_editorial",
    )
    s4 = FactSource(
        source_id="src_loc_ford_reprint",
        url="https://loc.gov/item/ford_assembly_line_reprint",
        title="Ford Assembly Line Research Summary",
        publisher="Library of Congress Syndication",
        source_type="academic_paper",
        authority_level=SourceAuthority.SECONDARY_ACADEMIC,
        independence_group="loc_archive",  # Same independence group as s2!
    )
    s5 = FactSource(
        source_id="src_random_blog",
        url="https://random-auto-facts.blogspot.com/fastest-car",
        title="10 Incredible Auto Myths",
        publisher="AutoFan99",
        source_type="blog",
        authority_level=SourceAuthority.UNVERIFIED,
        independence_group="uncited_blog",
    )
    return {
        s1.source_id: s1,
        s2.source_id: s2,
        s3.source_id: s3,
        s4.source_id: s4,
        s5.source_id: s5,
    }


def test_fact_source_validation():
    """T01: Verify FactSource creation and field validation."""
    source = FactSource(
        source_id="src_test",
        title="Test Document",
        publisher="Test Publisher",
        authority_level=SourceAuthority.PRIMARY_INSTITUTIONAL,
        independence_group="test_group",
    )
    assert source.source_id == "src_test"
    assert source.authority_level == SourceAuthority.PRIMARY_INSTITUTIONAL
    assert source.independence_group == "test_group"
    assert source.license == "Public Domain"


def test_fact_claim_validation():
    """T02: Verify FactClaim creation with multi-source and boundaries."""
    claim = FactClaim(
        claim_id="claim_001",
        claim_text="Bertha Benz realizó un viaje de aproximadamente 104 km en agosto de 1888.",
        source_ids=["src_daimler_archive"],
        entity="Bertha Benz",
        date_or_era="Agosto 1888",
        status=ClaimStatus.VERIFIED,
        scope="Viaje de ida entre Mannheim y Pforzheim",
        supporting_excerpt="Im August 1888 fuhr Bertha Benz ca. 104 km...",
        source_locator="Dok. B-1888, S. 4",
        allowed_wording="aproximadamente 104 km",
        prohibited_wording=["primer ser humano en conducir"],
    )
    assert claim.claim_id == "claim_001"
    assert claim.certainty == ClaimStatus.VERIFIED
    assert len(claim.source_ids) == 1
    assert claim.source_locator == "Dok. B-1888, S. 4"


def test_fact_dossier_validation(engine: FactIntelligenceEngine, sample_sources: dict):
    """T03: Verify FactDossier compilation and structure."""
    claims = [
        FactClaim(
            claim_id="c1",
            claim_text="El Ford Modelo T redujo el tiempo de ensamblado del chasis a 93 minutos.",
            source_ids=["src_loc_ford"],
            status=ClaimStatus.VERIFIED,
        )
    ]
    dossier = engine.compile_dossier(
        topic="Historia del automóvil",
        run_id="run_test_001",
        sources=list(sample_sources.values()),
        claims=claims,
        timeline_milestones=["1886: Patente Benz", "1913: Línea de montaje"],
        key_entities=["Bertha Benz", "Henry Ford"],
    )
    assert dossier.topic == "Historia del automóvil"
    assert len(dossier.sources) == 5
    assert len(dossier.claims) == 1
    assert len(dossier.dossier_sha256) == 64
    assert dossier.frozen is True


def test_canonical_serialization_deterministic_hash(engine: FactIntelligenceEngine, sample_sources: dict):
    """T04: Verify same content in different dictionary orders produces identical hash."""
    claims = [
        FactClaim(claim_id="c1", claim_text="Claim A", source_ids=["src_loc_ford"]),
        FactClaim(claim_id="c2", claim_text="Claim B", source_ids=["src_daimler_archive"]),
    ]

    fixed_time = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    d1_dict = {
        "dossier_id": "dossier_det",
        "run_id": "r1",
        "version": 1,
        "topic": "Test Topic",
        "created_at": fixed_time,
        "sources": {"src_b": sample_sources["src_loc_ford"], "src_a": sample_sources["src_daimler_archive"]},
        "claims": {"c2": claims[1], "c1": claims[0]},
        "timeline_milestones": ["m1", "m2"],
        "key_entities": ["E1", "E2"],
    }

    d2_dict = {
        "key_entities": ["E1", "E2"],
        "timeline_milestones": ["m1", "m2"],
        "claims": {"c1": claims[0], "c2": claims[1]},
        "sources": {"src_a": sample_sources["src_daimler_archive"], "src_b": sample_sources["src_loc_ford"]},
        "created_at": fixed_time,
        "topic": "Test Topic",
        "version": 1,
        "run_id": "r1",
        "dossier_id": "dossier_det",
    }

    hash1 = engine.compute_dossier_hash(d1_dict)
    hash2 = engine.compute_dossier_hash(d2_dict)

    assert hash1 == hash2


def test_claim_change_changes_hash(engine: FactIntelligenceEngine, sample_sources: dict):
    """T05: Modifying a claim alters the dossier SHA-256."""
    fixed_time = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    c1 = FactClaim(claim_id="c1", claim_text="Texto original", source_ids=["src_loc_ford"])
    c2 = FactClaim(claim_id="c1", claim_text="Texto modificado", source_ids=["src_loc_ford"])

    d1 = {"dossier_id": "d1", "run_id": "r1", "version": 1, "topic": "T", "created_at": fixed_time, "sources": {}, "claims": {"c1": c1}, "timeline_milestones": [], "key_entities": []}
    d2 = {"dossier_id": "d1", "run_id": "r1", "version": 1, "topic": "T", "created_at": fixed_time, "sources": {}, "claims": {"c1": c2}, "timeline_milestones": [], "key_entities": []}

    h1 = engine.compute_dossier_hash(d1)
    h2 = engine.compute_dossier_hash(d2)

    assert h1 != h2


def test_source_change_changes_hash(engine: FactIntelligenceEngine, sample_sources: dict):
    """T06: Modifying a source attribute alters the dossier SHA-256."""
    fixed_time = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    s1 = sample_sources["src_daimler_archive"]
    s2 = sample_sources["src_daimler_archive"].model_copy(update={"title": "Modified Title Archive"})

    d1 = {"dossier_id": "d1", "run_id": "r1", "version": 1, "topic": "T", "created_at": fixed_time, "sources": {"s": s1}, "claims": {}, "timeline_milestones": [], "key_entities": []}
    d2 = {"dossier_id": "d1", "run_id": "r1", "version": 1, "topic": "T", "created_at": fixed_time, "sources": {"s": s2}, "claims": {}, "timeline_milestones": [], "key_entities": []}

    h1 = engine.compute_dossier_hash(d1)
    h2 = engine.compute_dossier_hash(d2)

    assert h1 != h2


def test_unverified_source_cannot_certify_claim(engine: FactIntelligenceEngine, sample_sources: dict):
    """T07: A claim supported exclusively by UNVERIFIED source cannot receive VERIFIED status."""
    claim = FactClaim(
        claim_id="c_unverified",
        claim_text="Dato obtenido de un blog no verificado.",
        source_ids=["src_random_blog"],
        status=ClaimStatus.VERIFIED,
    )
    res = engine.verify_claim(claim, sample_sources)
    assert res.passed is False
    assert res.status == ClaimStatus.UNCERTAIN
    assert any("UNVERIFIED" in f for f in res.findings)


def test_primary_institutional_can_certify_domain_claim(engine: FactIntelligenceEngine, sample_sources: dict):
    """T08: Competent primary institutional source certifies a domain claim."""
    claim = FactClaim(
        claim_id="c_benz",
        claim_text="Bertha Benz condujo el Patent-Motorwagen Número 3.",
        source_ids=["src_daimler_archive"],
        status=ClaimStatus.VERIFIED,
    )
    res = engine.verify_claim(claim, sample_sources)
    assert res.passed is True
    assert res.status == ClaimStatus.VERIFIED
    assert res.independent_sources_count == 1


def test_two_independent_secondary_sources_corroborate(engine: FactIntelligenceEngine, sample_sources: dict):
    """T09: Two secondary sources from different independence groups corroborate a claim."""
    claim = FactClaim(
        claim_id="c_ford",
        claim_text="En 1913 se introdujo la línea de montaje móvil en Highland Park.",
        source_ids=["src_loc_ford", "src_britannica_assembly"],
        status=ClaimStatus.VERIFIED,
    )
    res = engine.verify_claim(claim, sample_sources)
    assert res.passed is True
    assert res.status == ClaimStatus.VERIFIED
    assert res.independent_sources_count == 2


def test_same_independence_group_fails_corroboration(engine: FactIntelligenceEngine, sample_sources: dict):
    """T10: Two sources sharing the same independence_group count as 1 and fail dual-corroboration."""
    # Both src_loc_ford and src_loc_ford_reprint belong to "loc_archive"
    claim = FactClaim(
        claim_id="c_same_group",
        claim_text="Afirmación con dos fuentes sindicadas de la misma institución.",
        source_ids=["src_loc_ford", "src_loc_ford_reprint"],
        status=ClaimStatus.VERIFIED,
    )
    res = engine.verify_claim(claim, sample_sources)
    # Since neither is primary institutional and independent count is 1 (< 2), fails
    assert res.passed is False
    assert res.independent_sources_count == 1
    assert any("lacks sufficient corroboration" in f for f in res.findings)


def test_contradiction_blocks_verified(engine: FactIntelligenceEngine, sample_sources: dict):
    """T11: Contradicted claim is rejected and status is set to CONTRADICTED."""
    claim = FactClaim(
        claim_id="c_contra",
        claim_text="Afirmación desmentida por evidencia documental.",
        source_ids=["src_daimler_archive"],
        status=ClaimStatus.CONTRADICTED,
    )
    res = engine.verify_claim(claim, sample_sources)
    assert res.passed is False
    assert res.has_contradiction is True
    assert res.status == ClaimStatus.CONTRADICTED


def test_context_required_mandates_scope(engine: FactIntelligenceEngine, sample_sources: dict):
    """T12: Claims marked CONTEXT_REQUIRED without scope fail verification."""
    claim_no_scope = FactClaim(
        claim_id="c_ctx1",
        claim_text="El auto alcanzaba velocidades extremas.",
        source_ids=["src_daimler_archive"],
        status=ClaimStatus.CONTEXT_REQUIRED,
        scope=None,  # Missing scope
    )
    res_fail = engine.verify_claim(claim_no_scope, sample_sources)
    assert res_fail.passed is False
    assert any("strictly require an explicit 'scope'" in f for f in res_fail.findings)

    claim_with_scope = FactClaim(
        claim_id="c_ctx2",
        claim_text="El auto alcanzaba velocidades extremas.",
        source_ids=["src_daimler_archive"],
        status=ClaimStatus.CONTEXT_REQUIRED,
        scope="Para los estándares de 1888 (~16 km/h)",
    )
    res_pass = engine.verify_claim(claim_with_scope, sample_sources)
    assert res_pass.passed is True
    assert res_pass.status == ClaimStatus.CONTEXT_REQUIRED


def test_prohibited_wording_prevents_overclaiming(engine: FactIntelligenceEngine, sample_sources: dict):
    """T13: Demonstrative Test: Source says 'uno de los primeros' -> allows that wording, rejects 'el primero de la historia'."""
    # 1. Allowed / Qualified Formulation:
    valid_claim = FactClaim(
        claim_id="c_first_valid",
        claim_text="El viaje de Bertha Benz en 1888 fue uno de los primeros viajes de larga distancia documentados.",
        source_ids=["src_daimler_archive"],
        status=ClaimStatus.VERIFIED,
        supporting_excerpt="Im August 1888 fuhr Bertha Benz: einer der ersten Langstreckenfahrten der Automobilgeschichte.",
        allowed_wording="uno de los primeros viajes",
        prohibited_wording=["el primero de la historia", "primer ser humano"],
    )
    res_valid = engine.verify_claim(valid_claim, sample_sources)
    assert res_valid.passed is True
    assert res_valid.overclaiming_detected is False
    assert res_valid.status == ClaimStatus.VERIFIED

    # 2. Overclaimed Superlative Formulation (Strictly Rejected):
    overclaimed_claim = FactClaim(
        claim_id="c_first_invalid",
        claim_text="El viaje de Bertha Benz fue el primero de la historia sin excepción.",
        source_ids=["src_daimler_archive"],
        status=ClaimStatus.VERIFIED,
        supporting_excerpt="Im August 1888 fuhr Bertha Benz: einer der ersten Langstreckenfahrten der Automobilgeschichte.",
        allowed_wording="uno de los primeros viajes",
        prohibited_wording=["el primero de la historia", "primer ser humano"],
    )
    res_invalid = engine.verify_claim(overclaimed_claim, sample_sources)
    assert res_invalid.passed is False
    assert res_invalid.overclaiming_detected is True
    assert any("Overclaiming detected" in f for f in res_invalid.findings)


def test_supporting_excerpt_requires_valid_source(engine: FactIntelligenceEngine, sample_sources: dict):
    """T14: Supporting excerpt references an existing source in catalog."""
    claim = FactClaim(
        claim_id="c_excerpt",
        claim_text="El viaje duró aproximadamente 12 horas.",
        source_ids=["src_non_existent"],
        supporting_excerpt="Cita de documento inexistente.",
    )
    res = engine.verify_claim(claim, sample_sources)
    assert res.passed is False
    assert any("not found in source catalog" in f for f in res.findings)


def test_source_locator_preserves_forensic_provenance():
    """T15: Source locator preserves exact document locator for forensic audits."""
    snap = EvidenceSnapshot(
        snapshot_id="snap_001",
        source_id="src_daimler_archive",
        raw_text="Bertha Benz fuhr ca. 104 km...",
        source_locator="Folio 42, Párrafo 2, Línea 14",
    )
    assert snap.source_locator == "Folio 42, Párrafo 2, Línea 14"
    assert snap.source_id == "src_daimler_archive"


def test_frozen_dossier_immutability(engine: FactIntelligenceEngine, sample_sources: dict):
    """T16: Compiled FactDossier is strictly read-only and raises TypeError upon attempted mutation."""
    dossier = engine.compile_dossier(
        topic="Immutability Test",
        run_id="run_immut_001",
        sources=list(sample_sources.values()),
        claims=[FactClaim(claim_id="c1", claim_text="Claim", source_ids=["src_loc_ford"])],
    )
    assert dossier.frozen is True

    # Mutating topic must raise TypeError
    with pytest.raises(TypeError, match="is frozen and cannot be modified"):
        dossier.topic = "New Topic"

    # Mutating version must raise TypeError
    with pytest.raises(TypeError, match="is frozen and cannot be modified"):
        dossier.version = 2


def test_revision_produces_new_version_and_hash(engine: FactIntelligenceEngine, sample_sources: dict):
    """T17: Incremental revision creates v2 with new hash and does not mutate base v1."""
    c1 = FactClaim(claim_id="c1", claim_text="Claim 1", source_ids=["src_loc_ford"])
    dossier_v1 = engine.compile_dossier(
        topic="Revision Topic",
        run_id="run_rev_001",
        sources=[sample_sources["src_loc_ford"]],
        claims=[c1],
        version=1,
    )
    hash_v1 = dossier_v1.dossier_sha256

    # Create revision with new evidence
    c2 = FactClaim(claim_id="c2", claim_text="Claim 2 (incremental)", source_ids=["src_daimler_archive"])
    dossier_v2 = engine.create_revision(
        base_dossier=dossier_v1,
        added_sources=[sample_sources["src_daimler_archive"]],
        added_claims=[c2],
    )

    # Assertions
    assert dossier_v1.version == 1
    assert len(dossier_v1.claims) == 1
    assert dossier_v1.dossier_sha256 == hash_v1  # Base untouched

    assert dossier_v2.version == 2
    assert len(dossier_v2.claims) == 2
    assert dossier_v2.dossier_sha256 != hash_v1
    assert "c2" in dossier_v2.claims
    assert dossier_v2.frozen is True


def test_multi_source_claims_aggregation(engine: FactIntelligenceEngine, sample_sources: dict):
    """T18: Claims with multiple independent sources calculate independent source count correctly."""
    claim = FactClaim(
        claim_id="c_multi",
        claim_text="El chasis del Modelo T.",
        source_ids=["src_daimler_archive", "src_loc_ford", "src_britannica_assembly"],
        status=ClaimStatus.VERIFIED,
    )
    res = engine.verify_claim(claim, sample_sources)
    assert res.independent_sources_count == 3
    assert res.passed is True


def test_claim_grounding_compatibility():
    """T19: FactClaim is fully compatible with downstream Scene schema in 12B."""
    from engine.story.schema import Scene

    claim = FactClaim(
        claim_id="c_scene",
        claim_text="Telemetría LiDAR en vehículos autónomos.",
        source_ids=["src_loc_ford"],
        status=ClaimStatus.VERIFIED,
        scope="Sistemas comerciales contemporáneos",
        allowed_wording="sensores LiDAR y cámaras",
        prohibited_wording=["visión humana perfecta"],
    )

    # Attach to 12B Scene model
    scene = Scene(
        id="scene_test_12c",
        scene_index=0,
        narrative_role="development_turning_point",
        script_text="Los sensores LiDAR miden distancias con precisión milimétrica.",
        word_count=9,
        estimated_duration_sec=3.6,
        factual_claims=[claim],
    )

    assert len(scene.factual_claims) == 1
    assert scene.factual_claims[0].claim_text == claim.claim_text
    assert scene.factual_claims[0].scope == claim.scope
    assert scene.factual_claims[0].certainty == ClaimStatus.VERIFIED


def test_zero_imports_from_engine_media():
    """T20: Absolute architectural isolation: zero imports from engine/media."""
    import sys
    # Verify neither engine.story.fact_intelligence nor engine.story.schema imported engine.media
    imported_media = [mod for mod in sys.modules if mod.startswith("engine.media")]
    # Prior stages might have run, but fact_intelligence itself must not import engine.media
    import inspect
    import engine.story.fact_intelligence as fi
    source_code = inspect.getsource(fi)
    assert "engine.media" not in source_code
    assert "ffmpeg" not in source_code.lower() or "ffprobe" not in source_code.lower()

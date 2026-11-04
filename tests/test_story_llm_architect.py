"""Unit tests for LLM Story Architect & Claim Grounding Gate (Stage 12C.2).

Validates:
1. LLMProvider interface contract and MockLLMProvider execution.
2. StoryDraft, SceneDraft, and AssertionUnit schema structure and validation.
3. ClaimGroundingGate passes valid, fully-grounded StoryDraft.
4. ClaimGroundingGate rejects orphan factual assertions (UNGROUNDED_FACTUAL_ASSERTION).
5. ClaimGroundingGate rejects fabricated claim IDs (FABRICATED_CLAIM_ID).
6. ClaimGroundingGate rejects contradicted claim usage (CONTRADICTED_CLAIM_USAGE).
7. ClaimGroundingGate enforces prohibited wording constraints (PROHIBITED_WORDING_VIOLATION).
8. ClaimGroundingGate detects and rejects overclaiming superlatives (OVERCLAIMING_VIOLATION).
9. Narrative and transition statements are permitted without claim grounding.
10. Interpretive statements are validated against valid claim IDs and wording bounds.
11. Gate detects dossier SHA-256 hash mismatch (DOSSIER_HASH_MISMATCH).
12. Gate detects dossier ID mismatch (DOSSIER_ID_MISMATCH).
13. Surgical scene regeneration modifies exclusively the failing scene.
14. Immutability guarantee: LLM synthesis and gate cannot mutate FactDossier.
15. Seamless conversion of approved StoryDraft to Stage 12B StoryArc.
16. Converted StoryArc passes Stage 12B StoryQA validation.
17. Absolute architectural isolation: zero imports from engine/media or web libraries.
18. LLMStoryArchitect end-to-end execution with successful draft and arc.
19. LLMStoryArchitect automated surgical retry loop recovers from single failing scene.
20. LLMStoryArchitect respects max_retries limit without infinite loops or crashes.
"""

import ast
import inspect
from pathlib import Path
import pytest

from engine.story import (
    AssertionUnit,
    ClaimGroundingGate,
    ClaimStatus,
    EndingStrategy,
    EvidenceSnapshot,
    FactClaim,
    FactDossier,
    FactIntelligenceEngine,
    FactSource,
    LLMProvider,
    LLMStoryArchitect,
    MockLLMProvider,
    NarrativeRole,
    SceneDraft,
    SourceAuthority,
    StatementType,
    StoryArc,
    StoryDraft,
    StoryQAEngine,
    VisualBrief,
)


@pytest.fixture
def intelligence_engine() -> FactIntelligenceEngine:
    return FactIntelligenceEngine()


@pytest.fixture
def sample_dossier(intelligence_engine: FactIntelligenceEngine) -> FactDossier:
    s1 = FactSource(
        source_id="src_univ_gottingen",
        url="https://uni-goettingen.de/gauss-weber-1833",
        title="Gauss-Weber Telegraph 1833 Historical Record",
        publisher="University of Göttingen Archives",
        authority_level=SourceAuthority.PRIMARY_INSTITUTIONAL,
        independence_group="gottingen_univ",
    )
    s2 = FactSource(
        source_id="src_ieee_history",
        url="https://ieeeghn.org/wiki/index.php/Milestones:Gauss-Weber_Telegraph",
        title="IEEE Milestone: Gauss-Weber Telegraph",
        publisher="IEEE History Center",
        authority_level=SourceAuthority.SECONDARY_ACADEMIC,
        independence_group="ieee",
    )

    claims = {
        "claim_01": FactClaim(
            claim_id="claim_01",
            claim_text="En 1833, Carl Friedrich Gauss y Wilhelm Weber construyeron una línea telegráfica electromagnética de 1.2 kilómetros en Gotinga.",
            source_ids=["src_univ_gottingen", "src_ieee_history"],
            entity="Carl Friedrich Gauss",
            status=ClaimStatus.VERIFIED,
            supporting_excerpt="En 1833, Gauss y Weber instalaron una línea de 1.2 km sobre los tejados de Gotinga.",
            prohibited_wording=["inventaron el teléfono", "inventó la radio"],
        ),
        "claim_02": FactClaim(
            claim_id="claim_02",
            claim_text="El dispositivo conectaba el observatorio astronómico con el instituto de física de la Universidad de Gotinga.",
            source_ids=["src_univ_gottingen"],
            entity="Wilhelm Weber",
            status=ClaimStatus.VERIFIED,
            supporting_excerpt="La conexión unía directamente el observatorio con el laboratorio de física.",
            prohibited_wording=[],
        ),
        "claim_03": FactClaim(
            claim_id="claim_03",
            claim_text="Gauss y Weber son considerados entre los primeros pioneros de la telegrafía eléctrica en Europa.",
            source_ids=["src_ieee_history"],
            entity="Gotinga",
            status=ClaimStatus.VERIFIED,
            supporting_excerpt="Fueron considerados uno de los primeros grupos pioneros en experimentar con pulsos eléctricos a distancia.",
            prohibited_wording=["inventores únicos y absolutos de toda comunicación"],
        ),
        "claim_04": FactClaim(
            claim_id="claim_04",
            claim_text="Gauss inventó la radio moderna en 1833.",
            source_ids=["src_univ_gottingen"],
            entity="Carl Friedrich Gauss",
            status=ClaimStatus.CONTRADICTED,
            supporting_excerpt="La radio fue desarrollada a finales del siglo XIX por Hertz, Tesla y Marconi.",
            prohibited_wording=[],
        ),
    }

    dossier = intelligence_engine.compile_dossier(
        dossier_id="dossier_gauss_telegraph_1833",
        run_id="run_test_12c2",
        topic="El telégrafo electromagnético de Gauss y Weber en Gotinga",
        sources=[s1, s2],
        claims=list(claims.values()),
        timeline_milestones=["1833: Construcción de la línea en Gotinga", "1835: Demostración de conmutación"],
        key_entities=["Carl Friedrich Gauss", "Wilhelm Weber", "Gotinga"],
    )
    return dossier


@pytest.fixture
def valid_story_draft(sample_dossier: FactDossier) -> StoryDraft:
    """Construct a complete, valid StoryDraft of ~180 words (>61s duration) across 5 scenes."""
    scenes = [
        SceneDraft(
            scene_id="scene_01",
            scene_index=0,
            narrative_role=NarrativeRole.HOOK,
            narration=(
                "¿Sabías que mucho antes del internet y los cables submarinos transatlánticos, "
                "dos genios alemanes lograron comunicarse a través de los tejados de toda una ciudad? "
                "Esta es la historia de una conexión invisible que cambió para siempre el destino humano."
            ),
            assertions=[
                AssertionUnit(
                    text="¿Sabías que dos genios alemanes lograron comunicarse a través de tejados?",
                    statement_type=StatementType.NARRATIVE,
                    claim_ids=[],
                ),
                AssertionUnit(
                    text="Esta es la historia de una conexión invisible que cambió el destino humano.",
                    statement_type=StatementType.TRANSITION,
                    claim_ids=[],
                ),
            ],
            visual_intent=VisualBrief(
                subject="Tejados de Gotinga en el siglo XIX",
                era="1833",
                environment="Ciudad universitaria alemana con agujas góticas",
                action="Cables de cobre tendidos entre torres",
                mood="Misterioso y fascinante",
            ),
            dependencies=[],
        ),
        SceneDraft(
            scene_id="scene_02",
            scene_index=1,
            narrative_role=NarrativeRole.ORIGIN_CONTEXT,
            narration=(
                "En el año 1833, en la prestigiosa ciudad de Gotinga, el matemático Carl Friedrich Gauss "
                "y el físico Wilhelm Weber construyeron una línea telegráfica electromagnética de 1.2 kilómetros. "
                "Fue una de las primeras grandes proezas de la física aplicada en Europa."
            ),
            assertions=[
                AssertionUnit(
                    text="En 1833, Carl Friedrich Gauss y Wilhelm Weber construyeron una línea de 1.2 kilómetros en Gotinga.",
                    statement_type=StatementType.FACTUAL,
                    claim_ids=["claim_01"],
                ),
                AssertionUnit(
                    text="Fue una de las primeras grandes proezas de la física aplicada.",
                    statement_type=StatementType.INTERPRETIVE,
                    claim_ids=["claim_03"],
                ),
            ],
            visual_intent=VisualBrief(
                subject="Laboratorio de Gauss y Weber",
                era="1833",
                environment="Taller científico con galvanómetros y bobinas",
                action="Ajustando electroimanes y agujas magnéticas",
                mood="Científico y riguroso",
            ),
            dependencies=["scene_01"],
        ),
        SceneDraft(
            scene_id="scene_03",
            scene_index=2,
            narrative_role=NarrativeRole.DEVELOPMENT_TURNING_POINT,
            narration=(
                "Aquel primitivo dispositivo conectaba directamente el observatorio astronómico con el "
                "instituto de física de la Universidad de Gotinga. Cada pulso eléctrico enviado hacía oscilar "
                "un imán suspendido al otro extremo, demostrando que la información podía viajar más rápido que cualquier carruaje."
            ),
            assertions=[
                AssertionUnit(
                    text="El dispositivo conectaba el observatorio astronómico con el instituto de física de la Universidad de Gotinga.",
                    statement_type=StatementType.FACTUAL,
                    claim_ids=["claim_02"],
                ),
                AssertionUnit(
                    text="Cada pulso eléctrico demostraba que la información viajaba instantáneamente.",
                    statement_type=StatementType.INTERPRETIVE,
                    claim_ids=[],
                ),
            ],
            visual_intent=VisualBrief(
                subject="Galvanómetro de espejo reflejando un rayo de luz",
                era="1833",
                environment="Observatorio astronómico de Gotinga",
                action="Espejo oscilando con cada pulso eléctrico",
                mood="Asombro tecnológico",
            ),
            dependencies=["scene_02"],
        ),
        SceneDraft(
            scene_id="scene_04",
            scene_index=3,
            narrative_role=NarrativeRole.TRANSFORMATION,
            narration=(
                "Ambos científicos son reconocidos por la comunidad académica como pioneros fundamentales en el "
                "nacimiento de las telecomunicaciones eléctricas. No buscaron patentarlo para enriquecerse, "
                "sino para estudiar las leyes profundas del magnetismo terrestre y sincronizar sus observaciones celestes."
            ),
            assertions=[
                AssertionUnit(
                    text="Ambos científicos son reconocidos como pioneros de las telecomunicaciones.",
                    statement_type=StatementType.FACTUAL,
                    claim_ids=["claim_03"],
                ),
                AssertionUnit(
                    text="No buscaron enriquecerse sino sincronizar observaciones astronómicas.",
                    statement_type=StatementType.INTERPRETIVE,
                    claim_ids=[],
                ),
            ],
            visual_intent=VisualBrief(
                subject="Retrato de Gauss y Weber discutiendo planos",
                era="1833",
                environment="Biblioteca académica iluminada con lámparas de aceite",
                action="Analizando mediciones magnéticas en pergaminos",
                mood="Intelectual y solemne",
            ),
            dependencies=["scene_03"],
        ),
        SceneDraft(
            scene_id="scene_05",
            scene_index=4,
            narrative_role=NarrativeRole.PAYOFF,
            narration=(
                "Hoy en día enviamos billones de mensajes por segundo a través de fibra óptica y satélites espaciales, "
                "pero el primer latido de ese mundo hiperconectado comenzó exactamente allí, con un modesto cable "
                "suspendido entre los tejados de Gotinga por Gauss y Weber. Síguenos para descubrir más revoluciones ocultas."
            ),
            assertions=[
                AssertionUnit(
                    text="Hoy enviamos billones de mensajes a la velocidad de la luz.",
                    statement_type=StatementType.NARRATIVE,
                    claim_ids=[],
                ),
                AssertionUnit(
                    text="Síguenos para descubrir más revoluciones ocultas de la historia.",
                    statement_type=StatementType.TRANSITION,
                    claim_ids=[],
                ),
            ],
            visual_intent=VisualBrief(
                subject="Transición visual de cables de cobre decimonónicos a fibra óptica contemporánea",
                era="Presente",
                environment="Perspectiva aérea de la Tierra conectada con pulsos de luz",
                action="Zoom dinámico espacial hacia el planeta iluminado",
                mood="Épico e inspirador",
            ),
            dependencies=["scene_04"],
        ),
    ]

    return StoryDraft(
        title="El telégrafo secreto de Gauss y Weber",
        topic=sample_dossier.topic,
        core_question="¿Cómo nació la comunicación instantánea en Europa?",
        narrative_promise="Descubre la primera red de telecomunicación electromagnética de la historia.",
        hook_strategy="question",
        scenes=scenes,
        ending_strategy=EndingStrategy.PAYOFF,
        target_audience="general_science",
        tone="curious_informative",
        dossier_id=sample_dossier.dossier_id,
        dossier_sha256=sample_dossier.dossier_sha256,
    )


# -----------------------------------------------------------------------------
# Test Suite: 20 Tests
# -----------------------------------------------------------------------------

def test_llm_provider_contract_and_mock(valid_story_draft: StoryDraft):
    """1. Validates LLMProvider abstraction and MockLLMProvider behavior."""
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore

    mock = MockLLMProvider(canned_response=valid_story_draft, model_name="mock-gemini-pro")
    meta = mock.metadata()
    assert meta["provider"] == "mock_deterministic"
    assert meta["model"] == "mock-gemini-pro"
    assert meta["offline"] is True
    assert meta["calls_made"] == 0

    res = mock.generate_structured("Write a story", StoryDraft)
    assert res.title == valid_story_draft.title
    assert mock.metadata()["calls_made"] == 1


def test_story_draft_schema_validation(valid_story_draft: StoryDraft):
    """2. Validates StoryDraft and child schemas serialization and structure."""
    assert len(valid_story_draft.scenes) == 5
    assert valid_story_draft.scenes[0].narrative_role == NarrativeRole.HOOK
    assert valid_story_draft.scenes[4].narrative_role == NarrativeRole.PAYOFF

    dumped = valid_story_draft.model_dump()
    reloaded = StoryDraft.model_validate(dumped)
    assert reloaded.title == valid_story_draft.title
    assert reloaded.dossier_sha256 == valid_story_draft.dossier_sha256


def test_grounding_gate_passes_valid_draft(valid_story_draft: StoryDraft, sample_dossier: FactDossier):
    """3. Validates that a correctly grounded draft passes ClaimGroundingGate cleanly."""
    gate = ClaimGroundingGate()
    report = gate.evaluate_draft(valid_story_draft, sample_dossier)

    assert report.passed is True
    assert len(report.findings) == 0
    assert report.total_assertions > 0
    assert report.factual_assertions > 0
    assert report.grounded_assertions == report.factual_assertions
    assert report.orphan_assertions == 0
    assert report.fabricated_claim_ids == 0
    assert report.overclaiming_assertions == 0
    assert all(report.scene_status.values())


def test_grounding_gate_rejects_orphan_factual_assertion(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """4. Rejects a FACTUAL statement with empty claim_ids (UNGROUNDED_FACTUAL_ASSERTION)."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Gauss descubrió una nueva luna orbitando Júpiter esa misma noche.",
            statement_type=StatementType.FACTUAL,
            claim_ids=[],  # Orphan!
        )
    )

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert report.orphan_assertions == 1
    assert report.scene_status["scene_02"] is False

    err = next(f for f in report.findings if f.rule == "UNGROUNDED_FACTUAL_ASSERTION")
    assert err.severity == "ERROR"
    assert err.scene_id == "scene_02"


def test_grounding_gate_rejects_fabricated_claim_id(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """5. Rejects assertions with non-existent claim IDs (FABRICATED_CLAIM_ID)."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Esta afirmación cita un claim inexistente inventado por el modelo.",
            statement_type=StatementType.FACTUAL,
            claim_ids=["claim_fake_9999"],
        )
    )

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert report.fabricated_claim_ids == 1
    assert report.scene_status["scene_02"] is False

    err = next(f for f in report.findings if f.rule == "FABRICATED_CLAIM_ID")
    assert err.severity == "ERROR"
    assert err.claim_id == "claim_fake_9999"


def test_grounding_gate_rejects_contradicted_claim_usage(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """6. Rejects usage of CONTRADICTED claims as factual truth (CONTRADICTED_CLAIM_USAGE)."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Gauss inventó la radio moderna en 1833 para enviar mensajes a larga distancia.",
            statement_type=StatementType.FACTUAL,
            claim_ids=["claim_04"],  # CONTRADICTED in dossier
        )
    )

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert report.scene_status["scene_02"] is False

    err = next(f for f in report.findings if f.rule == "CONTRADICTED_CLAIM_USAGE")
    assert err.severity == "ERROR"
    assert err.claim_id == "claim_04"


def test_grounding_gate_enforces_prohibited_wording(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """7. Rejects statements containing prohibited wording (PROHIBITED_WORDING_VIOLATION)."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[1].assertions.append(
        AssertionUnit(
            text="En 1833, Gauss y Weber inventaron el teléfono para conectar sus despachos.",
            statement_type=StatementType.FACTUAL,
            claim_ids=["claim_01"],
        )
    )

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert report.scene_status["scene_02"] is False

    err = next(f for f in report.findings if f.rule == "PROHIBITED_WORDING_VIOLATION")
    assert err.severity == "ERROR"
    assert "inventaron el teléfono" in err.message


def test_grounding_gate_detects_overclaiming_superlatives(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """8. Rejects absolute superlatives when evidence is qualified (OVERCLAIMING_VIOLATION)."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    # claim_03 has excerpt "Fueron considerados uno de los primeros..."
    # The statement asserts an absolute superlative: "el primer "
    corrupt_draft.scenes[3].assertions[0] = AssertionUnit(
        text="Gauss y Weber construyeron el primer sistema de comunicación de la historia humana.",
        statement_type=StatementType.FACTUAL,
        claim_ids=["claim_03"],
    )

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert report.overclaiming_assertions == 1
    assert report.scene_status["scene_04"] is False

    err = next(f for f in report.findings if f.rule == "OVERCLAIMING_VIOLATION")
    assert err.severity == "ERROR"


def test_narrative_and_transition_statements_allowed_freely(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """9. Confirms NARRATIVE and TRANSITION statements do not require claim grounding."""
    gate = ClaimGroundingGate()
    draft = valid_story_draft.model_copy(deep=True)
    draft.scenes[0].assertions.extend([
        AssertionUnit(text="Un destello de asombro cruzó la noche.", statement_type=StatementType.NARRATIVE, claim_ids=[]),
        AssertionUnit(text="Pero retrocedamos unos minutos en el tiempo.", statement_type=StatementType.TRANSITION, claim_ids=[]),
    ])

    report = gate.evaluate_draft(draft, sample_dossier)
    assert report.passed is True
    assert report.orphan_assertions == 0


def test_interpretive_statement_validation(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """10. Confirms INTERPRETIVE statements are checked against prohibited wording if claim_id is attached."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Eran los inventores únicos y absolutos de toda comunicación sin duda alguna.",
            statement_type=StatementType.INTERPRETIVE,
            claim_ids=["claim_03"],
        )
    )

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert any(f.rule == "PROHIBITED_WORDING_VIOLATION" for f in report.findings)


def test_dossier_sha256_hash_mismatch(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """11. Rejects draft referencing mismatched dossier SHA-256 hash."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(update={"dossier_sha256": "0" * 64})

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert any(f.rule == "DOSSIER_HASH_MISMATCH" for f in report.findings)


def test_dossier_id_mismatch(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """12. Rejects draft referencing mismatched dossier ID."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(update={"dossier_id": "different_dossier_id"})

    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert any(f.rule == "DOSSIER_ID_MISMATCH" for f in report.findings)


def test_surgical_scene_regeneration(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """13. Confirms surgical regeneration replaces ONLY the failing scene without modifying others."""
    gate = ClaimGroundingGate()
    original_scene_01 = valid_story_draft.scenes[0].model_copy(deep=True)
    original_scene_03 = valid_story_draft.scenes[2].model_copy(deep=True)

    remediated_scene_02 = SceneDraft(
        scene_id="scene_02",
        scene_index=1,
        narrative_role=NarrativeRole.ORIGIN_CONTEXT,
        narration="En 1833, en Gotinga, Gauss y Weber tendieron un cable de 1.2 kilómetros sobre los tejados.",
        assertions=[
            AssertionUnit(
                text="En 1833, Gauss y Weber tendieron un cable de 1.2 km en Gotinga.",
                statement_type=StatementType.FACTUAL,
                claim_ids=["claim_01"],
            )
        ],
        visual_intent=valid_story_draft.scenes[1].visual_intent,
        dependencies=["scene_01"],
    )

    mock_provider = MockLLMProvider(canned_response=remediated_scene_02)
    updated_draft = gate.surgical_regenerate_scene(
        draft=valid_story_draft,
        scene_id="scene_02",
        dossier=sample_dossier,
        provider=mock_provider,
        remediation_hint="Ensure claim_01 is cited properly.",
    )

    assert len(updated_draft.scenes) == 5
    # Target scene replaced
    assert updated_draft.scenes[1].narration == remediated_scene_02.narration
    # Other scenes are strictly identical
    assert updated_draft.scenes[0].model_dump() == original_scene_01.model_dump()
    assert updated_draft.scenes[2].model_dump() == original_scene_03.model_dump()


def test_llm_output_cannot_modify_fact_dossier(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """14. Verifies FactDossier remains frozen and completely immutable."""
    assert sample_dossier.frozen is True
    original_sha256 = sample_dossier.dossier_sha256

    gate = ClaimGroundingGate()
    gate.evaluate_draft(valid_story_draft, sample_dossier)

    # Attempt mutation raises TypeError
    with pytest.raises(TypeError, match="is frozen and cannot be modified"):
        sample_dossier.topic = "Mutated Topic"

    assert sample_dossier.dossier_sha256 == original_sha256


def test_convert_grounded_draft_to_story_arc(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """15. Validates conversion of approved StoryDraft to Stage 12B StoryArc."""
    gate = ClaimGroundingGate()
    arc = gate.convert_draft_to_story_arc(valid_story_draft, sample_dossier)

    assert isinstance(arc, StoryArc)
    assert arc.id == f"arc_{sample_dossier.dossier_id}"
    assert len(arc.scenes) == 5
    assert arc.contract.title == valid_story_draft.title
    assert "Carl Friedrich Gauss" in arc.contract.must_include_entities

    # Verify FactClaim attachment
    scene_02 = arc.scenes[1]
    assert len(scene_02.factual_claims) > 0
    assert any(c.claim_id == "claim_01" for c in scene_02.factual_claims)
    assert scene_02.scene_qa_passed is True


def test_grounded_story_arc_passes_12b_story_qa(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """16. Confirms converted StoryArc satisfies Stage 12B StoryQAEngine rules."""
    gate = ClaimGroundingGate()
    arc = gate.convert_draft_to_story_arc(valid_story_draft, sample_dossier)

    qa = StoryQAEngine()
    report = qa.evaluate(arc)

    assert report.passed is True, f"QA Failures: {[f.message for f in report.findings if f.severity == 'ERROR']}"
    assert arc.status == "qa_passed"
    assert arc.total_estimated_duration_sec >= 61.0


def test_zero_imports_from_engine_media_and_no_web():
    """17. Verifies zero imports from engine/media, web scraping, or live network APIs."""
    prohibited_modules = ["engine.media", "requests", "urllib", "httpx", "playwright", "aiohttp"]
    files_to_check = [
        Path(__file__).parent.parent / "engine" / "story" / "grounding_gate.py",
        Path(__file__).parent.parent / "engine" / "story" / "llm_architect.py",
        Path(__file__).parent.parent / "engine" / "story" / "llm_provider.py",
    ]

    for fpath in files_to_check:
        with open(fpath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prohibited in prohibited_modules:
                        assert not alias.name.startswith(prohibited), (
                            f"Prohibited import '{alias.name}' found in {fpath.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for prohibited in prohibited_modules:
                        assert not node.module.startswith(prohibited), (
                            f"Prohibited from-import '{node.module}' found in {fpath.name}"
                        )


def test_llm_story_architect_full_pipeline_success(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """18. End-to-end execution of LLMStoryArchitect producing approved StoryArc."""
    mock_provider = MockLLMProvider(canned_response=valid_story_draft)
    architect = LLMStoryArchitect(provider=mock_provider)

    arc, draft, report = architect.story_architect_run = architect.architect_story(
        dossier=sample_dossier,
        creative_brief={"hook_strategy": "question", "tone": "curious_informative"},
    )

    assert arc is not None
    assert report.passed is True
    assert draft.title == valid_story_draft.title
    assert len(arc.scenes) == 5


def test_llm_story_architect_automatic_surgical_retry(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """19. Automated recovery when initial draft has 1 failing scene."""
    # Create draft with failing scene_02
    flawed_draft = valid_story_draft.model_copy(deep=True)
    flawed_draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Un hecho huérfano sin claim id.",
            statement_type=StatementType.FACTUAL,
            claim_ids=[],
        )
    )

    remediated_scene = valid_story_draft.scenes[1].model_copy(deep=True)

    call_count = 0
    def dynamic_generator(prompt: str, schema_type: type):
        nonlocal call_count
        call_count += 1
        if schema_type == StoryDraft:
            return flawed_draft
        elif schema_type == SceneDraft:
            return remediated_scene
        raise ValueError("Unexpected schema requested")

    mock_provider = MockLLMProvider(generator_fn=dynamic_generator)
    architect = LLMStoryArchitect(provider=mock_provider, max_retries=2)

    arc, final_draft, report = architect.architect_story(sample_dossier)

    assert arc is not None
    assert report.passed is True
    assert call_count >= 2  # 1 for draft, 1 for surgical scene retry


def test_llm_story_architect_max_retries_exceeded(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """20. Halts gracefully when surgical retries fail repeatedly."""
    flawed_draft = valid_story_draft.model_copy(deep=True)
    flawed_draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Un hecho permanentemente huérfano.",
            statement_type=StatementType.FACTUAL,
            claim_ids=[],
        )
    )

    flawed_scene = flawed_draft.scenes[1].model_copy(deep=True)

    def stubborn_flawed_generator(prompt: str, schema_type: type):
        if schema_type == StoryDraft:
            return flawed_draft
        return flawed_scene  # Keeps returning flawed scene

    mock_provider = MockLLMProvider(generator_fn=stubborn_flawed_generator)
    architect = LLMStoryArchitect(provider=mock_provider, max_retries=2)

    arc, final_draft, report = architect.architect_story(sample_dossier)

    assert arc is None
    assert report.passed is False
    assert report.scene_status["scene_02"] is False


# -----------------------------------------------------------------------------
# Forensic Audit Tests (Release Lock Verification)
# -----------------------------------------------------------------------------

def test_forensic_audit_narrative_factual_masquerade_case_a(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """Case A: Factual statement disguised as NARRATIVE with claim_ids=[] must be REJECTED."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[0].assertions.append(
        AssertionUnit(
            text="Bertha Benz fue la primera persona de la historia en realizar un viaje automovilístico de larga distancia.",
            statement_type=StatementType.NARRATIVE,
            claim_ids=[],
        )
    )
    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert any(f.rule == "FACTUAL_MASQUERADE_VIOLATION" for f in report.findings)


def test_forensic_audit_narrative_factual_masquerade_case_b(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """Case B: Historical primacy/revolution claim disguised as NARRATIVE must be REJECTED."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[0].assertions.append(
        AssertionUnit(
            text="Ford revolucionó para siempre la producción industrial mundial.",
            statement_type=StatementType.NARRATIVE,
            claim_ids=[],
        )
    )
    report = gate.evaluate_draft(corrupt_draft, sample_dossier)
    assert report.passed is False
    assert any(f.rule == "FACTUAL_MASQUERADE_VIOLATION" for f in report.findings)


def test_forensic_audit_interpretive_case_c(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """Case C: Legitimate interpretive thematic statement with claim_ids=[] must PASS."""
    gate = ClaimGroundingGate()
    draft = valid_story_draft.model_copy(deep=True)
    draft.scenes[0].assertions.append(
        AssertionUnit(
            text="Este acontecimiento demuestra que la industria estaba destinada a cambiar.",
            statement_type=StatementType.INTERPRETIVE,
            claim_ids=[],
        )
    )
    report = gate.evaluate_draft(draft, sample_dossier)
    assert report.passed is True
    assert len(report.findings) == 0


def test_forensic_audit_valid_claim_id_does_not_permit_overclaiming(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """Valid claim_id is NOT a free pass: qualified claim + absolute superlative must be REJECTED."""
    gate = ClaimGroundingGate()
    draft = valid_story_draft.model_copy(deep=True)
    # claim_03 is qualified: "Gauss y Weber son considerados entre los primeros pioneros..."
    # The statement asserts an absolute superlative: "el primer viaje de larga distancia de la historia"
    draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Bertha Benz realizó el primer viaje de larga distancia de la historia.",
            statement_type=StatementType.FACTUAL,
            claim_ids=["claim_03"],
        )
    )
    report = gate.evaluate_draft(draft, sample_dossier)
    assert report.passed is False
    assert any(f.rule == "OVERCLAIMING_VIOLATION" for f in report.findings)


def test_forensic_audit_claim_status_unverified_rejected(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier, intelligence_engine: FactIntelligenceEngine
):
    """Unverified claims (NEEDS_SOURCE, UNCERTAIN) cannot be asserted as certified factual truth."""
    gate = ClaimGroundingGate()

    # Add a claim with NEEDS_SOURCE to dossier
    unverified_claim = FactClaim(
        claim_id="claim_unverified_01",
        claim_text="Gauss tenía un laboratorio subterráneo secreto.",
        status=ClaimStatus.NEEDS_SOURCE,
        source_ids=[],
    )
    revised_dossier = intelligence_engine.create_revision(
        base_dossier=sample_dossier,
        added_claims=[unverified_claim],
    )

    draft = valid_story_draft.model_copy(
        deep=True,
        update={
            "dossier_sha256": revised_dossier.dossier_sha256,
        },
    )
    draft.scenes[1].assertions.append(
        AssertionUnit(
            text="Gauss operaba un laboratorio subterráneo secreto en Gotinga.",
            statement_type=StatementType.FACTUAL,
            claim_ids=["claim_unverified_01"],
        )
    )

    report = gate.evaluate_draft(draft, revised_dossier)
    assert report.passed is False
    assert any(f.rule == "UNVERIFIED_CLAIM_USAGE" for f in report.findings)


def test_forensic_audit_dossier_revision_cross_validation_rejected(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier, intelligence_engine: FactIntelligenceEngine
):
    """Draft generated against Dossier A fails validation against modified Dossier B (DOSSIER_HASH_MISMATCH)."""
    gate = ClaimGroundingGate()

    # Create revised dossier B with an added source
    new_source = FactSource(
        source_id="src_revised_01",
        title="Weber Letters 1834",
        publisher="Archive Press",
    )
    dossier_b = intelligence_engine.create_revision(
        base_dossier=sample_dossier,
        added_sources=[new_source],
    )
    assert dossier_b.dossier_sha256 != sample_dossier.dossier_sha256

    # Attempt to validate draft A (which references sample_dossier hash) against dossier B
    report = gate.evaluate_draft(valid_story_draft, dossier_b)
    assert report.passed is False
    assert any(f.rule == "DOSSIER_HASH_MISMATCH" for f in report.findings)


def test_forensic_audit_story_arc_bypass_impossible(
    valid_story_draft: StoryDraft, sample_dossier: FactDossier
):
    """Ungrounded StoryDraft CANNOT bypass the gate to produce an approved StoryArc."""
    gate = ClaimGroundingGate()
    corrupt_draft = valid_story_draft.model_copy(deep=True)
    corrupt_draft.scenes[0].assertions.append(
        AssertionUnit(
            text="Afirmación factual sin grounding.",
            statement_type=StatementType.FACTUAL,
            claim_ids=[],
        )
    )

    # Calling convert_draft_to_story_arc on bad_draft MUST raise ValueError
    with pytest.raises(ValueError, match="Cannot convert ungrounded StoryDraft to StoryArc"):
        gate.convert_draft_to_story_arc(corrupt_draft, sample_dossier)


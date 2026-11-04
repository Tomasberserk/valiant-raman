"""Comprehensive unit test suite for the Story Engine (Stage 12B.1).

Validates:
1. Pydantic schema contracts and downstream media field preservation.
2. Planning duration heuristic (PLANNING_WPS).
3. VisualBrief decoupling and prohibited_mismatches.
4. FactClaim integrity modeling.
5. Golden Case synthesis and textual flexibility.
6. Three-tier duration policy evaluation (<61s fail, 61-90s pass, >90s pass with note).
7. Scene dependency graph validation (string IDs, no forward/self references).
8. Claim integrity validation (rejection of CONTRADICTED, enforcement of scope/wording on CONTEXT_REQUIRED).
9. Narrative coherence validation (required entities, avoided pitfalls, hook & payoff roles).
10. End-to-end StoryQA passage on the canonical Golden Case.
"""

from pathlib import Path
import pytest

from engine.story import (
    PLANNING_WPS,
    ClaimStatus,
    ContinuityRequirement,
    DurationPolicy,
    EndingStrategy,
    FactClaim,
    NarrativeRole,
    Scene,
    StoryArc,
    StoryArchitect,
    StoryContract,
    StoryQAEngine,
    StoryQAFinding,
    StoryQAReport,
    VisualBrief,
    WordTimestamp,
    count_words,
    estimate_duration_sec,
)


def test_story_contract_validation():
    """Verify StoryContract initialization, defaults, and custom policies."""
    contract = StoryContract(
        id="contract_test_01",
        title="Test Story",
        topic="Inteligencia Artificial",
        core_question="¿Cómo piensan las máquinas?",
        narrative_promise="Descubrirás el origen de las redes neuronales.",
        duration_policy=DurationPolicy(
            hard_minimum_sec=61.0,
            planning_target_sec=80.0,
            soft_maximum_sec=95.0,
        ),
        must_include_entities=["Alan Turing", "Perceptrón"],
        must_avoid_pitfalls=["las máquinas van a destruir el mundo mañana"],
        ending_strategy=EndingStrategy.PAYOFF,
    )

    assert contract.duration_policy.hard_minimum_sec == 61.0
    assert contract.duration_policy.planning_target_sec == 80.0
    assert contract.duration_policy.soft_maximum_sec == 95.0
    assert "Alan Turing" in contract.must_include_entities
    assert contract.ending_strategy == EndingStrategy.PAYOFF


def test_scene_downstream_fields_preservation():
    """Verify downstream audiovisual fields are preserved on Scene as optional/empty."""
    scene = Scene(
        id="scene_test_01",
        scene_index=0,
        narrative_role=NarrativeRole.HOOK,
        dependencies=[],
        script_text="Esta es una prueba conceptual de preservación.",
        word_count=7,
        estimated_duration_sec=2.8,
    )

    # Downstream fields must default gracefully to None / empty list
    assert scene.actual_duration_sec is None
    assert scene.voice_audio_path is None
    assert scene.word_timings == []
    assert scene.resolved_asset_path is None
    assert scene.resolution_tier is None

    # Verify downstream fields can be assigned without breaking validation
    scene.actual_duration_sec = 2.95
    scene.voice_audio_path = Path("storage/test_audio.mp3")
    scene.word_timings = [WordTimestamp(word="Esta", start=0.0, end=0.4)]
    scene.resolved_asset_path = Path("storage/broll.mp4")
    scene.resolution_tier = "tier1_exact"

    assert scene.actual_duration_sec == 2.95
    assert scene.word_timings[0].word == "Esta"


def test_planning_heuristic():
    """Verify planning duration heuristic with word counting and WPS calculation."""
    text = "Uno dos tres cuatro cinco seis siete ocho nueve diez."
    words = count_words(text)
    assert words == 10

    # 10 words / 2.5 wps = 4.0 seconds
    duration = estimate_duration_sec(words, wps=2.5)
    assert duration == 4.0

    # Custom wps
    custom_dur = estimate_duration_sec(words, wps=2.0)
    assert custom_dur == 5.0

    with pytest.raises(ValueError):
        estimate_duration_sec(words, wps=0)


def test_visual_brief_decoupling():
    """Verify decoupled VisualBrief with prohibited mismatches and continuity."""
    brief = VisualBrief(
        subject="Carruaje motorizado de tres ruedas",
        era="1886",
        environment="Calle adoquinada de época",
        action="Vehículo rudimentario avanzando despacio",
        mood="Misterioso, histórico",
        search_keywords=["Benz 1886", "first car"],
        prohibited_mismatches=["coches modernos", "asfalto contemporáneo"],
        continuity=ContinuityRequirement(
            visual_anchor="Triciclo motorizado",
            era_progression="1886",
            lighting_mood="Bruma matinal",
        ),
    )

    assert brief.era == "1886"
    assert "coches modernos" in brief.prohibited_mismatches
    assert brief.continuity is not None
    assert brief.continuity.visual_anchor == "Triciclo motorizado"


def test_fact_claim_integrity_model():
    """Verify FactClaim model with scopes, wording constraints, and status."""
    claim = FactClaim(
        claim_text="Bertha Benz realizó el primer viaje de larga distancia en 1888.",
        scope="Primer viaje documentado de larga distancia (~104 km)",
        source_reference="Mercedes-Benz Classic Archive",
        status=ClaimStatus.VERIFIED,
        wording_constraints=["Evitar formular que actuó sin avisar a las autoridades como delito."],
    )

    assert claim.status == ClaimStatus.VERIFIED
    assert claim.scope is not None
    assert len(claim.wording_constraints) == 1


def test_story_architect_golden_case():
    """Verify synthesis of the canonical automotive Golden Case."""
    architect = StoryArchitect(planning_wps=PLANNING_WPS)
    story = architect.synthesize_story(topic="La evolución del automóvil")

    assert len(story.scenes) == 5
    assert story.scenes[0].id == "scene_01"
    assert story.scenes[0].narrative_role == NarrativeRole.HOOK
    assert story.scenes[1].narrative_role == NarrativeRole.ORIGIN_CONTEXT
    assert story.scenes[2].narrative_role == NarrativeRole.DEVELOPMENT_TURNING_POINT
    assert story.scenes[3].narrative_role == NarrativeRole.TRANSFORMATION
    assert story.scenes[4].narrative_role == NarrativeRole.PAYOFF

    # String IDs for dependencies
    assert story.scenes[0].dependencies == []
    assert story.scenes[1].dependencies == ["scene_01"]
    assert story.scenes[2].dependencies == ["scene_02"]
    assert story.scenes[3].dependencies == ["scene_03"]
    assert story.scenes[4].dependencies == ["scene_04"]

    # Duration within 61s - 90s range (planning target ~78s)
    assert 61.0 <= story.total_estimated_duration_sec <= 90.0

    # Textual flexibility: key concepts present without rigid literal matching
    full_text = " ".join(s.script_text for s in story.scenes)
    for entity in story.contract.must_include_entities:
        assert entity.lower() in full_text.lower()


def test_story_qa_duration_rejection():
    """Verify StoryQA strictly rejects stories under the hard minimum duration (< 61.0s)."""
    architect = StoryArchitect()
    story = architect.synthesize_story(topic="La evolución del automóvil")

    # Artificially shorten all scenes to violate 61.0s
    for scene in story.scenes:
        scene.script_text = "Breve texto."
        scene.word_count = 2
        scene.estimated_duration_sec = 0.8
    story.total_estimated_duration_sec = round(sum(s.estimated_duration_sec for s in story.scenes), 1)

    qa = StoryQAEngine()
    report = qa.evaluate(story)

    assert report.passed is False
    assert report.checks["duration_policy"] is False
    errors = [f for f in report.findings if f.rule == "duration_policy_hard_minimum"]
    assert len(errors) == 1
    assert errors[0].severity == "ERROR"
    assert story.status == "qa_failed"


def test_story_qa_duration_soft_max():
    """Verify StoryQA accepts durations above soft maximum (90s) with WARNING (PASS WITH NOTE)."""
    architect = StoryArchitect()
    story = architect.synthesize_story(topic="La evolución del automóvil")

    # Lengthen scenes so total duration is ~95s (> 90.0s)
    for scene in story.scenes:
        scene.estimated_duration_sec = 19.0
    story.total_estimated_duration_sec = 95.0

    qa = StoryQAEngine()
    report = qa.evaluate(story)

    # Passes overall because soft maximum generates a WARNING, not an ERROR
    assert report.passed is True
    assert report.checks["duration_policy"] is True
    warnings = [f for f in report.findings if f.rule == "duration_policy_soft_maximum"]
    assert len(warnings) == 1
    assert warnings[0].severity == "WARNING"


def test_story_qa_dependency_failure():
    """Verify StoryQA catches nonexistent, forward, and self-referencing scene dependencies."""
    architect = StoryArchitect()
    story = architect.synthesize_story(topic="La evolución del automóvil")

    # Introduce dependency issues
    story.scenes[1].dependencies = ["scene_nonexistent"]
    story.scenes[2].dependencies = ["scene_04"]  # forward reference
    story.scenes[3].dependencies = ["scene_04"]  # self reference

    qa = StoryQAEngine()
    report = qa.evaluate(story)

    assert report.passed is False
    assert report.checks["scene_dependencies"] is False

    rules = {f.rule for f in report.findings if f.severity == "ERROR"}
    assert "scene_dependency_nonexistent" in rules
    assert "scene_dependency_forward_reference" in rules
    assert "scene_dependency_self_reference" in rules


def test_story_qa_claim_integrity_rejection():
    """Verify Claim Integrity Validation catches contradicted claims and un-scoped context claims."""
    architect = StoryArchitect()
    story = architect.synthesize_story(topic="La evolución del automóvil")

    # Inject a CONTRADICTED claim
    story.scenes[0].factual_claims.append(
        FactClaim(
            claim_text="El automóvil fue inventado en la antigua Roma.",
            status=ClaimStatus.CONTRADICTED,
        )
    )

    # Inject a CONTEXT_REQUIRED claim missing scope and wording constraints
    story.scenes[1].factual_claims.append(
        FactClaim(
            claim_text="Bertha Benz condujo a más de 200 km/h.",
            status=ClaimStatus.CONTEXT_REQUIRED,
            scope=None,
            wording_constraints=[],
        )
    )

    qa = StoryQAEngine()
    report = qa.evaluate(story)

    assert report.passed is False
    assert report.checks["claim_integrity"] is False

    rules = {f.rule for f in report.findings if f.severity == "ERROR"}
    assert "claim_integrity_contradicted" in rules
    assert "claim_integrity_missing_context" in rules


def test_story_qa_narrative_coherence():
    """Verify Narrative Coherence checks opening hook, required entities, and forbidden pitfalls."""
    architect = StoryArchitect()
    story = architect.synthesize_story(topic="La evolución del automóvil")

    # 1. Break opening hook
    story.scenes[0].narrative_role = NarrativeRole.TRANSFORMATION

    # 2. Break required entity: replace Henry Ford with a generic name
    story.scenes[2].script_text = story.scenes[2].script_text.replace("Henry Ford", "Un fabricante anónimo")

    # 3. Inject forbidden pitfall
    pitfall = story.contract.must_avoid_pitfalls[0]
    story.scenes[1].script_text += f" Cabe destacar y {pitfall}."

    qa = StoryQAEngine()
    report = qa.evaluate(story)

    assert report.passed is False
    assert report.checks["narrative_coherence"] is False

    rules = {f.rule for f in report.findings if f.severity == "ERROR"}
    assert "narrative_opening_hook" in rules
    assert "narrative_missing_entity" in rules
    assert "narrative_prohibited_pitfall" in rules


def test_golden_case_story_qa_pass():
    """Verify the canonical Golden Case passes Story QA cleanly with zero errors."""
    architect = StoryArchitect()
    story = architect.synthesize_story(topic="La evolución del automóvil")

    qa = StoryQAEngine()
    report = qa.evaluate(story)

    assert report.passed is True
    assert all(report.checks.values())
    assert story.status == "qa_passed"

    # All scenes must have individual QA passed
    assert all(scene.scene_qa_passed for scene in story.scenes)
    assert all(len(scene.scene_qa_failures) == 0 for scene in story.scenes)

    # Zero ERROR severity findings
    error_findings = [f for f in report.findings if f.severity == "ERROR"]
    assert len(error_findings) == 0

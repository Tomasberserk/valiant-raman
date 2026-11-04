"""Golden Test Suite for Phase 0 Acceptance Criteria (GA-01 to GA-10).

Validates:
- Mode detection (Narrative Fiction vs Factual Curiosity)
- Eradication of silent canned documentary placeholders
- Semantic Anti-Template Validator enforcement
- Creative Interpreter & Service narrative preservation
"""

import pytest
from engine.creative.interpreter import CreativeInterpreter
from engine.creative.knowledge import KnowledgeBank, KnowledgeNotFoundError
from engine.creative.modes import ContentModeRequest, ContentModeRouter, ResolvedContentMode
from engine.creative.service import CreativeService
from engine.experiments.repository import ExperimentRepository
from engine.scripting.schema import HookType, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider, SemanticScriptProvider
from engine.story.semantic_qa import (
    SemanticAntiTemplateValidator,
    SemanticPolicyViolationError,
)

SWORD_PROMPT = (
    "Un chico encuentra una espada, enterrada en un bosque perdido. "
    "Al sujetarla con sus manos el cielo cambia, pasa de estar vivo y brilloso "
    "a oscuro con relámpagos, viendo en el horizonte cómo almas carroñeras lo "
    "señalan para matarlo, haciendo una secuencia de acción muy chimba."
)

FACTUAL_PROMPT = "Quiero un video sobre el telescopio espacial James Webb y cómo observa las primeras galaxias del universo."


def test_ga01_detect_narrative_fiction_mode():
    """GA-01: Detects sword prompt strictly as NARRATIVE_FICTION."""
    mode = ContentModeRouter.resolve_mode(SWORD_PROMPT)
    assert mode == ResolvedContentMode.NARRATIVE_FICTION


def test_ga02_factual_mode_distinction():
    """GA-08: Factual curiosity is correctly detected and distinguished."""
    mode = ContentModeRouter.resolve_mode(FACTUAL_PROMPT)
    assert mode == ResolvedContentMode.FACTUAL_CURIOSITY


def test_ga03_semantic_anti_template_validator_catches_cliches():
    """GA-03: Rejects documentary filler clichés in narrative mode."""
    cliche_text = (
        "¿Sabías que existe un hecho fascinante y comprobado sobre un chico encuentra una espada? "
        "Al investigar a fondo, los expertos descubrieron patrones que transformaron su comprensión."
    )

    result = SemanticAntiTemplateValidator.validate_text(
        cliche_text,
        mode=ResolvedContentMode.NARRATIVE_FICTION,
    )
    assert not result.is_valid
    assert len(result.violations) >= 3

    with pytest.raises(SemanticPolicyViolationError):
        SemanticAntiTemplateValidator.validate_text(
            cliche_text,
            mode=ResolvedContentMode.NARRATIVE_FICTION,
            raise_on_violation=True,
        )


def test_ga04_semantic_anti_template_validator_passes_narrative():
    """Legitimate cinematic narrative passes semantic anti-template linting."""
    narrative_text = (
        "Al empuñar la espada oculta en el bosque, el cielo se desgarró en relámpagos y sombras. "
        "Criaturas espectrales emergieron del horizonte dispuestas a destruirlo."
    )
    result = SemanticAntiTemplateValidator.validate_text(
        narrative_text,
        mode=ResolvedContentMode.NARRATIVE_FICTION,
        raise_on_violation=True,
    )
    assert result.is_valid
    assert len(result.violations) == 0


def test_ga05_no_canned_dynamic_custom_in_knowledge_bank():
    """KnowledgeBank find_fact does NOT synthesize fake documentary placeholders."""
    # When raise_on_missing=True, raises KnowledgeNotFoundError
    with pytest.raises(KnowledgeNotFoundError):
        KnowledgeBank.find_fact(
            "un chico encuentra una espada perdida",
            clean_topic="un chico encuentra una espada perdida",
            raise_on_missing=True,
        )

    # When raise_on_missing=False, returns standard catalog fact, NEVER dynamic_custom with canned string
    fact = KnowledgeBank.find_fact(
        "un chico encuentra una espada perdida",
        clean_topic="un chico encuentra una espada perdida",
        raise_on_missing=False,
    )
    assert fact.id != "dynamic_custom"
    assert "un chico encuentra una espada" not in fact.hook_question.lower()


def test_ga06_interpreter_produces_narrative_concepts_without_documentary_filler():
    """CreativeInterpreter produces 3 dramatic cinematic concepts preserving the sword prompt."""
    interpreter = CreativeInterpreter()
    res = interpreter.interpret(SWORD_PROMPT)

    assert res.content_mode == ResolvedContentMode.NARRATIVE_FICTION.value
    assert res.suggested_format == "cinematic_narrative"
    assert len(res.concepts) == 3

    for c in res.concepts:
        # None of the concepts should have the documentary clichés
        assert "¿sabías que existe un hecho fascinante" not in c.hook_text.lower()
        assert "expertos descubrieron" not in c.hook_text.lower()
        # Should reflect narrative tension
        assert any(w in c.hook_text.lower() for w in ["espada", "bosque", "cielo", "relámpagos", "almas", "sombras", "oscura"])


def test_ga07_scriptwriter_narrative_generation_clean():
    """Scriptwriter produces cinematic segments instead of researchers discovering patterns."""
    provider = SemanticScriptProvider()
    plan = VariantPlan(
        variant_code="A",
        hook_type=HookType.STORY_IN_MEDIAS_RES,
        target_duration_sec=25.0,
        topic=SWORD_PROMPT,
        parameters={"content_mode": "narrative_fiction"},
    )

    script = provider.generate_script("Hipótesis narrativa", plan)
    full_text = script.full_text()

    # Must pass semantic QA
    result = SemanticAntiTemplateValidator.validate_text(
        full_text,
        mode=ResolvedContentMode.NARRATIVE_FICTION,
        raise_on_violation=True,
    )
    assert result.is_valid
    assert "investigadores de todo el mundo" not in full_text
    assert "patrones que transformaron" not in full_text


def test_ga08_dummy_scriptwriter_narrative_support():
    """DummyScriptProvider also provides narrative support when content_mode is narrative_fiction."""
    dummy = DummyScriptProvider()
    plan = VariantPlan(
        variant_code="A",
        hook_type=HookType.STORY_IN_MEDIAS_RES,
        target_duration_sec=25.0,
        topic=SWORD_PROMPT,
        parameters={"content_mode": "narrative_fiction"},
    )
    script = dummy.generate_script("Hipótesis", plan)
    full_text = script.full_text()
    assert "investigadores" not in full_text
    assert "relámpagos" in full_text.lower() or "oscuridad" in full_text.lower()

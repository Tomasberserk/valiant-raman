"""Unit tests for Phase B: Pydantic schemas, validation constraints, and deterministic script generation."""

import pytest
from pydantic import ValidationError

from engine.scripting.schema import HookType, ScriptSegment, StructuredScript, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider, ScriptwriterService


def test_valid_structured_script():
    """Verify that a properly formed script passes validation."""
    script = StructuredScript(
        title="Test Script",
        hook_type=HookType.QUESTION,
        hook="¿Sabías esto?",
        segments=[
            ScriptSegment(
                order=1,
                text="Primer segmento de prueba.",
                duration_target_sec=10.0,
                visual_cue="Visual 1",
            ),
            ScriptSegment(
                order=2,
                text="Segundo segmento de prueba.",
                duration_target_sec=15.0,
                visual_cue="Visual 2",
            ),
        ],
        target_duration_sec=25.0,
        cta="Comenta qué opinas.",
    )
    assert script.title == "Test Script"
    assert len(script.segments) == 2
    assert "Primer segmento de prueba." in script.full_text()


def test_invalid_script_validations():
    """Verify that validation catches blank fields, empty segments, and non-consecutive order."""
    # Blank hook
    with pytest.raises(ValidationError):
        StructuredScript(
            title="Invalid",
            hook_type=HookType.STATEMENT,
            hook="   ",
            segments=[
                ScriptSegment(order=1, text="Text", duration_target_sec=5.0, visual_cue="Cue")
            ],
            target_duration_sec=5.0,
            cta="CTA",
        )

    # Empty segments
    with pytest.raises(ValidationError):
        StructuredScript(
            title="Invalid",
            hook_type=HookType.STATEMENT,
            hook="Valid Hook",
            segments=[],
            target_duration_sec=5.0,
            cta="CTA",
        )

    # Non-consecutive order (1 then 3)
    with pytest.raises(ValidationError, match="Segment order must be consecutive"):
        StructuredScript(
            title="Invalid",
            hook_type=HookType.STATEMENT,
            hook="Valid Hook",
            segments=[
                ScriptSegment(order=1, text="One", duration_target_sec=5.0, visual_cue="Cue 1"),
                ScriptSegment(order=3, text="Three", duration_target_sec=5.0, visual_cue="Cue 2"),
            ],
            target_duration_sec=10.0,
            cta="CTA",
        )

    # Negative segment duration
    with pytest.raises(ValidationError):
        ScriptSegment(order=1, text="Text", duration_target_sec=-5.0, visual_cue="Cue")


def test_deterministic_scriptwriter_variants():
    """Verify that DummyScriptProvider generates distinct, valid scripts for variants A, B, and C."""
    provider = DummyScriptProvider()
    service = ScriptwriterService(provider)

    plans = [
        VariantPlan(variant_code="A", hook_type=HookType.QUESTION, topic="el Telescopio James Webb"),
        VariantPlan(variant_code="B", hook_type=HookType.STATEMENT, topic="el Telescopio James Webb"),
        VariantPlan(variant_code="C", hook_type=HookType.SURPRISE, topic="el Telescopio James Webb"),
    ]

    scripts = service.create_variant_scripts(
        hypothesis_statement="Hook interrogativo retiene más que afirmativo",
        plans=plans,
    )

    assert len(scripts) == 3

    # Check distinct hook types and texts
    assert scripts[0].hook_type == HookType.QUESTION
    assert "¿Sabías que existe un misterio" in scripts[0].hook

    assert scripts[1].hook_type == HookType.STATEMENT
    assert "Este es el hecho más impactante" in scripts[1].hook

    assert scripts[2].hook_type == HookType.SURPRISE
    assert "está completamente equivocado" in scripts[2].hook

    # Verify reproducibility (same inputs produce identical output)
    script_a_second_call = provider.generate_script(
        hypothesis_statement="Hook interrogativo retiene más que afirmativo",
        plan=plans[0],
    )
    assert scripts[0].model_dump() == script_a_second_call.model_dump()


def test_custom_hook_text_priority_and_fallback():
    """Verify plan.parameters['hook_text'] takes priority, and fallback preserves historical behavior."""
    provider = DummyScriptProvider()

    # Case 1: Custom hook_text provided in parameters
    custom_plan = VariantPlan(
        variant_code="A",
        hook_type=HookType.QUESTION,
        topic="la materia oscura",
        parameters={"hook_text": "¿Por qué el 85% del universo es completamente invisible?"},
    )
    script_custom = provider.generate_script("Test hypo", custom_plan)
    assert script_custom.hook == "¿Por qué el 85% del universo es completamente invisible?"

    # Case 2: No custom hook provided in parameters (historical fallback preserved)
    fallback_plan = VariantPlan(
        variant_code="B",
        hook_type=HookType.STATEMENT,
        topic="la materia oscura",
        parameters={},
    )
    script_fallback = provider.generate_script("Test hypo", fallback_plan)
    assert "Este es el hecho más impactante y comprobado sobre la materia oscura" in script_fallback.hook


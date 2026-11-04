"""Tests for Stage 2: CreativeInterpreter, IdeationMemory, and CreativeService."""

from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from engine.creative.ideation_memory import IdeationMemory
from engine.creative.interpreter import CreativeInterpreter
from engine.creative.models import Concept, Idea, Series
from engine.creative.service import CreativeService
from engine.experiments.models import Experiment, Hypothesis, Variant
from engine.experiments.repository import ExperimentRepository
from engine.scripting.schema import HookType


@pytest.fixture
def test_repo(tmp_path: Path) -> ExperimentRepository:
    """Provide an isolated ExperimentRepository with an empty migrated SQLite database."""
    db_file = tmp_path / "test_creative.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    repo = ExperimentRepository(db_url)
    repo.init_db()
    return repo


def test_interpreter_validation_and_determinism():
    """Verify interpreter validates min length and produces deterministic contrastive concepts."""
    interpreter = CreativeInterpreter()

    # Short input validation
    with pytest.raises(ValueError, match="demasiado breve"):
        interpreter.interpret("Hola")

    with pytest.raises(ValueError, match="demasiado breve"):
        interpreter.interpret("   12345   ")

    # Valid input determinism
    text = "Quiero hacer un video explicando por qué el cielo nocturno es oscuro si hay infinitas estrellas (paradoja de Olbers)."
    res1 = interpreter.interpret(text)
    res2 = interpreter.interpret(text)

    assert res1.theme == res2.theme
    assert len(res1.concepts) == 3
    assert [c.concept_number for c in res1.concepts] == [1, 2, 3]

    hook_types = [c.hook_type for c in res1.concepts]
    assert hook_types == [HookType.QUESTION.value, HookType.SURPRISE.value, HookType.STATEMENT.value]

    # Verify contrastive hooks
    assert res1.concepts[0].hook_text != res1.concepts[1].hook_text
    assert res1.concepts[1].hook_text != res1.concepts[2].hook_text


def test_ideation_memory_honesty(test_repo: ExperimentRepository):
    """Verify IdeationMemory honesty: structured FACT, OPPORTUNITY, HYPOTHESIS separation."""
    memory = IdeationMemory()

    with test_repo.get_session() as session:
        # Case 1: Empty database (< 3 experiments)
        report_empty = memory.diagnose_and_suggest(session)
        assert report_empty.has_enough_history is False
        assert report_empty.total_experiments == 0
        assert "insuficiente" in report_empty.fact.lower()
        assert len(report_empty.opportunity) > 0
        assert len(report_empty.hypothesis) > 0
        assert len(report_empty.suggested_prompts) > 0

        # Case 2: Populate 3 experiments with unbalanced hooks
        # Exp 1: 3 QUESTION variants
        # Exp 2: 3 QUESTION variants
        # Exp 3: 2 QUESTION variants, 1 STATEMENT variant
        # (SURPRISE has 0)
        for i in range(3):
            exp = Experiment(name=f"Exp {i}", description="Test")
            session.add(exp)
            session.flush()

            hypo = Hypothesis(
                experiment_id=exp.id,
                statement="Hypo",
                independent_variable="hook_type",
                primary_metric="RETENTION_3S",
                success_criterion="Test",
                baseline_description="Test",
            )
            session.add(hypo)
            session.flush()

            v1 = Variant(name="Var A", hypothesis_id=hypo.id, variant_code="A", hook_type=HookType.QUESTION.value)
            session.add(v1)

            if i == 2:
                v2 = Variant(name="Var B", hypothesis_id=hypo.id, variant_code="B", hook_type=HookType.STATEMENT.value)
            else:
                v2 = Variant(name="Var B", hypothesis_id=hypo.id, variant_code="B", hook_type=HookType.QUESTION.value)
            session.add(v2)

            v3 = Variant(name="Var C", hypothesis_id=hypo.id, variant_code="C", hook_type=HookType.QUESTION.value)
            session.add(v3)

        session.commit()

        # Diagnose with 3 experiments
        report_populated = memory.diagnose_and_suggest(session)
        assert report_populated.has_enough_history is True
        assert report_populated.total_experiments == 3
        assert report_populated.hook_distribution[HookType.QUESTION.value] == 8
        assert report_populated.hook_distribution[HookType.STATEMENT.value] == 1
        assert report_populated.hook_distribution[HookType.SURPRISE.value] == 0
        assert HookType.SURPRISE.value in report_populated.underrepresented_hooks

        # Epistemological separation: FACT, OPPORTUNITY, HYPOTHESIS
        assert "3 experimentos registrados" in report_populated.fact
        assert "SURPRISE" in report_populated.opportunity
        assert "evidencia comparable" in report_populated.hypothesis.lower()

        # Must not infer "menos utilizado = mejor" or "peor"
        for forbidden in ["mejor", "peor", "ganador", "superior", "inferior"]:
            assert forbidden not in report_populated.hypothesis.lower()


def test_creative_service_capture_and_analysis_lifecycle(test_repo: ExperimentRepository):
    """Test full Idea and Concept lifecycle from capture to selection."""
    service = CreativeService(repository=test_repo)

    # 1. Capture idea
    raw_text = "El misterio del manuscrito Voynich y los criptógrafos que enloquecieron intentando descifrarlo"
    idea = service.capture_idea(raw_text=raw_text)
    assert idea.id is not None
    assert idea.status == "captured"

    # 2. Analyze idea -> generates 3 concepts
    concepts = service.analyze_idea(idea.id)
    assert len(concepts) == 3
    assert [c.concept_number for c in concepts] == [1, 2, 3]
    for c in concepts:
        assert c.status == "proposed"

    # Subsequent analyze call without force_regenerate returns existing
    concepts_cached = service.analyze_idea(idea.id)
    assert [c.id for c in concepts_cached] == [c.id for c in concepts]

    # 3. Select concept 2 (SURPRISE)
    c2 = concepts[1]
    selected = service.select_concept(c2.id)
    assert selected.status == "selected"

    # Check sibling concepts are rejected (only 1 selected allowed per idea)
    with test_repo.get_session() as session:
        c1 = session.get(Concept, concepts[0].id)
        c3 = session.get(Concept, concepts[2].id)
        assert c1.status == "rejected"
        assert c3.status == "rejected"


def test_creative_service_compile_experiment_isolation_and_neutrality(test_repo: ExperimentRepository):
    """Test that compile_experiment creates neutral Hypothesis, and canonical A/B/C VariantPlans."""
    service = CreativeService(repository=test_repo)

    # Setup series, idea, and concept
    with test_repo.get_session() as session:
        series = Series(name="Criptografía Histórica", premise="Enigmas de la historia")
        session.add(series)
        session.commit()
        series_id = series.id

    idea = service.capture_idea(
        raw_text="La máquina Enigma y cómo Alan Turing descifró los códigos secretos navales",
        series_id=series_id,
    )
    concepts = service.analyze_idea(idea.id)
    concept_to_select = concepts[0]  # QUESTION concept
    service.select_concept(concept_to_select.id)

    # Compile experiment
    experiment, hypothesis, variant_plans = service.compile_experiment(concept_to_select.id)

    assert experiment.id is not None
    assert experiment.source_concept_id == concept_to_select.id
    assert experiment.series_id == series_id
    assert experiment.status == "draft"

    # Neutral Hypothesis verification
    assert hypothesis.experiment_id == experiment.id
    assert hypothesis.independent_variable == "hook_type"
    assert hypothesis.primary_metric == "RETENTION_3S"
    assert "evaluar el impacto comparativo" in hypothesis.statement.lower()

    # Must NOT assume winner or superiority
    for forbidden in ["maximizará", "ganará", "superará", "mejor", "rendimiento superior"]:
        assert forbidden not in hypothesis.statement.lower()

    # Canonical order A=QUESTION, B=STATEMENT, C=SURPRISE
    assert len(variant_plans) == 3
    assert [vp.variant_code for vp in variant_plans] == ["A", "B", "C"]
    assert variant_plans[0].hook_type == HookType.QUESTION
    assert variant_plans[1].hook_type == HookType.STATEMENT
    assert variant_plans[2].hook_type == HookType.SURPRISE

    # Invariable: Same topic, same angle, same target duration
    topics = {vp.topic for vp in variant_plans}
    angles = {vp.angle for vp in variant_plans}
    durations = {vp.target_duration_sec for vp in variant_plans}
    assert len(topics) == 1, "All variants must share the identical topic"
    assert len(angles) == 1, "All variants must share the identical angle"
    assert len(durations) == 1, "All variants must share the identical target duration"

    # Verify concept hook_text is injected into matching variant parameters
    assert variant_plans[0].parameters.get("hook_text") == concept_to_select.hook_text

    # Verify concept and idea status transition to converted
    with test_repo.get_session() as session:
        re_concept = session.get(Concept, concept_to_select.id)
        assert re_concept.status == "converted"
        re_idea = session.get(Idea, idea.id)
        assert re_idea.status == "converted"


def test_creative_service_regeneration_preserves_history(test_repo: ExperimentRepository):
    """Verify force_regenerate preserves previous concepts as superseded without destructive deletes."""
    service = CreativeService(repository=test_repo)

    idea = service.capture_idea(raw_text="El telescopio James Webb y la primera luz del universo cósmico")

    # Initial generation
    gen1_concepts = service.analyze_idea(idea.id, force_regenerate=False)
    assert len(gen1_concepts) == 3
    gen1_ids = [c.id for c in gen1_concepts]
    assert all(c.generation == 1 for c in gen1_concepts)

    # Force regenerate: must NOT delete gen1; transitions gen1 to superseded, creates gen2
    gen2_concepts = service.analyze_idea(idea.id, force_regenerate=True)
    assert len(gen2_concepts) == 3
    gen2_ids = [c.id for c in gen2_concepts]
    assert all(c.generation == 2 for c in gen2_concepts)

    # Verify distinct IDs
    assert set(gen1_ids).isdisjoint(set(gen2_ids))

    # Verify database state: both generations exist!
    with test_repo.get_session() as session:
        saved_idea = session.get(Idea, idea.id)
        assert saved_idea.status == "analyzed"
        all_concepts = saved_idea.concepts
        assert len(all_concepts) == 6  # 3 superseded + 3 proposed

        superseded = [c for c in all_concepts if c.status == "superseded"]
        assert len(superseded) == 3
        assert {c.id for c in superseded} == set(gen1_ids)

        active = saved_idea.get_active_concepts()
        assert len(active) == 3
        assert {c.id for c in active} == set(gen2_ids)

    # Verify that converted concepts block regeneration
    selected_concept = service.select_concept(gen2_concepts[0].id)
    service.compile_experiment(selected_concept.id)

    # Now that a concept is converted, regeneration must be strictly rejected
    with pytest.raises(ValueError, match="already converted"):
        service.analyze_idea(idea.id, force_regenerate=True)


def test_creative_service_reject_concept_standalone(test_repo: ExperimentRepository):
    """Verify reject_concept directly transitions a concept to rejected."""
    service = CreativeService(repository=test_repo)
    idea = service.capture_idea(raw_text="Exploración de la fosa de las Marianas y organismos extremófilos")
    concepts = service.analyze_idea(idea.id)

    target_concept = concepts[0]
    rejected = service.reject_concept(target_concept.id)
    assert rejected.status == "rejected"

    with test_repo.get_session() as session:
        re_loaded = session.get(Concept, target_concept.id)
        assert re_loaded.status == "rejected"


def test_creative_service_i_am_blocked_integration(test_repo: ExperimentRepository):
    """Test that i_am_blocked integrates cleanly with repository through CreativeService."""
    service = CreativeService(repository=test_repo)
    report = service.i_am_blocked()
    assert report is not None
    assert isinstance(report.suggested_prompts, list)
    assert len(report.suggested_prompts) > 0
    assert len(report.fact) > 0
    assert len(report.opportunity) > 0
    assert len(report.hypothesis) > 0

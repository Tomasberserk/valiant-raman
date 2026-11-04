"""Creative Service: Domain coordinator for idea capture, analysis, concept selection, and experiment compilation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from engine.creative.ideation_memory import BlockedReport, IdeationMemory
from engine.creative.interpreter import CreativeInterpreter
from engine.creative.models import Concept, Idea, Series
from engine.experiments.models import Experiment, ExperimentRun, Hypothesis, Render
from engine.experiments.repository import ExperimentRepository
from engine.scripting.schema import HookType, VariantPlan


@dataclass
class MediaDescriptor:
    """Encapsulates render provenance and physical file resolution for media delivery."""
    run_id: str
    render_id: str
    variant_code: str
    resolved_path: Path
    content_type: str = "video/mp4"


class CreativeService:
    """Coordinator service managing the lifecycle of creative ideation into technical experiments."""

    def __init__(
        self,
        repository: ExperimentRepository,
        interpreter: Optional[CreativeInterpreter] = None,
        memory: Optional[IdeationMemory] = None,
        dispatcher: Optional[Any] = None,
    ):
        self.repository = repository
        self.interpreter = interpreter or CreativeInterpreter()
        self.memory = memory or IdeationMemory()
        self.dispatcher = dispatcher

    def capture_idea(
        self,
        raw_text: str,
        input_type: str = "text",
        series_id: Optional[str] = None,
    ) -> Idea:
        """Capture and persist a raw creative idea."""
        cleaned = raw_text.strip()
        if len(cleaned) < CreativeInterpreter.MIN_TEXT_LENGTH:
            raise ValueError(
                f"El texto de la idea es demasiado breve ({len(cleaned)} caracteres). "
                f"Proporciona al menos {CreativeInterpreter.MIN_TEXT_LENGTH} caracteres con más contexto o detalles."
            )

        with self.repository.get_session() as session:
            # Validate series if provided
            if series_id:
                series = session.get(Series, series_id)
                if not series:
                    raise ValueError(f"Series with id '{series_id}' does not exist.")

            # Quick initial topic extraction
            initial_topic = self.interpreter._extract_topic(cleaned.split("\n")[0])

            idea = Idea(
                raw_input=cleaned,
                input_type=input_type,
                theme=initial_topic,
                editorial_angle=f"Exploración inicial sobre {initial_topic}",
                status="captured",
                series_id=series_id,
            )
            session.add(idea)
            session.commit()
            session.refresh(idea)
            return idea

    def analyze_idea(self, idea_id: str, force_regenerate: bool = False) -> List[Concept]:
        """Analyze an idea using CreativeInterpreter and generate 3 contrastive concepts."""
        with self.repository.get_session() as session:
            idea = session.get(Idea, idea_id)
            if not idea:
                raise ValueError(f"Idea with id '{idea_id}' does not exist.")

            # Check existing concepts
            active_concepts = idea.get_active_concepts()
            if active_concepts and not force_regenerate:
                return active_concepts

            # If force_regenerate, ensure none is already converted
            for c in idea.concepts:
                if c.status == "converted":
                    raise ValueError(
                        f"Cannot regenerate concepts for idea '{idea_id}'; "
                        f"concept '{c.id}' is already converted into an experiment."
                    )

            # Preserve history: transition existing active/rejected concepts to superseded
            if idea.concepts and force_regenerate:
                for c in list(idea.concepts):
                    if c.status in ("proposed", "selected", "rejected"):
                        c.transition_to("superseded")
                session.flush()

            # Determine next generation index
            next_generation = max((c.generation for c in idea.concepts), default=0) + 1

            # Run deterministic interpretation
            result = self.interpreter.interpret(idea.raw_input)

            # Update idea properties
            idea.theme = result.theme
            idea.editorial_angle = result.editorial_angle
            idea.series_potential = result.series_potential
            idea.suggested_format = result.suggested_format
            idea.status = "analyzed"

            # Create 3 concept entities with incremented generation
            new_concepts: List[Concept] = []
            for draft in result.concepts:
                concept = Concept(
                    idea_id=idea.id,
                    generation=next_generation,
                    concept_number=draft.concept_number,
                    title=draft.title,
                    hook_text=draft.hook_text,
                    hook_type=draft.hook_type,
                    angle_description=draft.angle_description,
                    status="proposed",
                )
                session.add(concept)
                new_concepts.append(concept)


            session.commit()
            for c in new_concepts:
                session.refresh(c)
            return new_concepts

    def select_concept(self, concept_id: str, custom_hook: Optional[str] = None) -> Concept:
        """Select a concept, optionally update hook_text, and enforce single selection per idea."""
        with self.repository.get_session() as session:
            concept = session.get(Concept, concept_id)
            if not concept:
                raise ValueError(f"Concept with id '{concept_id}' does not exist.")

            if custom_hook and isinstance(custom_hook, str) and custom_hook.strip():
                concept.hook_text = custom_hook.strip()

            if concept.status == "converted":
                session.commit()
                session.refresh(concept)
                return concept

            # Reject all sibling concepts for the same idea
            sibling_concepts = (
                session.query(Concept)
                .filter(Concept.idea_id == concept.idea_id, Concept.id != concept.id)
                .all()
            )
            for sibling in sibling_concepts:
                if sibling.status in ("proposed", "selected"):
                    sibling.transition_to("rejected")

            concept.transition_to("selected")
            session.commit()
            session.refresh(concept)
            return concept

    def reject_concept(self, concept_id: str) -> Concept:
        """Explicitly reject a concept."""
        with self.repository.get_session() as session:
            concept = session.get(Concept, concept_id)
            if not concept:
                raise ValueError(f"Concept with id '{concept_id}' does not exist.")

            concept.transition_to("rejected")
            session.commit()
            session.refresh(concept)
            return concept

    def compile_experiment(
        self, concept_id: str
    ) -> Tuple[Experiment, Hypothesis, List[VariantPlan]]:
        """Compile a selected concept into an Experiment, Hypothesis, and 3 VariantPlans."""
        from engine.creative.knowledge import KnowledgeBank

        with self.repository.get_session() as session:
            concept = session.get(Concept, concept_id)
            if not concept:
                raise ValueError(f"Concept with id '{concept_id}' does not exist.")

            if concept.status not in ("proposed", "selected"):
                raise ValueError(
                    f"Concept '{concept_id}' has status '{concept.status}' and cannot be compiled."
                )

            # Transition concept and idea to converted
            concept.transition_to("selected" if concept.status == "proposed" else concept.status)
            concept.transition_to("converted")
            concept.idea.status = "converted"

            # Create Experiment
            experiment = Experiment(
                name=f"Exp - {concept.title}",
                description=f"Derivado de concepto: '{concept.title}' (Idea: {concept.idea.theme})",
                source_concept_id=concept.id,
                series_id=concept.idea.series_id,
                status="draft",
            )
            session.add(experiment)
            session.flush()

            # Create Hypothesis with neutral comparative statement
            hypothesis = Hypothesis(
                experiment_id=experiment.id,
                statement=(
                    f"Evaluar el impacto comparativo de tres tipologías de gancho (QUESTION, STATEMENT, SURPRISE) "
                    f"sobre la retención inicial a los 3 segundos para el tema '{concept.idea.theme}'."
                ),
                independent_variable="hook_type",
                primary_metric="RETENTION_3S",
                success_criterion="Diferencia medible de retención a los 3 segundos entre variantes con un umbral mínimo de retención del 35% en al menos una variante",
                baseline_description="Promedio de retención estándar en formato corto",
            )
            session.add(hypothesis)
            session.flush()

            # Retrieve factual capsule for bulletproof consistency
            fact = KnowledgeBank.find_fact(concept.idea.theme)
            topic = fact.topic
            angle = concept.angle_description
            
            # Detect duration constraint dynamically from raw idea input
            _, target_duration = self.interpreter._extract_topic_and_constraints(concept.idea.raw_input)

            variant_plans = [
                VariantPlan(
                    variant_code="A",
                    hook_type=HookType.QUESTION,
                    target_duration_sec=target_duration,
                    topic=topic,
                    angle=angle,
                    parameters={
                        "hook_text": (
                            concept.hook_text
                            if concept.hook_type == HookType.QUESTION.value
                            else fact.hook_question
                        ),
                        "source_concept_id": concept.id,
                    },
                ),
                VariantPlan(
                    variant_code="B",
                    hook_type=HookType.STATEMENT,
                    target_duration_sec=target_duration,
                    topic=topic,
                    angle=angle,
                    parameters={
                        "hook_text": (
                            concept.hook_text
                            if concept.hook_type == HookType.STATEMENT.value
                            else fact.hook_statement
                        ),
                        "source_concept_id": concept.id,
                    },
                ),
                VariantPlan(
                    variant_code="C",
                    hook_type=HookType.SURPRISE,
                    target_duration_sec=target_duration,
                    topic=topic,
                    angle=angle,
                    parameters={
                        "hook_text": (
                            concept.hook_text
                            if concept.hook_type == HookType.SURPRISE.value
                            else fact.hook_surprise
                        ),
                        "source_concept_id": concept.id,
                    },
                ),
            ]


            session.commit()
            session.refresh(experiment)
            session.refresh(hypothesis)
            return experiment, hypothesis, variant_plans

    def launch_experiment(self, concept_id: str) -> str:
        """Compile experiment and dispatch execution to RunDispatcher."""
        if self.dispatcher is None:
            raise NotImplementedError(
                "RunDispatcher no está configurado en este entorno. Se integrará en Etapa 4."
            )
        experiment, hypothesis, variant_plans = self.compile_experiment(concept_id)
        run_id = self.dispatcher.dispatch(experiment.id, hypothesis.id, variant_plans)
        return run_id

    def i_am_blocked(self) -> BlockedReport:
        """Diagnose past experimentation and offer targeted prompts for unexplored areas."""
        with self.repository.get_session() as session:
            return self.memory.diagnose_and_suggest(session)

    def get_idea(self, idea_id: str) -> Optional[Idea]:
        """Fetch an idea by its UUID."""
        with self.repository.get_session() as session:
            return session.get(Idea, idea_id)

    def get_concepts_for_idea(self, idea_id: str) -> List[Concept]:
        """Fetch all active concepts for a given idea."""
        with self.repository.get_session() as session:
            idea = session.get(Idea, idea_id)
            if not idea:
                return []
            return idea.get_active_concepts()

    def get_concept(self, concept_id: str) -> Optional[Concept]:
        """Fetch a concept by its UUID."""
        with self.repository.get_session() as session:
            return session.get(Concept, concept_id)

    def get_run(self, run_id: str) -> Optional[ExperimentRun]:
        """Fetch an ExperimentRun with loaded renders via repository."""
        return self.repository.get_run(run_id)

    def get_media_descriptor(self, run_id: str, variant: str) -> Optional[MediaDescriptor]:
        """Safely locate and resolve render provenance without exposing filesystem to callers."""
        run = self.repository.get_run(run_id)
        if not run:
            return None

        # Robust variant resolution: match by variant_code ('A', 'B', 'C') or render id
        render = next(
            (
                r
                for r in run.renders
                if (
                    (r.variant and r.variant.variant_code.upper() == variant.upper())
                    or r.id == variant
                )
            ),
            None,
        )
        if not render or not render.file_path:
            return None

        variant_code = render.variant.variant_code if render.variant else variant
        return MediaDescriptor(
            run_id=run_id,
            render_id=render.id,
            variant_code=variant_code,
            resolved_path=Path(render.file_path).resolve(),
            content_type="video/mp4",
        )

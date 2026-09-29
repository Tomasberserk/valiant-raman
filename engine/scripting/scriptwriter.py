"""Scriptwriter module providing decoupled interfaces and deterministic providers."""

from abc import ABC, abstractmethod
from typing import Dict, List

from engine.scripting.schema import HookType, ScriptSegment, StructuredScript, VariantPlan


class ScriptProvider(ABC):
    """Abstract interface for script generation engines."""

    @abstractmethod
    def generate_script(self, hypothesis_statement: str, plan: VariantPlan) -> StructuredScript:
        """Generate a structured script conforming to the hypothesis and variant plan."""
        pass


class DummyScriptProvider(ScriptProvider):
    """Deterministic script generator for offline runs, tests, and demo pipelines."""

    def __init__(self, seed_offset: int = 0):
        self.seed_offset = seed_offset

    def generate_script(self, hypothesis_statement: str, plan: VariantPlan) -> StructuredScript:
        """Produce a deterministic, fully structured script based on hook_type and topic."""
        topic = plan.topic.strip()

        # Deterministic hooks according to typology
        hook_map: Dict[HookType, str] = {
            HookType.QUESTION: f"¿Sabías que existe un misterio inexplicable sobre {topic} que la ciencia aún debate?",
            HookType.STATEMENT: f"Este es el hecho más impactante y comprobado sobre {topic} jamás registrado.",
            HookType.SURPRISE: f"Todo lo que te enseñaron en la escuela sobre {topic} está completamente equivocado.",
            HookType.STORY_IN_MEDIAS_RES: f"Estábamos a punto de perderlo todo cuando descubrimos la verdad sobre {topic}.",
        }

        hook = hook_map.get(
            plan.hook_type,
            f"Presta atención a lo que sucede realmente con {topic}.",
        )

        segments = [
            ScriptSegment(
                order=1,
                text=f"Durante décadas, investigadores de todo el mundo intentaron descifrar los patrones ocultos de {topic}.",
                duration_target_sec=plan.target_duration_sec * 0.35,
                visual_cue="Tomas cinematográficas de archivo y diagramas de investigación en alta definición",
                tone="curious",
            ),
            ScriptSegment(
                order=2,
                text="Los resultados revelaron una correlación directa que nadie había sido capaz de predecir hasta este momento.",
                duration_target_sec=plan.target_duration_sec * 0.40,
                visual_cue="Visualización de datos e infografía animada sobre fondo oscuro minimalista",
                tone="serious",
            ),
        ]

        cta = f"¿Tú qué opinas sobre {topic}? Déjalo en los comentarios."

        return StructuredScript(
            title=f"Experimento {plan.variant_code} - {topic}",
            hook_type=plan.hook_type,
            hook=hook,
            segments=segments,
            target_duration_sec=plan.target_duration_sec,
            cta=cta,
            metadata={
                "provider": "DummyScriptProvider",
                "variant_code": plan.variant_code,
                "hypothesis": hypothesis_statement,
                "angle": plan.angle,
            },
        )


class ScriptwriterService:
    """Coordinator service for creating variant scripts given an experiment specification."""

    def __init__(self, provider: ScriptProvider):
        self.provider = provider

    def create_variant_scripts(
        self, hypothesis_statement: str, plans: List[VariantPlan]
    ) -> List[StructuredScript]:
        """Generate structured scripts for each variant plan in the experiment."""
        return [self.provider.generate_script(hypothesis_statement, plan) for plan in plans]

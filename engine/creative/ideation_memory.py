"""Ideation Memory: Empirical, data-grounded ideation suggestions ('Estoy Bloqueado')."""

from collections import Counter
from typing import Dict, List
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from engine.experiments.models import Experiment, Variant
from engine.scripting.schema import HookType


class BlockedReport(BaseModel):
    """Empirical diagnostic report and targeted suggestions for creative blocks."""

    total_experiments: int
    hook_distribution: Dict[str, int]
    underrepresented_hooks: List[str]
    has_enough_history: bool
    fact: str
    opportunity: str
    hypothesis: str
    suggested_prompts: List[str]
    analysis_summary: str = ""


class IdeationMemory:
    """Historical ideation advisor based strictly on verified experiment history.
    
    Adheres to analytical honesty:
    - If fewer than 3 experiments exist, clearly states insufficient statistical data.
    - If 3+ experiments exist, highlights unvisited or under-tested hook quadrants.
    - Explicitly segregates FACT (observed database evidence), OPPORTUNITY (unexplored quadrant),
      and HYPOTHESIS (learning proposition without premature performance inference).
    """

    MIN_HISTORY_THRESHOLD: int = 3

    # Canonical hook types to check for coverage
    ALL_HOOKS = [
        HookType.QUESTION.value,
        HookType.STATEMENT.value,
        HookType.SURPRISE.value,
        HookType.STORY_IN_MEDIAS_RES.value,
    ]

    STARTER_PROMPTS = [
        "Desmonta un mito científico común que la mayoría de personas da por cierto.",
        "Explica una paradoja física o matemática contraintuitiva en 30 segundos.",
        "Presenta un hallazgo astronómico reciente con tono de intriga y descubrimiento.",
        "Explica el funcionamiento de un mecanismo cotidiano revelando su complejidad oculta.",
    ]

    HOOK_TARGETED_PROMPTS = {
        HookType.QUESTION.value: [
            "Formula una pregunta provocativa sobre un fenómeno diario que nadie suele cuestionar.",
            "Inicia preguntando qué pasaría en un escenario extremo e hipotético.",
        ],
        HookType.SURPRISE.value: [
            "Revela un dato chocante que contradiga directamente el sentido común.",
            "Expón un error histórico que cambió para siempre el rumbo de la ciencia.",
        ],
        HookType.STATEMENT.value: [
            "Lanza una afirmación categórica sobre un récord o límite absoluto del universo.",
            "Presenta la ley fundamental que rige un comportamiento humano o natural.",
        ],
        HookType.STORY_IN_MEDIAS_RES.value: [
            "Comienza en el momento culminante de un experimento que casi termina en catástrofe.",
            "Abre en el segundo exacto en que un científico descubrió un resultado imprevisto.",
        ],
    }

    def diagnose_and_suggest(self, session: Session) -> BlockedReport:
        """Diagnose past experimentation and generate targeted prompts for unexplored areas."""
        total_experiments = session.query(Experiment).count()

        # Query real hook counts from variants
        variant_hook_rows = (
            session.query(Variant.hook_type, func.count(Variant.id))
            .group_by(Variant.hook_type)
            .all()
        )

        hook_distribution: Dict[str, int] = {hook: 0 for hook in self.ALL_HOOKS}
        for hook_val, count in variant_hook_rows:
            if hook_val:
                hook_distribution[hook_val] = count

        has_enough_history = total_experiments >= self.MIN_HISTORY_THRESHOLD

        if not has_enough_history:
            fact = f"{total_experiments} experimentos registrados en base de datos. Historial insuficiente para inferir patrones de distribución."
            opportunity = "Iniciar la exploración sistemática de tipologías de gancho para construir una línea base comparable."
            hypothesis = "Ejecutar experimentos iniciales en cuadrantes balanceados permitirá calibrar el rendimiento relativo de los formatos cortos del canal."
            return BlockedReport(
                total_experiments=total_experiments,
                hook_distribution=hook_distribution,
                underrepresented_hooks=[],
                has_enough_history=False,
                fact=fact,
                opportunity=opportunity,
                hypothesis=hypothesis,
                analysis_summary=f"{fact} {opportunity}",
                suggested_prompts=self.STARTER_PROMPTS,
            )

        # Identify underrepresented hook types (ordered by lowest count)
        sorted_hooks = sorted(hook_distribution.items(), key=lambda item: item[1])
        min_count = sorted_hooks[0][1]
        underrepresented = [hook for hook, count in sorted_hooks if count <= min_count or count == 0]

        counts_summary = ", ".join(f"{h}: {c}" for h, c in hook_distribution.items())
        fact = f"{total_experiments} experimentos registrados ({counts_summary})."
        opportunity = f"Cuadrantes menos explorados en el historial disponible: {', '.join(underrepresented)}."
        hypothesis = (
            f"Explorar {', '.join(underrepresented)} permitirá obtener evidencia comparable "
            f"sobre su comportamiento de retención inicial frente a los cuadrantes frecuentes."
        )

        # Pick suggestions targeting underrepresented hooks
        suggested: List[str] = []
        for hook in underrepresented:
            prompts = self.HOOK_TARGETED_PROMPTS.get(hook, [])
            for p in prompts:
                if p not in suggested:
                    suggested.append(p)

        # Fallback if suggestions empty
        if not suggested:
            suggested = self.STARTER_PROMPTS

        return BlockedReport(
            total_experiments=total_experiments,
            hook_distribution=hook_distribution,
            underrepresented_hooks=underrepresented,
            has_enough_history=True,
            fact=fact,
            opportunity=opportunity,
            hypothesis=hypothesis,
            analysis_summary=f"{fact} {opportunity}",
            suggested_prompts=suggested[:4],
        )


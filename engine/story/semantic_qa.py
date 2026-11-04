"""Semantic QA & Anti-Template Validation (Phase 0).

Ensures narrative scripts never regress into formulaic documentary filler clichés.
"""

from dataclasses import dataclass, field
import re
from typing import List

from engine.creative.modes import ResolvedContentMode


class SemanticPolicyViolationError(Exception):
    """Raised when a narrative script violates editorial integrity policies."""
    pass


@dataclass
class SemanticValidationResult:
    """Result of semantic anti-template linting."""
    is_valid: bool
    violations: List[str] = field(default_factory=list)
    mode: ResolvedContentMode = ResolvedContentMode.NARRATIVE_FICTION


class SemanticAntiTemplateValidator:
    """Detects and rejects documentary and bureaucratic clichés in narrative storyboards/scripts."""

    PROHIBITED_DOCUMENTARY_PATTERNS = [
        (r"¿\s*sab[ií]as\s+que", "Cliché de apertura '¿Sabías que...'"),
        (r"un\s+hecho\s+fascinante", "Frase formulaica 'un hecho fascinante'"),
        (r"hecho\s+comprobado", "Frase factual 'hecho comprobado' en ficción"),
        (r"los\s+expertos\s+descubrieron", "Falsa apelación a autoridad 'los expertos descubrieron'"),
        (r"al\s+investigar\s+a\s+fondo", "Relleno documental 'al investigar a fondo'"),
        (r"estudios\s+demuestran", "Lenguaje de divulgación 'estudios demuestran'"),
        (r"seg[uú]n\s+los\s+cient[ií]ficos", "Cita a científicos en contexto narrativo"),
        (r"pieza\s+fundamental\s+del\s+conocimiento", "Relleno documental 'pieza fundamental del conocimiento'"),
        (r"la\s+ciencia\s+a[uú]n\s+debate", "Frase documental 'la ciencia aún debate'"),
        (r"investigadores\s+de\s+todo\s+el\s+mundo", "Frase genérica de investigadores"),
        (r"los\s+resultados\s+revelaron\s+una\s+correlaci[oó]n", "Terminología estadística en ficción"),
        (r"qued[oó]\s+registrado\s+en\s+los\s+archivos", "Cliché de archivo documental"),
    ]

    @classmethod
    def validate_text(
        cls,
        text: str,
        mode: ResolvedContentMode = ResolvedContentMode.NARRATIVE_FICTION,
        raise_on_violation: bool = False,
    ) -> SemanticValidationResult:
        """Scan text for prohibited patterns if mode is NARRATIVE_FICTION."""
        if mode != ResolvedContentMode.NARRATIVE_FICTION:
            # Factual mode is allowed to contain factual phrases
            return SemanticValidationResult(is_valid=True, violations=[], mode=mode)

        violations: List[str] = []
        for pattern, label in cls.PROHIBITED_DOCUMENTARY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(label)

        is_valid = len(violations) == 0
        if not is_valid and raise_on_violation:
            raise SemanticPolicyViolationError(
                f"Guion narrativo rechazado por violaciones semánticas de plantilla: {', '.join(violations)}"
            )

        return SemanticValidationResult(is_valid=is_valid, violations=violations, mode=mode)

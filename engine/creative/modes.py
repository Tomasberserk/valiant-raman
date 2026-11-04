"""Content mode taxonomy and heuristic intent routing (Stage 0).

Distinguishes between Narrative/Fiction storytelling and Factual/Curiosity journalism.
"""

from enum import Enum
import re
from typing import Optional


class ContentModeRequest(str, Enum):
    """User or caller requested mode (can be AUTO)."""
    AUTO = "auto"
    NARRATIVE_FICTION = "narrative_fiction"
    FACTUAL_CURIOSITY = "factual_curiosity"


class ResolvedContentMode(str, Enum):
    """Canonical, fully resolved mode for a storyboard or production pipeline."""
    NARRATIVE_FICTION = "narrative_fiction"
    FACTUAL_CURIOSITY = "factual_curiosity"


class ContentModeRouter:
    """Heuristic and pattern-based classifier separating fiction from factual requests."""

    NARRATIVE_PATTERNS = [
        # Characters & archetypes
        r"\b(?:un|una)\s+(?:chico|chica|joven|hombre|mujer|guerrero|mago|caballero|viajero|detective|anciano|niño|niña)\b",
        r"\b(?:personaje|protagonista|antagonista|héroe|villano|monstruo|espectro|criatura|almas?|drag[oó]n|demonio|carroñer[ao]s?)\b",
        # Action & storytelling verbs
        r"\b(?:sujeta|sujetó|empuña|empuñó|corre|escapa|pelea|lucha|ataca|combate|matar|matarlo|matarla|sobrevive)\b",
        r"\b(?:grita|muere|asesina|enfrenta|desata|desató|blandir)\b",
        # Narrative settings & props
        r"\b(?:espada|bosque|castillo|torre|reino|mazmorra|portal|cueva|templo|ruinas|tumba|reliquia|artefacto|hechizo|magia)\b",
        r"\b(?:rel[aá]mpagos?|tormenta|cielo cambia|horizonte|oscuridad|sombras?|maldici[oó]n|runas?)\b",
        # Explicit narrative intentions
        r"\b(?:historia|cuento|ficci[oó]n|secuencia de acci[oó]n|cinem[aá]tic[ao]|pel[ií]cula|animaci[oó]n)\b",
    ]

    FACTUAL_PATTERNS = [
        r"\b(?:dato|curiosidad|sab[ií]as que|por qu[eé]|c[oó]mo funciona|origen de|historia real|hecho|comprobado)\b",
        r"\b(?:ciencia|cient[ií]fic[ao]s?|f[ií]sica|astronom[ií]a|cosmolog[ií]a|tecnolog[ií]a|investigaci[oó]n|investigadores|estudio|estudios)\b",
        r"\b(?:universo|planetas?|telescopios?|galaxias?|estrellas?|espacio|espacial|nasa|james webb|hubble|algoritmos?|computadoras?|internet|experimentos?|paradojas?)\b",
    ]

    @classmethod
    def resolve_mode(
        cls,
        raw_text: str,
        requested_mode: Optional[ContentModeRequest] = ContentModeRequest.AUTO,
    ) -> ResolvedContentMode:
        """Resolve content mode explicitly or infer via heuristic pattern weighting."""
        if requested_mode and requested_mode != ContentModeRequest.AUTO:
            if requested_mode == ContentModeRequest.NARRATIVE_FICTION:
                return ResolvedContentMode.NARRATIVE_FICTION
            if requested_mode == ContentModeRequest.FACTUAL_CURIOSITY:
                return ResolvedContentMode.FACTUAL_CURIOSITY

        text_lower = raw_text.lower()

        narrative_score = 0
        for pattern in cls.NARRATIVE_PATTERNS:
            matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
            narrative_score += matches * 2

        factual_score = 0
        for pattern in cls.FACTUAL_PATTERNS:
            matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
            factual_score += matches * 2

        # If narrative score is strictly higher or has strong fiction markers, resolve to NARRATIVE_FICTION
        if narrative_score > factual_score:
            return ResolvedContentMode.NARRATIVE_FICTION

        # If factual score dominates
        if factual_score > narrative_score:
            return ResolvedContentMode.FACTUAL_CURIOSITY

        # Default fallback: if action verbs or characters are present, prefer narrative; otherwise curiosity
        if narrative_score > 0:
            return ResolvedContentMode.NARRATIVE_FICTION

        return ResolvedContentMode.FACTUAL_CURIOSITY

"""Creative Interpreter: Offline, deterministic editorial analysis of raw ideas."""

import re
from typing import List, Optional
from pydantic import BaseModel, Field

from engine.creative.models import Concept
from engine.creative.modes import ContentModeRequest, ContentModeRouter, ResolvedContentMode
from engine.scripting.schema import HookType
from engine.creative.knowledge import KnowledgeBank, FactCapsule


class ConceptDraft(BaseModel):
    """Structured proposal for a single concept before database persistence."""

    concept_number: int = Field(ge=1, le=3)
    title: str = Field(min_length=3)
    hook_text: str = Field(min_length=5)
    hook_type: str
    angle_description: str
    target_duration_seconds: float = 30.0


class InterpretationResult(BaseModel):
    """Complete editorial interpretation result for a raw idea."""

    theme: str
    editorial_angle: str
    series_potential: str = "media"
    suggested_format: str = "microdocumentary"
    content_mode: str = "factual_curiosity"
    concepts: List[ConceptDraft] = Field(min_length=3, max_length=3)


class CreativeInterpreter:
    """Offline, deterministic editorial interpreter.
    
    Transforms unstructured idea text into 3 contrastive concepts:
    Concept 1: QUESTION / IN_MEDIAS_RES
    Concept 2: SURPRISE / ESCALATION
    Concept 3: STATEMENT / CLIMAX
    
    Maintains a humble editorial stance: 'Esto es lo que entendí de tu idea (Sugerencia editable)'.
    """

    MIN_TEXT_LENGTH: int = 10

    def interpret(
        self,
        raw_text: str,
        mode: Optional[ContentModeRequest] = ContentModeRequest.AUTO,
    ) -> InterpretationResult:
        """Analyze raw text, resolve verified factual anchors or narrative story angles, and return 3 concepts."""
        cleaned = raw_text.strip()
        if len(cleaned) < self.MIN_TEXT_LENGTH:
            raise ValueError(
                f"El texto de la idea es demasiado breve ({len(cleaned)} caracteres). "
                f"Proporciona al menos {self.MIN_TEXT_LENGTH} caracteres con más contexto o detalles."
            )

        # 1. Resolve content mode (Narrative vs Factual)
        resolved_mode = ContentModeRouter.resolve_mode(cleaned, requested_mode=mode)

        # 2. Extract clean topic and target duration constraints
        first_line = cleaned.split("\n")[0].strip()
        topic, target_duration = self._extract_topic_and_constraints(first_line)

        # 3. Branch by mode
        if resolved_mode == ResolvedContentMode.NARRATIVE_FICTION:
            # Narrative / Cinematic Fiction Branch: preserve story premise and generate dramatic beats
            editorial_angle = f"Producción cinemática narrativa de ficción: {topic}"

            # Distill punchy hooks from the user's narrative premise
            hook_in_medias = f"Al tocar la empuñadura de aquella espada en el bosque, el cielo se quebró en relámpagos oscuros."
            if "espada" in cleaned.lower() and "cielo" in cleaned.lower():
                hook_in_medias = "Al empuñar la espada oculta en el bosque, el cielo se desgarró en relámpagos y sombras."
            elif len(topic) > 20:
                hook_in_medias = f"Nadie imaginaba lo que despertaría al descubrir {topic.lower()}."

            hook_threat = f"Creía estar solo en el bosque... hasta que las almas carroñeras en el horizonte lo señalaron para matarlo."
            hook_climax = f"La espada enterrada despertó un poder ancestral que jamás debió ser desenterrado."

            hook_question = "¿Qué harías si al empuñar una espada en el bosque, el cielo se desgarrara en relámpagos?"
            hook_surprise = "Creía estar solo en el bosque... hasta que las almas en el horizonte lo señalaron para matarlo."
            hook_statement = hook_in_medias

            concepts = [
                ConceptDraft(
                    concept_number=1,
                    title="La Amenaza del Horizonte",
                    hook_text=hook_question,
                    hook_type=HookType.QUESTION.value,
                    angle_description="Ángulo de suspenso y pregunta abierta sobre la maldición desatada.",
                    target_duration_seconds=target_duration,
                ),
                ConceptDraft(
                    concept_number=2,
                    title="El Giro Inesperado",
                    hook_text=hook_surprise,
                    hook_type=HookType.SURPRISE.value,
                    angle_description="Ángulo de sorpresa e impacto con la emboscada sobrenatural.",
                    target_duration_seconds=target_duration,
                ),
                ConceptDraft(
                    concept_number=3,
                    title="El Despertar de la Espada",
                    hook_text=hook_statement,
                    hook_type=HookType.STATEMENT.value,
                    angle_description="Apertura cinemática en plena acción con el contacto inicial del artefacto.",
                    target_duration_seconds=target_duration,
                ),
            ]

            return InterpretationResult(
                theme=topic,
                editorial_angle=editorial_angle,
                series_potential="alta",
                suggested_format="cinematic_narrative",
                content_mode=ResolvedContentMode.NARRATIVE_FICTION.value,
                concepts=concepts,
            )

        # Factual / Curiosity Branch: retrieve verified factual capsule
        fact = KnowledgeBank.find_fact(cleaned, clean_topic=topic)
        editorial_angle = f"Exploración de alto impacto sobre {fact.topic.lower()}: {fact.source_note}"

        concepts = [
            ConceptDraft(
                concept_number=1,
                title=f"¿El misterio de {fact.topic}?",
                hook_text=fact.hook_question,
                hook_type=HookType.QUESTION.value,
                angle_description="Ángulo de curiosidad y pregunta abierta para despertar intriga inmediata.",
                target_duration_seconds=target_duration,
            ),
            ConceptDraft(
                concept_number=2,
                title=f"La paradoja de {fact.topic}",
                hook_text=fact.hook_surprise,
                hook_type=HookType.SURPRISE.value,
                angle_description="Ángulo contraintuitivo que desafía una creencia establecida sobre el tema.",
                target_duration_seconds=target_duration,
            ),
            ConceptDraft(
                concept_number=3,
                title=f"{fact.topic}: El origen real",
                hook_text=fact.hook_statement,
                hook_type=HookType.STATEMENT.value,
                angle_description="Ángulo de autoridad y afirmación directa con alto impacto inicial.",
                target_duration_seconds=target_duration,
            ),
        ]

        return InterpretationResult(
            theme=fact.topic,
            editorial_angle=editorial_angle,
            series_potential="alta" if len(cleaned) > 50 else "media",
            suggested_format="microdocumentary",
            content_mode=ResolvedContentMode.FACTUAL_CURIOSITY.value,
            concepts=concepts,
        )

    def _extract_topic_and_constraints(self, text: str) -> tuple[str, float]:
        """Extract clean subject and target duration in seconds from the prompt."""
        topic = text.strip()
        target_duration = 30.0

        # 1. Detect duration constraint (e.g. 'menos de 20 segundos', 'de 10s', 'hazlo de 10 segundos')
        dur_match = re.search(
            r"(?:hazlo\s+)?(?:en\s+menos\s+de|menos\s+de|(?:de|en))\s+(\d+)\s*(?:segundos?|s)\b",
            topic,
            flags=re.IGNORECASE,
        )
        if dur_match:
            sec_req = float(dur_match.group(1))
            if sec_req <= 12.0:
                target_duration = max(8.0, sec_req)
            elif sec_req <= 20.0:
                target_duration = max(12.0, sec_req - 3.0)
            else:
                target_duration = max(15.0, min(sec_req - 6.0, 30.0))
            topic = re.sub(
                r"(?:hazlo\s+)?(?:en\s+menos\s+de|menos\s+de|(?:de|en))\s+\d+\s*(?:segundos?|s)\b",
                "",
                topic,
                flags=re.IGNORECASE,
            )

        # 2. Remove common request prefixes
        patterns = [
            r"^(?:quiero|necesito|dame|hazme|haz|cuéntame|cuenta|explica|explicar)\s+(?:un\s+video\s+(?:de|sobre)?|una\s+curiosidad\s+(?:de|sobre|histórica\s+sobre|histórica)?|un\s+dato\s+(?:curioso\s+sobre|interesante\s+sobre|sobre)?|algo\s+(?:sorprendente\s+sobre|interesante\s+sobre|sobre|de)?|qué\s+es|que\s+es)?\s*(?:de|sobre)?\s*",
            r"^(?:un\s+dato\s+curioso\s+sobre|un\s+dato\s+interesante\s+sobre|algo\s+sorprendente\s+sobre|un\s+misterio\s+sobre|un\s+hecho\s+sobre)\s*",
            r"^(?:la\s+historia\s+de|el\s+origen\s+de|el\s+misterio\s+de|la\s+verdad\s+de|el\s+secreto\s+de)\s*",
            r"^(?:¿sabías\s+que|sabías\s+que|sabias\s+que)\s*",
            r"^(?:una\s+curiosidad\s+histórica|una\s+curiosidad)\s*",
            r"^(?:un\s+video)\s*",
        ]
        for p in patterns:
            topic = re.sub(p, "", topic, flags=re.IGNORECASE)

        topic = topic.strip(".,;:?!¿¡-\"'\n\r ")

        # 3. Trailing intent qualifiers
        trailing = [
            r"(?:\s+|^)(?:que\s+pueda\s+contar\s+r[aá]pido|que\s+sea\s+r[aá]pido|que\s+sorprenda\s+a\s+alguien|que\s+sorprenda|para\s+alguien\s+que\s+no\s+sabe\s+tecnolog[ií]a|pero\s+no\s+inventes\s+nada)\b",
            r"(?:\s+|^)(?:r[aá]pido|viral)\b",
        ]
        for t in trailing:
            topic = re.sub(t, "", topic, flags=re.IGNORECASE)

        topic = topic.strip(".,;:?!¿¡-\"'\n\r ")

        # 4. Domain inference fallback if text requested domain curiosity
        if re.search(r"hist[oó]ric[ao]|historia", text, flags=re.IGNORECASE) and (
            not topic or topic.lower() in ("curiosidad", "tecnología e innovación")
        ):
            topic = "Historia"

        if not topic:
            topic = "Tecnología e Innovación"

        # Truncate cleanly if too long without awkward elisions
        if len(topic) > 60:
            words = topic[:60].split()
            topic = " ".join(words[:-1]) if len(words) > 1 else topic[:60]

        formatted_topic = topic[0].upper() + topic[1:] if len(topic) > 1 else topic.upper()
        return formatted_topic, target_duration

    def _extract_topic(self, text: str) -> str:
        """Backward-compatible helper returning clean topic title."""
        topic, _ = self._extract_topic_and_constraints(text)
        return topic


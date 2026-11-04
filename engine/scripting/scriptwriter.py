"""Scriptwriter module providing decoupled interfaces and deterministic providers."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

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

        # Deterministic hooks according to typology with priority to plan.parameters['hook_text']
        hook_map: Dict[HookType, str] = {
            HookType.QUESTION: f"¿Sabías que existe un misterio inexplicable sobre {topic} que la ciencia aún debate?",
            HookType.STATEMENT: f"Este es el hecho más impactante y comprobado sobre {topic} jamás registrado.",
            HookType.SURPRISE: f"Todo lo que te enseñaron en la escuela sobre {topic} está completamente equivocado.",
            HookType.STORY_IN_MEDIAS_RES: f"Estábamos a punto de perderlo todo cuando descubrimos la verdad sobre {topic}.",
        }

        custom_hook = plan.parameters.get("hook_text")
        if custom_hook and isinstance(custom_hook, str) and custom_hook.strip():
            hook = custom_hook.strip()
        else:
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


class SemanticScriptProvider(ScriptProvider):
    """High-quality semantic script generator creating natural, factual spoken Spanish narratives offline."""

    def generate_script(self, hypothesis_statement: str, plan: VariantPlan) -> StructuredScript:
        from engine.creative.knowledge import KnowledgeBank

        topic = plan.topic.strip()
        custom_hook = plan.parameters.get("hook_text")

        # Resolve verified factual capsule
        fact = KnowledgeBank.find_fact(topic)

        # 1. Resolve hook according to A/B/C canonical order or custom hook
        hook_map: Dict[HookType, str] = {
            HookType.QUESTION: fact.hook_question,
            HookType.STATEMENT: fact.hook_statement,
            HookType.SURPRISE: fact.hook_surprise,
            HookType.STORY_IN_MEDIAS_RES: f"Todo cambió por completo cuando descubrimos la verdad sobre {fact.topic.lower()}.",
        }

        if custom_hook and isinstance(custom_hook, str) and custom_hook.strip():
            hook = custom_hook.strip()
        else:
            hook = hook_map.get(plan.hook_type, fact.hook_question)

        # 2. Strict Word Budget Calculation based on speech rate (~2.1 words/sec)
        target_sec = max(plan.target_duration_sec, 8.0)
        # Allocate acoustic safety margin for pauses
        margin_sec = 1.0 if target_sec <= 12.0 else 2.0
        max_words = max(18, int((target_sec - margin_sec) * 2.1))

        # 3. Factual spoken segments from verified knowledge base
        segment1_text = fact.body_segment_1
        segment2_text = fact.body_segment_2
        cta = fact.cta

        # For very short durations (e.g. 10s), omit segment 2 and use compact CTA
        if target_sec <= 14.0 or max_words < 26:
            segment2_text = ""
            cta = "Sígueme para más."

        # Validate and enforce word budget
        candidate_words = f"{hook} {segment1_text} {segment2_text} {cta}".split()
        if len(candidate_words) > max_words:
            # Compact CTA to fit strictly within budget
            cta = "Sígueme para más."
            candidate_words = f"{hook} {segment1_text} {segment2_text} {cta}".split()
            if len(candidate_words) > max_words:
                if segment2_text:
                    # Truncate segment2 to fit word budget gracefully
                    allowed_seg2_words = max_words - len(f"{hook} {segment1_text} {cta}".split())
                    if allowed_seg2_words > 5:
                        seg2_words = segment2_text.split()[:allowed_seg2_words]
                        segment2_text = " ".join(seg2_words).rstrip(".,;") + "."
                    else:
                        segment2_text = ""
                # If still over budget, truncate segment1
                allowed_seg1_words = max_words - len(f"{hook} {cta}".split())
                if allowed_seg1_words > 5:
                    seg1_words = segment1_text.split()[:allowed_seg1_words]
                    segment1_text = " ".join(seg1_words).rstrip(".,;") + "."

        total_words = len(f"{hook} {segment1_text} {segment2_text} {cta}".split())

        segments = [
            ScriptSegment(
                order=1,
                text=segment1_text,
                duration_target_sec=round(target_sec * (0.9 if not segment2_text else 0.45), 1),
                visual_cue=f"Documentación visual y archivo sobre {fact.topic}",
                tone="curious",
            )
        ]
        if segment2_text:
            segments.append(
                ScriptSegment(
                    order=2,
                    text=segment2_text,
                    duration_target_sec=round(target_sec * 0.45, 1),
                    visual_cue="Visualización de datos e impacto histórico comprobado",
                    tone="serious",
                )
            )

        return StructuredScript(
            title=f"Short: {fact.topic}",
            hook_type=plan.hook_type,
            hook=hook,
            segments=segments,
            target_duration_sec=target_sec,
            cta=cta,
            metadata={
                "provider": "SemanticScriptProvider",
                "variant_code": plan.variant_code,
                "hypothesis": hypothesis_statement,
                "angle": plan.angle,
                "fact_id": fact.id,
                "word_count": total_words,
                "word_budget": max_words,
            },
        )


class GeminiScriptProvider(ScriptProvider):
    """Real LLM script generator leveraging Google GenAI (Gemini) with automatic structured fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        fallback_provider: Optional[ScriptProvider] = None,
    ):
        import os
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.fallback_provider = fallback_provider or SemanticScriptProvider()

    def generate_script(self, hypothesis_statement: str, plan: VariantPlan) -> StructuredScript:
        import logging
        logger = logging.getLogger(__name__)

        if not self.api_key:
            logger.info("GEMINI_API_KEY no configurada. Usando fallback semántico determinista.")
            return self.fallback_provider.generate_script(hypothesis_statement, plan)

        try:
            from google import genai
            import json

            client = genai.Client(api_key=self.api_key)
            prompt = (
                f"Eres un guionista experto en videos cortos verticales (TikTok, Reels, Shorts) en español. "
                f"Escribe un guión conciso y ultra-atrapante sobre el tema: '{plan.topic}'.\n"
                f"Tipología de gancho requerida: {plan.hook_type.value}.\n"
                f"Gancho sugerido si aplica: '{plan.parameters.get('hook_text', '')}'.\n"
                f"Duración estimada del video: {plan.target_duration_sec:.0f} segundos (aproximadamente {int(plan.target_duration_sec * 2.5)} palabras en total).\n"
                f"Reglas estrictas:\n"
                f"- Lenguaje oral, natural, fluido y entusiasta en español neutro.\n"
                f"- Cero relleno, cero jerga académica innecesaria.\n"
                f"- Devuelve ÚNICAMENTE un objeto JSON válido con este formato:\n"
                f'{{\n'
                f'  "title": "Título corto y atractivo",\n'
                f'  "hook": "Línea inicial de alto impacto (2-3 segundos)",\n'
                f'  "segments": [\n'
                f'    {{"order": 1, "text": "Primera parte del cuerpo narrativo...", "duration_target_sec": {plan.target_duration_sec * 0.4:.1f}, "visual_cue": "Descripción de visual sugerido", "tone": "curioso"}},\n'
                f'    {{"order": 2, "text": "Segunda parte y remate informativo...", "duration_target_sec": {plan.target_duration_sec * 0.4:.1f}, "visual_cue": "Descripción de visual sugerido", "tone": "asombro"}}\n'
                f'  ],\n'
                f'  "cta": "Llamado a la acción breve (ej: ¿Tú qué piensas? Déjalo en los comentarios.)"\n'
                f'}}'
            )

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )

            raw_text = response.text.strip()
            # Clean markdown JSON block fences if present
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            parsed = json.loads(raw_text)

            segments = [
                ScriptSegment(
                    order=s.get("order", idx + 1),
                    text=s.get("text", "").strip(),
                    duration_target_sec=float(s.get("duration_target_sec", plan.target_duration_sec * 0.4)),
                    visual_cue=s.get("visual_cue", "Toma cinematográfica").strip(),
                    tone=s.get("tone", "neutral").strip(),
                )
                for idx, s in enumerate(parsed.get("segments", []))
            ]

            hook = parsed.get("hook", "").strip() or plan.parameters.get("hook_text", "")

            return StructuredScript(
                title=parsed.get("title", f"Short - {plan.topic}").strip(),
                hook_type=plan.hook_type,
                hook=hook,
                segments=segments,
                target_duration_sec=plan.target_duration_sec,
                cta=parsed.get("cta", "¿Tú qué opinas? Comenta abajo.").strip(),
                metadata={
                    "provider": "GeminiScriptProvider",
                    "model": self.model,
                    "variant_code": plan.variant_code,
                    "hypothesis": hypothesis_statement,
                    "angle": plan.angle,
                },
            )
        except Exception as e:
            logger.warning(f"Error en GeminiScriptProvider ({e}). Usando fallback semántico seguro.")
            return self.fallback_provider.generate_script(hypothesis_statement, plan)


def get_default_script_provider() -> ScriptProvider:
    """Resolve the optimal script provider based on environment and available credentials."""
    import os
    provider_type = os.getenv("SCRIPT_PROVIDER", "auto").lower()

    if provider_type == "dummy":
        return DummyScriptProvider()
    elif provider_type == "semantic":
        return SemanticScriptProvider()
    else:  # auto or gemini
        if os.getenv("GEMINI_API_KEY"):
            return GeminiScriptProvider(fallback_provider=SemanticScriptProvider())
        return SemanticScriptProvider()


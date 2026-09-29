"""Deterministic research provider for offline runs and tests."""

from engine.research.base import ResearchBrief, ResearchProvider


class DummyResearchProvider(ResearchProvider):
    """Produces structured, factual research briefs deterministically without external network."""

    def research_topic(self, topic: str) -> ResearchBrief:
        clean_topic = topic.strip()
        return ResearchBrief(
            topic=clean_topic,
            summary=f"Investigación fundamental estructurada sobre {clean_topic}.",
            core_facts=[
                f"{clean_topic} es un fenómeno documentado con observaciones empíricas replicables.",
                f"La evidencia histórica muestra avances sistemáticos en la comprensión de {clean_topic}.",
                f"Nuevos instrumentos tecnológicos han permitido medir aspectos antes invisibles de {clean_topic}.",
            ],
            open_questions=[
                f"¿Cuál es el mecanismo causal principal que gobierna a {clean_topic}?",
                f"¿Cómo afectará {clean_topic} el desarrollo tecnológico futuro?",
            ],
            common_misconceptions=[
                f"Creer que {clean_topic} es un evento aleatorio sin leyes subyacentes.",
            ],
            sources=["Archivos científicos abiertos", "Literatura académica verificada"],
        )

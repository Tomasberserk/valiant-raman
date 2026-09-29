"""Research provider leveraging Google GenAI (Gemini) when credentials are available."""

import os
from typing import Optional
from engine.research.base import ResearchBrief, ResearchProvider


class GeminiResearchProvider(ResearchProvider):
    """Integrates Gemini models for factual research and editorial angle extraction."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model

    def research_topic(self, topic: str) -> ResearchBrief:
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Provide an API key or use DummyResearchProvider for offline operation."
            )

        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = (
                f"Proporciona un brief de investigación en español para un video corto educativo sobre: '{topic}'. "
                "Devuelve: hechos comprobados, preguntas abiertas y mitos comunes."
            )
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            text = response.text or ""
            return ResearchBrief(
                topic=topic,
                summary=text[:300],
                core_facts=[text[:150], text[150:300]],
                sources=["Google GenAI Research Output"],
            )
        except Exception as e:
            raise RuntimeError(f"Gemini research query failed: {str(e)}")

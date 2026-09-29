"""Research interfaces and models for factual grounding."""

from abc import ABC, abstractmethod
from typing import List
from pydantic import BaseModel, Field


class ResearchBrief(BaseModel):
    """Structured research brief containing verified facts and narrative angles."""

    topic: str
    summary: str
    core_facts: List[str] = Field(min_length=1)
    open_questions: List[str] = Field(default_factory=list)
    common_misconceptions: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class ResearchProvider(ABC):
    """Interface for research and factual grounding engines."""

    @abstractmethod
    def research_topic(self, topic: str) -> ResearchBrief:
        """Produce a structured research brief on a given topic."""
        pass

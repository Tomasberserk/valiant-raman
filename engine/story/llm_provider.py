"""LLM Provider abstraction and deterministic mock for Story Engine (Stage 12C.2).

Decouples the Story Architect from concrete LLM APIs (Gemini, Groq, OpenAI),
ensuring 100% hermetic offline testing with zero network dependencies.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract interface for structured language model generation."""

    @abstractmethod
    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        """Produce a structured output conforming strictly to the requested Pydantic schema."""
        pass

    @abstractmethod
    def metadata(self) -> Dict[str, Any]:
        """Return provider identification, model tier, and configuration details."""
        pass


class MockLLMProvider(LLMProvider):
    """Deterministic, offline mock provider for hermetic testing."""

    def __init__(
        self,
        canned_response: Optional[BaseModel] = None,
        generator_fn: Optional[Callable[[str, Type[T]], T]] = None,
        model_name: str = "mock-deterministic-v1",
    ):
        self.canned_response = canned_response
        self.generator_fn = generator_fn
        self.model_name = model_name
        self.call_history: list[dict[str, Any]] = []

    def set_canned_response(self, response: BaseModel) -> None:
        """Update canned response dynamically."""
        self.canned_response = response

    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        """Return pre-configured response or delegate to custom generator."""
        self.call_history.append({"prompt": prompt, "schema": schema.__name__})

        if self.generator_fn:
            return self.generator_fn(prompt, schema)

        if self.canned_response is not None:
            if isinstance(self.canned_response, schema):
                return self.canned_response  # type: ignore
            # Try to validate/parse dictionary or dump
            if isinstance(self.canned_response, BaseModel):
                return schema.model_validate(self.canned_response.model_dump())
            if isinstance(self.canned_response, dict):
                return schema.model_validate(self.canned_response)

        raise ValueError(
            f"MockLLMProvider has no canned response or generator configured for schema '{schema.__name__}'."
        )

    def metadata(self) -> Dict[str, Any]:
        return {
            "provider": "mock_deterministic",
            "model": self.model_name,
            "offline": True,
            "calls_made": len(self.call_history),
        }

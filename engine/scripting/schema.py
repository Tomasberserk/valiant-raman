"""Pydantic schemas for structured scripts, segments, hooks, and variant plans."""

from enum import Enum
from typing import Any, Dict, List
from pydantic import BaseModel, Field, field_validator, model_validator


class HookType(str, Enum):
    """Catalog of testable narrative hook typologies."""

    QUESTION = "QUESTION"
    STATEMENT = "STATEMENT"
    SURPRISE = "SURPRISE"
    STORY_IN_MEDIAS_RES = "STORY_IN_MEDIAS_RES"


class ScriptSegment(BaseModel):
    """An atomic segment within a structured short-form script."""

    order: int = Field(ge=1, description="1-indexed sequence order")
    text: str = Field(min_length=1, description="Spoken narrative for this segment")
    duration_target_sec: float = Field(gt=0, description="Estimated target duration in seconds")
    visual_cue: str = Field(min_length=1, description="Editorial direction for background visual")
    tone: str = Field(default="neutral", description="Emotional delivery tone")

    @field_validator("text", "visual_cue")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be blank.")
        return v.strip()


class StructuredScript(BaseModel):
    """Full structured script with timing, hook specification, and quality constraints."""

    title: str = Field(min_length=1, description="Internal title of the script")
    hook_type: HookType = Field(description="Typology of the hook used")
    hook: str = Field(min_length=1, description="Exact hook line designed for the first 2-3 seconds")
    segments: List[ScriptSegment] = Field(min_length=1, description="Ordered list of script segments")
    target_duration_sec: float = Field(gt=0, description="Target total duration in seconds")
    cta: str = Field(min_length=1, description="Call to action or thought-provoking ending")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional provenance or topic tags")

    @field_validator("title", "hook", "cta")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Text fields cannot be blank.")
        return v.strip()

    @model_validator(mode="after")
    def validate_segments_and_order(self) -> "StructuredScript":
        """Verify segments are strictly consecutive starting at 1, and target duration is valid."""
        if not self.segments:
            raise ValueError("StructuredScript must contain at least one segment.")

        expected_order = 1
        for seg in self.segments:
            if seg.order != expected_order:
                raise ValueError(
                    f"Segment order must be consecutive starting at 1. Expected {expected_order}, got {seg.order}."
                )
            expected_order += 1

        total_segment_duration = sum(s.duration_target_sec for s in self.segments)
        if total_segment_duration <= 0:
            raise ValueError("Sum of segment durations must be positive.")

        return self

    def full_text(self) -> str:
        """Combine hook, segment texts, and cta into a single coherent vocal transcript."""
        texts = [self.hook]
        for seg in self.segments:
            texts.append(seg.text)
        if self.cta:
            texts.append(self.cta)
        return " ".join(texts)


class VariantPlan(BaseModel):
    """Specification of a test variant derived from an experimental hypothesis."""

    variant_code: str = Field(pattern=r"^[A-Z]$", description="Single capital letter (A, B, C)")
    hook_type: HookType = Field(description="Hook typology to test")
    target_duration_sec: float = Field(gt=0, default=30.0, description="Target duration in seconds")
    topic: str = Field(min_length=1, description="Subject matter of the video")
    angle: str = Field(default="standard", description="Narrative angle or perspective")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary variant parameters")

"""Creative domain models: Series, Idea, and Concept with strict integrity constraints."""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from engine.experiments.models import Base, generate_uuid, now_utc


class Series(Base):
    """An overarching editorial franchise or series maintaining consistent identity."""

    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(String(100), nullable=False, default="curious")
    target_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    visual_identity_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    narrative_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # Relationships
    ideas: Mapped[List["Idea"]] = relationship("Idea", back_populates="series")
    experiments: Mapped[List["Experiment"]] = relationship(  # type: ignore[name-defined]
        "Experiment", back_populates="series"
    )

    def get_visual_identity(self) -> Dict[str, Any]:
        return json.loads(self.visual_identity_json) if self.visual_identity_json else {}

    def get_narrative_rules(self) -> Dict[str, Any]:
        return json.loads(self.narrative_rules_json) if self.narrative_rules_json else {}


class Idea(Base):
    """An uncommitted creative idea captured as text or voice."""

    __tablename__ = "ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    input_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")  # text | voice
    theme: Mapped[str] = mapped_column(String(255), nullable=False)
    editorial_angle: Mapped[str] = mapped_column(Text, nullable=False)
    series_potential: Mapped[str] = mapped_column(String(50), nullable=False, default="media")
    suggested_format: Mapped[str] = mapped_column(String(100), nullable=False, default="microdocumentary")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="captured"
    )  # captured, analyzed, converted, archived
    series_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("series.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # Relationships
    series: Mapped[Optional["Series"]] = relationship("Series", back_populates="ideas")
    concepts: Mapped[List["Concept"]] = relationship(
        "Concept", back_populates="idea", cascade="all, delete-orphan", order_by="Concept.concept_number"
    )

    def get_selected_concept(self) -> Optional["Concept"]:
        """Return the single concept selected or converted for this idea, if any."""
        for c in self.concepts:
            if c.status in ("selected", "converted"):
                return c
        return None

    def get_active_concepts(self) -> List["Concept"]:
        """Return the latest active generation of concepts (proposed, selected, converted)."""
        active = [c for c in self.concepts if c.status in ("proposed", "selected", "converted")]
        if not active:
            return []
        latest_gen = max(c.generation for c in active)
        return sorted([c for c in active if c.generation == latest_gen], key=lambda c: c.concept_number)


class Concept(Base):
    """An editorial path and testable angle derived from an idea."""

    __tablename__ = "concepts"

    __table_args__ = (
        UniqueConstraint("idea_id", "generation", "concept_number", name="uq_idea_generation_concept_number"),
        CheckConstraint("concept_number BETWEEN 1 AND 3", name="ck_concept_number_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    idea_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    concept_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    hook_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # QUESTION, STATEMENT, SURPRISE
    angle_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="proposed"
    )  # proposed -> selected -> converted OR proposed -> rejected / superseded / archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # Relationships
    idea: Mapped["Idea"] = relationship("Idea", back_populates="concepts")
    experiments: Mapped[List["Experiment"]] = relationship(  # type: ignore[name-defined]
        "Experiment", back_populates="source_concept"
    )

    def transition_to(self, new_status: str) -> None:
        """Enforce strict concept state machine transitions."""
        if self.status == new_status:
            return
        valid_transitions = {
            "proposed": ["selected", "rejected", "superseded", "archived"],
            "selected": ["converted", "rejected", "superseded", "archived"],
            "rejected": ["proposed", "selected", "superseded", "archived"],
            "superseded": [],  # Terminal historical state
            "archived": [],    # Terminal historical state
            "converted": [],   # Terminal state once compiled
        }
        allowed = valid_transitions.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid Concept status transition from '{self.status}' to '{new_status}'. Allowed: {allowed}"
            )
        self.status = new_status


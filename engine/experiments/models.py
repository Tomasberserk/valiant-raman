"""SQLAlchemy models for valiant-raman experiment tracking and asset provenance."""

from datetime import datetime, timezone
import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """Enforce SQLite foreign key constraints."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def generate_uuid() -> str:
    """Generate a clean UUID string."""
    return str(uuid.uuid4())


def now_utc() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class."""
    pass


class Experiment(Base):
    """An experiment encapsulating a hypothesis and test variants."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Relationships
    hypotheses: Mapped[List["Hypothesis"]] = relationship(
        "Hypothesis", back_populates="experiment", cascade="all, delete-orphan"
    )
    runs: Mapped[List["ExperimentRun"]] = relationship(
        "ExperimentRun", back_populates="experiment", cascade="all, delete-orphan"
    )


class Hypothesis(Base):
    """A testable, quantifiable premise explaining expected audience behavior."""

    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    experiment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    independent_variable: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_metric: Mapped[str] = mapped_column(String(255), nullable=False)
    success_criterion: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # Relationships
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="hypotheses")
    variants: Mapped[List["Variant"]] = relationship(
        "Variant", back_populates="hypothesis", cascade="all, delete-orphan"
    )


class Variant(Base):
    """A specific test variant (e.g. A: Question, B: Statement) derived from a hypothesis."""

    __tablename__ = "variants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    hypothesis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_code: Mapped[str] = mapped_column(String(10), nullable=False)  # "A", "B", "C"
    hook_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # Relationships
    hypothesis: Mapped["Hypothesis"] = relationship("Hypothesis", back_populates="variants")
    renders: Mapped[List["Render"]] = relationship("Render", back_populates="variant")

    def get_parameters(self) -> Dict[str, Any]:
        """Return parameters as dictionary."""
        return json.loads(self.parameters_json) if self.parameters_json else {}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        """Serialize parameters to JSON."""
        self.parameters_json = json.dumps(params)


class ExperimentRun(Base):
    """An execution run of an experiment producing specific renders."""

    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    experiment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")  # running, completed, failed
    pipeline_version: Mapped[str] = mapped_column(String(50), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="runs")
    renders: Mapped[List["Render"]] = relationship(
        "Render", back_populates="experiment_run", cascade="all, delete-orphan"
    )


class Asset(Base):
    """Media asset with mandatory provenance tracking."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # video, audio, font, image, script
    source: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[str] = mapped_column(String(255), nullable=False)
    creator: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    allowed_platforms: Mapped[str] = mapped_column(String(255), nullable=False, default="all")
    attribution_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    render_associations: Mapped[List["RenderAsset"]] = relationship(
        "RenderAsset", back_populates="asset", cascade="all, delete-orphan"
    )

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata as dictionary."""
        return json.loads(self.metadata_json) if self.metadata_json else {}

    def set_metadata(self, meta: Dict[str, Any]) -> None:
        """Serialize metadata to JSON."""
        self.metadata_json = json.dumps(meta)


class Render(Base):
    """Rendered audiovisual output corresponding to a variant execution."""

    __tablename__ = "renders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    experiment_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_runs.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("variants.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[float] = mapped_column(Float, nullable=False)
    codec: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    render_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    qa_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    qa_report_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # Relationships
    experiment_run: Mapped["ExperimentRun"] = relationship(
        "ExperimentRun", back_populates="renders", lazy="joined"
    )
    variant: Mapped["Variant"] = relationship(
        "Variant", back_populates="renders", lazy="joined"
    )
    asset_associations: Mapped[List["RenderAsset"]] = relationship(
        "RenderAsset", back_populates="render", cascade="all, delete-orphan"
    )
    publications: Mapped[List["Publication"]] = relationship(
        "Publication", back_populates="render", cascade="all, delete-orphan"
    )


class RenderAsset(Base):
    """Association table linking renders to their constituent assets with defined roles."""

    __tablename__ = "render_assets"

    render_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("renders.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # background_video, voiceover, subtitle_font, music

    # Relationships
    render: Mapped["Render"] = relationship("Render", back_populates="asset_associations")
    asset: Mapped["Asset"] = relationship("Asset", back_populates="render_associations")


class Publication(Base):
    """Distribution tracking for a completed render on social platforms."""

    __tablename__ = "publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    render_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("renders.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # tiktok, youtube_shorts, instagram_reels
    post_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    render: Mapped["Render"] = relationship("Render", back_populates="publications")
    metrics: Mapped[List["Metric"]] = relationship(
        "Metric", back_populates="publication", cascade="all, delete-orphan"
    )


class Metric(Base):
    """Performance measurements recorded for a published video."""

    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    publication_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_watch_time_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    likes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shares: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comments: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retention_at_3s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    publication: Mapped["Publication"] = relationship("Publication", back_populates="metrics")

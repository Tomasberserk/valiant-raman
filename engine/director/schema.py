"""Production Director Schemas and Contracts (Stage 12D.2).

Defines the operational contracts governing the ProductionDirector state machine,
idempotency, persistent job lifecycle, recovery actions, and execution results.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from engine.story.schema import EndingStrategy, FactDossier


class ProductionState(str, Enum):
    """Discrete states of the 12D production state machine."""
    CREATED = "created"
    FAILED_PRECONDITION = "failed_precondition"  # Terminal (0 retries): hash mismatch, payload corrupt
    STORY_SYNTHESIS = "story_synthesis"
    CLAIM_GROUNDING = "claim_grounding"
    FAILED_GROUNDING = "failed_grounding"        # Terminal: exhausted surgical regenerations
    STORY_QA_AUDIT = "story_qa_audit"
    FAILED_STORY_QA = "failed_story_qa"          # Terminal: contract/duration invariants invalid
    VISUAL_RESOLUTION = "visual_resolution"
    FAILED_VISUAL = "failed_visual"              # Terminal: contract failure (not asset fallback)
    SCENE_PRODUCTION = "scene_production"
    FAILED_SCENE = "failed_scene"                # Terminal: exhausted transient scene retries
    MASTER_ASSEMBLY = "master_assembly"
    FAILED_MASTER = "failed_master"              # Terminal: fatal timeline assembly/mux failure
    FINAL_MEDIA_QA = "final_media_qa"
    FAILED_MEDIA_QA = "failed_media_qa"          # Terminal: non-repairable media rejection
    COMPLETED = "completed"                      # Terminal: derived from 12B.5 CERTIFIED_FOR_PUBLICATION


class RecoveryAction(str, Enum):
    """Formal taxonomy of recovery operations."""
    RETRY = "retry"          # Transient I/O / synthesis glitch -> re-execute same operation
    REPAIR = "repair"        # Assembly / mix deviation -> re-master applying existing MasterPolicy (-14 LUFS)
    REGENERATE = "regenerate"# Grounding / content violation -> surgical re-authoring of specific scene via LLM


class CreativeBrief(BaseModel):
    """Directives guiding dramatic framing and audience tone."""
    hook_strategy: str = "surprise"
    tone: str = "curious_informative"
    target_audience: str = "general"
    ending_strategy: EndingStrategy = EndingStrategy.PAYOFF


class OutputSpec(BaseModel):
    """Physical target format specifications."""
    width: int = 1080
    height: int = 1920
    fps: float = 30.0


class JobExecutionPolicy(BaseModel):
    """Thresholds governing timeouts, limits, and recovery cycles."""
    max_surgical_regenerations: int = 3
    max_scene_retries: int = 3
    max_master_repairs: int = 1
    timeout_per_scene_sec: float = 120.0
    preserve_intermediate_artifacts: bool = True


class ProductionRequest(BaseModel):
    """Formal, idempotent entry contract for production."""
    request_id: str = Field(..., description="Idempotency key provided by client")
    topic: str = Field(..., description="Production title or core subject")
    dossier: FactDossier = Field(..., description="Immutable FactDossier from Stage 12C.1")
    creative_brief: CreativeBrief = Field(default_factory=CreativeBrief)
    output_spec: OutputSpec = Field(default_factory=OutputSpec)
    execution_policy: JobExecutionPolicy = Field(default_factory=JobExecutionPolicy)


class StateTransitionRecord(BaseModel):
    """Audit record capturing an explicit state transition."""
    from_state: ProductionState
    to_state: ProductionState
    attempt_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trigger: str
    details: Optional[str] = None


class StageError(BaseModel):
    """Diagnostic detail of an operational issue."""
    stage: str
    error_code: str
    message: str
    remediation_hint: Optional[str] = None
    attempt_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SceneExecutionMetadata(BaseModel):
    """Per-scene operational metadata for crash inspection and recovery."""
    scene_id: str
    artifact_path: Optional[Path] = None
    voice_path: Optional[Path] = None
    status: str = "pending"
    attempt_id: str = "attempt_01"
    actual_duration_sec: Optional[float] = None
    resolution_tier: Optional[str] = None
    scene_qa_passed: bool = False


class ProductionJob(BaseModel):
    """Durable, observable model of an active or completed production run."""
    job_id: str
    request_id: str
    current_state: ProductionState = ProductionState.CREATED
    current_attempt_id: str = "attempt_01"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_history: List[StateTransitionRecord] = Field(default_factory=list)

    # Artifact provenance
    workspace_dir: Path
    dossier_id: str
    dossier_sha256: str
    story_arc_path: Optional[Path] = None
    produced_scenes_count: int = 0
    scene_metadata: Dict[str, SceneExecutionMetadata] = Field(default_factory=dict)
    master_video_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    master_sha256: Optional[str] = None  # Read-only, propagated strictly from 12B.5

    # Diagnostics and recovery tracking
    errors: List[StageError] = Field(default_factory=list)
    recovery_stats: Dict[str, int] = Field(
        default_factory=lambda: {"retries": 0, "repairs": 0, "regenerations": 0}
    )


class ProductionResult(BaseModel):
    """Immutable terminal output contract delivered to client."""
    job_id: str
    request_id: str
    status: ProductionState
    is_certified: bool
    certified_master_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    master_sha256: Optional[str] = None  # Propagated strictly from 12B.5
    total_physical_duration_sec: float = 0.0
    error_summary: Optional[str] = None
    job_persisted_path: Path

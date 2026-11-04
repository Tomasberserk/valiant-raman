"""Pydantic v2 schemas for Web API request and response contracts."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# --- Ideas & Concepts ---

class IdeaCreateRequest(BaseModel):
    raw_text: str = Field(..., min_length=10, description="Texto descriptivo de la idea (mínimo 10 caracteres)")
    input_type: str = Field(default="text", description="Tipo de entrada: 'text' o 'voice'")
    series_id: Optional[str] = Field(default=None, description="UUID opcional de la serie asociada")


class ConceptDTO(BaseModel):
    id: str
    idea_id: str
    concept_number: int
    generation: int
    title: str
    hook_text: str
    hook_type: str
    angle_description: str
    status: str
    created_at: Optional[datetime] = None


class IdeaResponse(BaseModel):
    id: str
    raw_input: str
    theme: str
    editorial_angle: str
    series_potential: str
    suggested_format: str
    status: str
    series_id: Optional[str] = None
    created_at: Optional[datetime] = None
    concepts: List[ConceptDTO] = []


# --- Execution, Polling & Media ---

class LaunchResponse(BaseModel):
    run_id: str
    status: str = "queued"
    message: str = "Experimento encolado exitosamente para ejecución en background."


class RenderDTO(BaseModel):
    id: str
    variant_code: str
    hook_type: str
    duration_seconds: float
    width: int
    height: int
    qa_passed: bool
    media_url: str  # URL pública del endpoint /api/media/{run_id}/{variant_code}. NUNCA ruta física de filesystem.


class RunStatusResponse(BaseModel):
    run_id: str
    status: str  # queued | running | completed | failed
    progress_percent: int  # 0 a 100
    stage: str  # queued | scripting | voice | subtitles | rendering | qa | finalizing | completed | failed
    message: str
    current_variant: Optional[str] = None
    completed_variants: int = 0
    total_variants: int = 3
    error_message: Optional[str] = None
    renders: List[RenderDTO] = []


# --- Diagnostics ---

class BlockedReportResponse(BaseModel):
    fact: str
    opportunity: str
    hypothesis: str

"""Creative Workspace routes: Ideation, concept analysis, selection, and diagnostics."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from engine.creative.service import CreativeService
from web.deps import get_service
from web.schemas import (
    BlockedReportResponse,
    ConceptDTO,
    IdeaCreateRequest,
    IdeaResponse,
)

router = APIRouter(tags=["creative"])


def _to_concept_dto(concept) -> ConceptDTO:
    """Helper to convert domain Concept model to ConceptDTO."""
    return ConceptDTO(
        id=concept.id,
        idea_id=concept.idea_id,
        concept_number=concept.concept_number,
        generation=concept.generation,
        title=concept.title,
        hook_text=concept.hook_text,
        hook_type=concept.hook_type,
        angle_description=concept.angle_description,
        status=concept.status,
        created_at=concept.created_at,
    )


@router.post("/ideas", response_model=IdeaResponse, status_code=status.HTTP_200_OK)
def create_and_analyze_idea(
    payload: IdeaCreateRequest,
    service: CreativeService = Depends(get_service),
):
    """Capture raw creative idea and immediately run deterministic analysis generating 3 concepts."""
    try:
        idea = service.capture_idea(
            raw_text=payload.raw_text,
            input_type=payload.input_type,
            series_id=payload.series_id,
        )
        concepts = service.analyze_idea(idea.id)
        idea = service.get_idea(idea.id) or idea
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar la idea: {str(e)}",
        )

    return IdeaResponse(
        id=idea.id,
        raw_input=idea.raw_input,
        theme=idea.theme,
        editorial_angle=idea.editorial_angle,
        series_potential=idea.series_potential,
        suggested_format=idea.suggested_format,
        status=idea.status,
        series_id=idea.series_id,
        created_at=idea.created_at,
        concepts=[_to_concept_dto(c) for c in concepts],
    )


@router.get("/ideas/{idea_id}/concepts", response_model=List[ConceptDTO])
def get_idea_concepts(
    idea_id: str,
    service: CreativeService = Depends(get_service),
):
    """Retrieve active concepts associated with a given idea."""
    idea = service.get_idea(idea_id)
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Idea con id '{idea_id}' no encontrada.",
        )
    concepts = service.get_concepts_for_idea(idea_id)
    return [_to_concept_dto(c) for c in concepts]


class SelectConceptRequest(BaseModel):
    custom_hook: Optional[str] = None


@router.post("/concepts/{concept_id}/select", response_model=ConceptDTO)
def select_concept(
    concept_id: str,
    payload: Optional[SelectConceptRequest] = None,
    service: CreativeService = Depends(get_service),
):
    """Mark a concept as selected, optionally update its hook, and automatically reject sibling concepts."""
    try:
        custom_hook = payload.custom_hook if payload else None
        concept = service.select_concept(concept_id, custom_hook=custom_hook)
        return _to_concept_dto(concept)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al seleccionar concepto: {str(e)}",
        )


@router.post("/concepts/{concept_id}/reject", response_model=ConceptDTO)
def reject_concept(
    concept_id: str,
    service: CreativeService = Depends(get_service),
):
    """Explicitly reject a concept."""
    try:
        concept = service.reject_concept(concept_id)
        return _to_concept_dto(concept)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al rechazar concepto: {str(e)}",
        )


@router.get("/blocked", response_model=BlockedReportResponse)
def get_blocked_diagnosis(
    service: CreativeService = Depends(get_service),
):
    """Empirical diagnostic of past experimentation providing prompts for unexplored areas."""
    try:
        report = service.i_am_blocked()
        return BlockedReportResponse(
            fact=report.fact,
            opportunity=report.opportunity,
            hypothesis=report.hypothesis,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar diagnóstico: {str(e)}",
        )

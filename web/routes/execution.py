"""Execution and media streaming routes: Launching, hybrid progress polling, and secure video streaming."""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from config.settings import settings
from engine.creative.run_dispatcher import RunDispatcher
from engine.creative.service import CreativeService
from web.deps import get_dispatcher, get_service
from web.schemas import LaunchResponse, RenderDTO, RunStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["execution"])


def _to_render_dto(render, run_id: str) -> RenderDTO:
    """Helper to convert persistent Render model to RenderDTO exposing public media_url without filesystem paths."""
    variant_code = render.variant.variant_code if render.variant else "unknown"
    hook_type = render.variant.hook_type if render.variant else "unknown"
    return RenderDTO(
        id=render.id,
        variant_code=variant_code,
        hook_type=hook_type,
        duration_seconds=render.duration_seconds,
        width=render.width,
        height=render.height,
        qa_passed=render.qa_passed,
        media_url=f"/api/media/{run_id}/{variant_code}",
    )


@router.post("/concepts/{concept_id}/launch", response_model=LaunchResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_concept_experiment(
    concept_id: str,
    service: CreativeService = Depends(get_service),
):
    """Compile selected concept into an experiment and dispatch execution asynchronously in the background.
    
    Returns HTTP 202 Accepted with the newly generated run_id in 'queued' status.
    """
    try:
        run_id = service.launch_experiment(concept_id)
        return LaunchResponse(
            run_id=run_id,
            status="queued",
            message="Experimento encolado exitosamente para ejecución en background.",
        )
    except ValueError as e:
        msg = str(e)
        if "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Error inesperado al lanzar concepto '{concept_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al lanzar experimento: {str(e)}",
        )


@router.get("/runs/{run_id}/status", response_model=RunStatusResponse)
def get_run_status(
    run_id: str,
    dispatcher: RunDispatcher = Depends(get_dispatcher),
    service: CreativeService = Depends(get_service),
):
    """Hybrid polling endpoint: returns real-time progress update from memory cache,
    falling back to SQLite for historical runs or post-reboot recovery.
    """
    # 1. Check real-time progress cache in dispatcher
    cached_update = dispatcher.get_progress(run_id)
    
    if cached_update:
        renders: List[RenderDTO] = []
        # If execution is finished, enrich with persistent renders from SQLite via service
        if cached_update.status == "completed":
            run = service.get_run(run_id)
            if run and run.renders:
                renders = [_to_render_dto(r, run_id) for r in run.renders]

        return RunStatusResponse(
            run_id=cached_update.run_id,
            status=cached_update.status,
            progress_percent=cached_update.progress_percent,
            stage=cached_update.stage,
            message=cached_update.message,
            current_variant=cached_update.current_variant,
            completed_variants=cached_update.completed_variants,
            total_variants=cached_update.total_variants,
            error_message=cached_update.message if cached_update.status == "failed" else None,
            renders=renders,
        )

    # 2. Fallback to durable SQLite records via service
    db_run = service.get_run(run_id)
    if not db_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run con ID '{run_id}' no encontrado en el sistema.",
        )

    renders = [_to_render_dto(r, run_id) for r in db_run.renders]
    is_terminal = db_run.status in ("completed", "failed")
    progress_percent = 100 if is_terminal else (50 if db_run.status == "running" else 0)

    return RunStatusResponse(
        run_id=db_run.id,
        status=db_run.status,
        progress_percent=progress_percent,
        stage=db_run.status,
        message=db_run.error_message or f"Estado persistido: {db_run.status}",
        current_variant=None,
        completed_variants=len(renders),
        total_variants=max(3, len(renders)),
        error_message=db_run.error_message,
        renders=renders,
    )


@router.get("/media/{run_id}/{variant}")
def stream_media_variant(
    run_id: str,
    variant: str,
    service: CreativeService = Depends(get_service),
):
    """Secure video streaming endpoint with provenance validation and anti-path traversal protection.
    
    - Resolves render via service layer.
    - Strictly confines file path within storage/output/.
    - Returns FileResponse with media_type='video/mp4'.
    """
    # 1. Resolve provenance via service
    descriptor = service.get_media_descriptor(run_id=run_id, variant=variant)
    if not descriptor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Render para run '{run_id}' y variante '{variant}' no encontrado.",
        )

    # 2. Strict anti-path traversal validation
    allowed_root = settings.output_dir.resolve()
    resolved_path = descriptor.resolved_path

    if not resolved_path.is_relative_to(allowed_root):
        logger.warning(
            f"Posible violación de seguridad anti-path traversal para run '{run_id}', "
            f"variante '{variant}': '{resolved_path}' fuera de '{allowed_root}'"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: el recurso solicitado reside fuera del directorio autorizado.",
        )

    # 3. Physical file existence check
    if not resolved_path.is_file():
        logger.error(f"Archivo registrado pero no hallado en disco: {resolved_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El archivo de video registrado no existe en el almacenamiento local.",
        )

    return FileResponse(
        path=resolved_path,
        media_type=descriptor.content_type,
        filename=resolved_path.name,
    )

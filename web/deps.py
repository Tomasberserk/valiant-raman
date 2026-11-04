"""Dependency injection helpers for FastAPI routes."""

from fastapi import Request
from engine.creative.run_dispatcher import RunDispatcher
from engine.creative.service import CreativeService
from engine.experiments.repository import ExperimentRepository


def get_service(request: Request) -> CreativeService:
    """Extract CreativeService instance attached to application state."""
    return request.app.state.service


def get_dispatcher(request: Request) -> RunDispatcher:
    """Extract RunDispatcher instance attached to application state."""
    return request.app.state.dispatcher


def get_repo(request: Request) -> ExperimentRepository:
    """Extract ExperimentRepository instance attached to application state."""
    return request.app.state.repo

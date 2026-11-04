"""FastAPI application factory and lifecycle management."""

from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.creative.run_dispatcher import LocalRunDispatcher, RunDispatcher
from engine.creative.service import CreativeService
from engine.experiments.repository import ExperimentRepository
from web.routes.creative import router as creative_router
from web.routes.execution import router as execution_router


def create_app(
    repository: Optional[ExperimentRepository] = None,
    dispatcher: Optional[RunDispatcher] = None,
    service: Optional[CreativeService] = None,
) -> FastAPI:
    """Create and configure a FastAPI application instance."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 1. Initialize repository and run idempotent migrations
        repo = repository or getattr(app.state, "repo", None) or ExperimentRepository()
        repo.init_db()
        app.state.repo = repo

        # 2. Initialize background dispatcher with strictly single worker FIFO
        disp = dispatcher or getattr(app.state, "dispatcher", None) or LocalRunDispatcher(repository=repo, max_workers=1)
        app.state.dispatcher = disp

        # 3. Initialize creative domain service
        svc = service or getattr(app.state, "service", None) or CreativeService(repository=repo, dispatcher=disp)
        app.state.service = svc

        yield

        # 4. Clean shutdown: finish or terminate background tasks
        disp.shutdown(wait=True)

    app = FastAPI(
        title="Valiant Raman - Creative Workspace Studio",
        description="Deterministic short-form content ideation and experimentation engine.",
        version="0.2.0-fase2",
        lifespan=lifespan,
    )

    # Allow local development and studio frontend requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers under /api
    app.include_router(creative_router, prefix="/api")
    app.include_router(execution_router, prefix="/api")
    # Static files and HTML templates
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from fastapi import Request
    from fastapi.responses import HTMLResponse

    web_dir = Path(__file__).resolve().parent
    static_dir = web_dir / "static"
    templates_dir = web_dir / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse, tags=["studio"])
    @app.get("/studio", response_class=HTMLResponse, tags=["studio"])
    def studio_ui(request: Request):
        return templates.TemplateResponse(request=request, name="index.html")

    @app.get("/health", tags=["system"])
    def health_check():
        return {"status": "ok", "app": "valiant-raman studio", "engine": "running"}

    return app

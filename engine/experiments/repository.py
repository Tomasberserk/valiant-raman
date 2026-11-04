"""Repository layer for SQLite database access and provenance tracking."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker, selectinload

from config.settings import settings
from engine.experiments.models import (
    Asset,
    Base,
    Experiment,
    ExperimentRun,
    Hypothesis,
    Metric,
    Publication,
    Render,
    RenderAsset,
    Variant,
)


class ExperimentRepository:
    """Encapsulates all database operations, ensuring transactional safety and provenance."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or settings.database_url
        self.engine = create_engine(self.db_url, echo=False)
        self.SessionFactory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self) -> None:
        """Create all tables and run idempotent migrations in SQLite."""
        from engine.creative.migrations import migrate_db
        migrate_db(self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session: Session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_experiment(self, name: str, description: str, status: str = "active") -> Experiment:
        """Create and persist a new experiment."""
        with self.get_session() as session:
            experiment = Experiment(name=name, description=description, status=status)
            session.add(experiment)
            session.flush()
            session.refresh(experiment)
            return experiment

    def create_hypothesis(
        self,
        experiment_id: str,
        statement: str,
        independent_variable: str,
        primary_metric: str,
        success_criterion: str,
        baseline_description: str,
    ) -> Hypothesis:
        """Create and persist a testable hypothesis under an experiment."""
        with self.get_session() as session:
            hypothesis = Hypothesis(
                experiment_id=experiment_id,
                statement=statement,
                independent_variable=independent_variable,
                primary_metric=primary_metric,
                success_criterion=success_criterion,
                baseline_description=baseline_description,
            )
            session.add(hypothesis)
            session.flush()
            session.refresh(hypothesis)
            return hypothesis

    def create_variant(
        self,
        hypothesis_id: str,
        name: str,
        variant_code: str,
        hook_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Variant:
        """Create a variant (e.g., A, B, C) linked to a hypothesis."""
        params_json = json.dumps(parameters or {})
        with self.get_session() as session:
            variant = Variant(
                hypothesis_id=hypothesis_id,
                name=name,
                variant_code=variant_code,
                hook_type=hook_type,
                parameters_json=params_json,
            )
            session.add(variant)
            session.flush()
            session.refresh(variant)
            return variant

    def create_run(
        self,
        experiment_id: str,
        pipeline_version: str,
        config_hash: str,
        status: str = "running",
    ) -> ExperimentRun:
        """Record the initiation of a new experiment execution run."""
        with self.get_session() as session:
            run = ExperimentRun(
                experiment_id=experiment_id,
                pipeline_version=pipeline_version,
                config_hash=config_hash,
                status=status,
            )
            session.add(run)
            session.flush()
            session.refresh(run)
            return run

    def complete_run(
        self,
        run_id: str,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> Optional[ExperimentRun]:
        """Mark an experiment run as finished."""
        with self.get_session() as session:
            run = session.get(ExperimentRun, run_id)
            if run:
                run.status = status
                run.completed_at = datetime.now(timezone.utc)
                run.error_message = error_message
                session.flush()
                session.refresh(run)
            return run

    def update_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        pipeline_version: Optional[str] = None,
        config_hash: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[ExperimentRun]:
        """Update attributes of an existing experiment run."""
        with self.get_session() as session:
            run = session.get(ExperimentRun, run_id)
            if run:
                if status is not None:
                    run.status = status
                if pipeline_version is not None:
                    run.pipeline_version = pipeline_version
                if config_hash is not None:
                    run.config_hash = config_hash
                if error_message is not None:
                    run.error_message = error_message
                session.flush()
                session.refresh(run)
            return run


    def register_asset(
        self,
        asset_type: str,
        source: str,
        license_name: str,
        creator: str,
        allowed_platforms: str = "all",
        attribution_required: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Asset:
        """Register a media asset ensuring provenance metadata is strictly present."""
        if not source or not source.strip():
            raise ValueError("Asset source is required for provenance.")
        if not license_name or not license_name.strip():
            raise ValueError("Asset license is required for compliance.")
        if not creator or not creator.strip():
            raise ValueError("Asset creator is required for provenance.")

        with self.get_session() as session:
            asset = Asset(
                type=asset_type,
                source=source.strip(),
                license=license_name.strip(),
                creator=creator.strip(),
                allowed_platforms=allowed_platforms,
                attribution_required=attribution_required,
                metadata_json=json.dumps(metadata or {}),
            )
            session.add(asset)
            session.flush()
            session.refresh(asset)
            return asset

    def register_render(
        self,
        experiment_run_id: str,
        variant_id: str,
        file_path: str,
        duration_seconds: float,
        width: int,
        height: int,
        fps: float,
        codec: str,
        file_size_bytes: int,
        render_time_seconds: float,
        qa_passed: bool,
        qa_report: Optional[Dict[str, Any]] = None,
    ) -> Render:
        """Persist rendering outputs, dimensions, and QA results."""
        with self.get_session() as session:
            render = Render(
                experiment_run_id=experiment_run_id,
                variant_id=variant_id,
                file_path=file_path,
                duration_seconds=duration_seconds,
                width=width,
                height=height,
                fps=fps,
                codec=codec,
                file_size_bytes=file_size_bytes,
                render_time_seconds=render_time_seconds,
                qa_passed=qa_passed,
                qa_report_json=json.dumps(qa_report) if qa_report else None,
            )
            session.add(render)
            session.flush()
            session.refresh(render)
            return render

    def link_asset_to_render(self, render_id: str, asset_id: str, role: str) -> None:
        """Create explicit provenance association between a render and an asset."""
        with self.get_session() as session:
            link = RenderAsset(render_id=render_id, asset_id=asset_id, role=role)
            session.merge(link)

    def register_publication(
        self,
        render_id: str,
        platform: str,
        post_url: Optional[str] = None,
        published_at: Optional[datetime] = None,
    ) -> Publication:
        """Record publication event of a render on a platform."""
        with self.get_session() as session:
            pub = Publication(
                render_id=render_id,
                platform=platform,
                post_url=post_url,
                published_at=published_at or datetime.now(timezone.utc),
            )
            session.add(pub)
            session.flush()
            session.refresh(pub)
            return pub

    def record_metric(
        self,
        publication_id: str,
        views: Optional[int] = None,
        avg_watch_time_seconds: Optional[float] = None,
        completion_rate: Optional[float] = None,
        likes: Optional[int] = None,
        shares: Optional[int] = None,
        comments: Optional[int] = None,
        retention_at_3s: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Metric:
        """Record performance measurements for a published video."""
        with self.get_session() as session:
            metric = Metric(
                publication_id=publication_id,
                views=views,
                avg_watch_time_seconds=avg_watch_time_seconds,
                completion_rate=completion_rate,
                likes=likes,
                shares=shares,
                comments=comments,
                retention_at_3s=retention_at_3s,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            session.add(metric)
            session.flush()
            session.refresh(metric)
            return metric

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Fetch experiment with its hypotheses and variants."""
        with self.get_session() as session:
            stmt = (
                select(Experiment)
                .where(Experiment.id == experiment_id)
                .options(
                    selectinload(Experiment.hypotheses).selectinload(Hypothesis.variants),
                    selectinload(Experiment.runs).selectinload(ExperimentRun.renders),
                )
            )
            return session.execute(stmt).scalars().first()

    def get_run(self, run_id: str) -> Optional[ExperimentRun]:
        """Fetch run with associated renders."""
        with self.get_session() as session:
            stmt = (
                select(ExperimentRun)
                .where(ExperimentRun.id == run_id)
                .options(selectinload(ExperimentRun.renders))
            )
            return session.execute(stmt).scalars().first()

    def list_experiments(self) -> List[Experiment]:
        """List all experiments in descending order of creation."""
        with self.get_session() as session:
            stmt = (
                select(Experiment)
                .options(
                    selectinload(Experiment.hypotheses).selectinload(Hypothesis.variants),
                    selectinload(Experiment.runs).selectinload(ExperimentRun.renders),
                )
                .order_by(Experiment.created_at.desc())
            )
            return list(session.execute(stmt).scalars().all())

"""Run Dispatcher: Decoupled background execution coordinator for experiments."""

from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
import hashlib
import json
import logging
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Optional

from config.settings import settings
from engine.experiments.models import ExperimentRun
from engine.experiments.repository import ExperimentRepository
from engine.pipeline import ContentEnginePipeline, ProgressUpdate
from engine.scripting.schema import HookType, VariantPlan

logger = logging.getLogger(__name__)


class RunDispatcher(ABC):
    """Abstract interface for background run dispatching."""

    @abstractmethod
    def dispatch(
        self,
        experiment_id: str,
        hypothesis_id: Optional[str] = None,
        variant_plans: Optional[List[VariantPlan]] = None,
        output_dir: Optional[Path] = None,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None,
    ) -> str:
        """Enqueue an experiment run and return its unique run_id immediately."""
        pass

    @abstractmethod
    def get_progress(self, run_id: str) -> Optional[ProgressUpdate]:
        """Fetch the latest known progress event for a given run."""
        pass

    @abstractmethod
    def shutdown(self, wait: bool = True) -> None:
        """Cleanly terminate the worker executor."""
        pass


class LocalRunDispatcher(RunDispatcher):
    """Local, single-worker FIFO background dispatcher.

    Guarantees:
    - Exactly 1 ExperimentRun created per logical job with status='queued'.
    - Single worker (max_workers=1) ensuring serialized execution without concurrency races.
    - Pipeline adopts the existing run_id and transitions it: queued -> running -> completed/failed.
    - Complete database session isolation for background execution threads.
    - Thread-safe memory storage of the latest ProgressUpdate for instant status polling.
    """

    def __init__(
        self,
        repository: ExperimentRepository,
        pipeline: Optional[ContentEnginePipeline] = None,
        max_workers: int = 1,
    ):
        self.repo = repository
        self.pipeline = pipeline or ContentEnginePipeline(repository=self.repo)
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="local_dispatcher")
        self._lock = threading.Lock()
        self._latest_progress: Dict[str, ProgressUpdate] = {}
        self._active_futures: Dict[str, Future] = {}
        self._is_shutdown = False

    def dispatch(
        self,
        experiment_id: str,
        hypothesis_id: Optional[str] = None,
        variant_plans: Optional[List[VariantPlan]] = None,
        output_dir: Optional[Path] = None,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None,
    ) -> str:
        """Enqueue an experiment run, returning its run_id immediately."""
        if self._is_shutdown:
            raise RuntimeError("Cannot dispatch new runs; LocalRunDispatcher is already shut down.")

        # 1. Validate experiment existence
        exp = self.repo.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"Experiment with id '{experiment_id}' does not exist.")

        # Resolve hypothesis and variant plans if omitted
        resolved_hypo_id = hypothesis_id
        if not resolved_hypo_id:
            if not exp.hypotheses:
                raise ValueError(f"Experiment '{experiment_id}' has no associated hypotheses.")
            resolved_hypo_id = exp.hypotheses[0].id

        resolved_plans = variant_plans
        if not resolved_plans:
            hypo = next((h for h in exp.hypotheses if h.id == resolved_hypo_id), exp.hypotheses[0])
            if hypo.variants:
                resolved_plans = []
                for v in hypo.variants:
                    plan = VariantPlan(
                        variant_code=v.variant_code,
                        hook_type=HookType(v.hook_type),
                        target_duration_sec=30.0,
                        topic=exp.name,
                        angle="standard",
                        parameters=v.get_parameters(),
                    )
                    resolved_plans.append(plan)
            else:
                # Canonical 3 variants
                resolved_plans = [
                    VariantPlan(variant_code="A", hook_type=HookType.QUESTION, topic=exp.name),
                    VariantPlan(variant_code="B", hook_type=HookType.STATEMENT, topic=exp.name),
                    VariantPlan(variant_code="C", hook_type=HookType.SURPRISE, topic=exp.name),
                ]

        config_data = {
            "pipeline_version": settings.pipeline_version,
            "width": settings.default_width,
            "height": settings.default_height,
            "fps": settings.default_fps,
            "variants": [p.model_dump() for p in resolved_plans],
        }
        config_hash = hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()

        # 2. Create single ExperimentRun with status='queued'
        run = self.repo.create_run(
            experiment_id=experiment_id,
            pipeline_version=settings.pipeline_version,
            config_hash=config_hash,
            status="queued",
        )
        run_id = run.id

        # Initial queued progress state
        initial_progress = ProgressUpdate(
            run_id=run_id,
            status="queued",
            progress_percent=0,
            stage="queued",
            message="Encolado para ejecución en background...",
            current_variant=None,
            completed_variants=0,
            total_variants=len(resolved_plans),
        )
        with self._lock:
            self._latest_progress[run_id] = initial_progress

        if on_progress:
            try:
                on_progress(initial_progress)
            except Exception as cb_err:
                logger.warning(f"Error in initial on_progress callback: {cb_err}")

        # 3. Submit background job to executor
        future = self._executor.submit(
            self._worker_execute,
            experiment_id=experiment_id,
            hypothesis_id=resolved_hypo_id,
            variant_plans=resolved_plans,
            output_dir=output_dir,
            run_id=run_id,
            caller_on_progress=on_progress,
        )

        with self._lock:
            self._active_futures[run_id] = future

        return run_id

    def _worker_execute(
        self,
        experiment_id: str,
        hypothesis_id: str,
        variant_plans: List[VariantPlan],
        output_dir: Optional[Path],
        run_id: str,
        caller_on_progress: Optional[Callable[[ProgressUpdate], None]],
    ) -> None:
        """Worker function executed in the background thread."""
        def chained_progress(update: ProgressUpdate):
            with self._lock:
                self._latest_progress[run_id] = update
            if caller_on_progress:
                try:
                    caller_on_progress(update)
                except Exception as cb_err:
                    logger.warning(f"Error in chained on_progress callback: {cb_err}")

        try:
            self.pipeline.run_experiment_variants(
                experiment_id=experiment_id,
                hypothesis_id=hypothesis_id,
                variant_plans=variant_plans,
                output_dir=output_dir,
                existing_run_id=run_id,
                on_progress=chained_progress,
            )
        except Exception as e:
            logger.error(f"Background execution failed for run '{run_id}': {e}", exc_info=True)
            # Ensure DB reflects failed status
            try:
                self.repo.complete_run(run_id, status="failed", error_message=str(e))
            except Exception as db_err:
                logger.critical(f"Failed to record failure for run '{run_id}': {db_err}")

            failed_update = ProgressUpdate(
                run_id=run_id,
                status="failed",
                progress_percent=100,
                stage="failed",
                message=f"Fallo en ejecución: {str(e)}",
                completed_variants=0,
                total_variants=len(variant_plans),
            )
            with self._lock:
                self._latest_progress[run_id] = failed_update
            if caller_on_progress:
                try:
                    caller_on_progress(failed_update)
                except Exception:
                    pass

    def get_progress(self, run_id: str) -> Optional[ProgressUpdate]:
        """Fetch the latest cached progress event for a given run."""
        with self._lock:
            return self._latest_progress.get(run_id)

    def shutdown(self, wait: bool = True) -> None:
        """Cleanly terminate the worker executor, waiting for running jobs if wait=True."""
        self._is_shutdown = True
        self._executor.shutdown(wait=wait)

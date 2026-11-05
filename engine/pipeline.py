"""Pipeline orchestrator for the Short-Form Content Engine."""

import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel

from config.settings import settings
from engine.experiments.models import ExperimentRun, Render
from engine.experiments.repository import ExperimentRepository
from engine.media.base import Compositor, TranscriptionProvider, VoiceProvider
from engine.media.compositor import FFmpegCompositor
from engine.media.subtitles import generate_ass_subtitles
from engine.media.transcription import DummyTranscriptionProvider
from engine.media.voice import DummyVoiceProvider
from engine.audio.audio_director import AudioDirector
from engine.qa.validator import MediaValidator
from engine.scripting.schema import HookType, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider, ScriptProvider, ScriptwriterService
from engine.story.storyboard_planner import StoryboardPlanner
from engine.story.timeline_assembler import TimelineAssembler
from engine.visual.orchestrator import VisualOrchestrator

logger = logging.getLogger(__name__)


class ProgressUpdate(BaseModel):
    """Real progress update event emitted at milestones of pipeline execution."""

    run_id: str
    status: str = "running"
    progress_percent: int = 0
    stage: str = "starting"
    message: str = ""
    current_variant: Optional[str] = None
    completed_variants: int = 0
    total_variants: int = 3

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class PipelineExecutionResult:
    """Encapsulates the output of a full experiment pipeline run."""

    def __init__(self, run: ExperimentRun, renders: List[Render]):
        self.run = run
        self.renders = renders



class ContentEnginePipeline:
    """Coordinates research, scripting, media generation, composition, and provenance recording."""

    def __init__(
        self,
        repository: ExperimentRepository,
        script_provider: Optional[ScriptProvider] = None,
        voice_provider: Optional[VoiceProvider] = None,
        transcription_provider: Optional[TranscriptionProvider] = None,
        compositor: Optional[Compositor] = None,
        validator: Optional[MediaValidator] = None,
    ):
        self.repo = repository

        if script_provider is None:
            try:
                from engine.scripting.scriptwriter import get_default_script_provider
                self.script_provider = get_default_script_provider()
            except ImportError:
                self.script_provider = DummyScriptProvider()
        else:
            self.script_provider = script_provider

        self.scriptwriter = ScriptwriterService(self.script_provider)

        if voice_provider is None:
            try:
                from engine.media.voice import get_default_voice_provider
                self.voice_provider = get_default_voice_provider()
            except ImportError:
                self.voice_provider = DummyVoiceProvider()
        else:
            self.voice_provider = voice_provider

        self.transcription_provider = transcription_provider or DummyTranscriptionProvider()
        self.compositor = compositor or FFmpegCompositor(prefer_nvenc=settings.prefer_nvenc)
        self.validator = validator or MediaValidator(
            expected_width=settings.default_width,
            expected_height=settings.default_height,
        )

    def run_experiment_variants(
        self,
        experiment_id: str,
        hypothesis_id: str,
        variant_plans: List[VariantPlan],
        output_dir: Optional[Path] = None,
        existing_run_id: Optional[str] = None,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None,
    ) -> PipelineExecutionResult:
        """Execute end-to-end variant generation, rendering, QA, and registration."""
        out_base = output_dir or settings.output_dir
        out_base.mkdir(parents=True, exist_ok=True)

        config_data = {
            "pipeline_version": settings.pipeline_version,
            "width": settings.default_width,
            "height": settings.default_height,
            "fps": settings.default_fps,
            "variants": [p.model_dump() for p in variant_plans],
        }
        config_hash = hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()

        # 1. Resolve or adopt ExperimentRun (Strict prohibition of duplicate runs)
        if existing_run_id is not None:
            run = self.repo.get_run(existing_run_id)
            if not run:
                raise ValueError(f"ExperimentRun with id '{existing_run_id}' not found.")
            if run.experiment_id != experiment_id:
                raise ValueError(
                    f"ExperimentRun '{existing_run_id}' belongs to experiment '{run.experiment_id}', "
                    f"not to requested experiment '{experiment_id}'."
                )
            # Adopt existing run and transition to running
            updated_run = self.repo.update_run(
                run_id=existing_run_id,
                status="running",
                pipeline_version=settings.pipeline_version,
                config_hash=config_hash,
            )
            if updated_run:
                run = updated_run
        else:
            # Legacy Phase 1 path: Pipeline creates ExperimentRun
            run = self.repo.create_run(
                experiment_id=experiment_id,
                pipeline_version=settings.pipeline_version,
                config_hash=config_hash,
                status="running",
            )

        total_variants = len(variant_plans)

        def emit_progress(
            stage: str,
            progress_percent: int,
            message: str,
            current_variant: Optional[str] = None,
            completed_variants: int = 0,
            status: str = "running",
        ) -> None:
            if on_progress is None:
                return
            try:
                event = ProgressUpdate(
                    run_id=run.id,
                    status=status,
                    progress_percent=progress_percent,
                    stage=stage,
                    message=message,
                    current_variant=current_variant,
                    completed_variants=completed_variants,
                    total_variants=total_variants,
                )
                on_progress(event)
            except Exception as cb_err:
                logger.warning(f"Error in on_progress callback: {cb_err}")

        # Emit initial starting event (0%)
        emit_progress(
            stage="starting",
            progress_percent=0,
            message="Iniciando pipeline de experimentación...",
            current_variant=None,
            completed_variants=0,
        )

        completed_renders: List[Render] = []

        try:
            # 2. Register common baseline assets for provenance
            bg_asset = self.repo.register_asset(
                asset_type="video",
                source="procedural:lavfi:dark_grid",
                license_name="CC0-1.0 / Internal Procedural",
                creator="Valiant Raman Pipeline",
                allowed_platforms="all",
                attribution_required=False,
                metadata={"dimensions": f"{settings.default_width}x{settings.default_height}"},
            )

            font_asset = self.repo.register_asset(
                asset_type="font",
                source="system:Arial",
                license_name="Standard System Font License",
                creator="Monotype / Microsoft",
                allowed_platforms="all",
                attribution_required=False,
            )

            # 3. Process each variant plan
            for i, plan in enumerate(variant_plans):
                # Variant started milestone
                emit_progress(
                    stage="variant_started",
                    progress_percent=int((i / total_variants) * 100),
                    message=f"Iniciando guión y voz para Variante {plan.variant_code} ({i+1}/{total_variants})...",
                    current_variant=plan.variant_code,
                    completed_variants=i,
                )

                # Find or create variant entity in SQLite
                var_entity = self.repo.create_variant(
                    hypothesis_id=hypothesis_id,
                    name=f"Variant {plan.variant_code} - {plan.hook_type.value}",
                    variant_code=plan.variant_code,
                    hook_type=plan.hook_type.value,
                    parameters=plan.parameters,
                )

                # Check if this variant is narrative fiction or factual curiosity
                is_narrative = (plan.parameters or {}).get("content_mode") == "narrative_fiction"

                if is_narrative:
                    # =========================================================================
                    # CINEMATIC MULTI-SHOT STORYBOARD PIPELINE (Phases 1-3)
                    # =========================================================================
                    variant_work_dir = out_base / f"run_{run.id[:8]}" / f"variant_{plan.variant_code}"
                    variant_work_dir.mkdir(parents=True, exist_ok=True)

                    # 1. Storyboard Planning
                    planner = StoryboardPlanner()
                    narrative_prompt = (
                        (plan.parameters or {}).get("narrative_premise")
                        or (plan.parameters or {}).get("hook_text")
                        or plan.topic
                        or plan.angle
                        or "Narrative Action Sequence"
                    )
                    target_dur = float(plan.target_duration_sec or 25.0)
                    storyboard = planner.plan_storyboard(
                        raw_prompt=narrative_prompt,
                        target_duration_sec=target_dur,
                    )

                    # Save storyboard manifest
                    sb_json_path = variant_work_dir / "storyboard.json"
                    with open(sb_json_path, "w", encoding="utf-8") as f:
                        f.write(storyboard.model_dump_json(indent=2))

                    emit_progress(
                        stage="visual_orchestration",
                        progress_percent=int(((i + 0.3) / total_variants) * 100),
                        message=f"Generando tomas visuales y cámara para Variante {plan.variant_code}...",
                        current_variant=plan.variant_code,
                        completed_variants=i,
                    )

                    # 2. Visual Orchestration
                    visual_orchestrator = VisualOrchestrator()
                    shot_results = visual_orchestrator.orchestrate_storyboard(
                        storyboard=storyboard,
                        output_dir=variant_work_dir,
                        fps=settings.default_fps,
                        width=settings.default_width,
                        height=settings.default_height,
                    )
                    shot_dict = {r.shot_id: r for r in shot_results}

                    emit_progress(
                        stage="audio_direction",
                        progress_percent=int(((i + 0.6) / total_variants) * 100),
                        message=f"Mezclando diseño sonoro (SFX + BGM) para Variante {plan.variant_code}...",
                        current_variant=plan.variant_code,
                        completed_variants=i,
                    )

                    # 3. Audio Direction
                    audio_director = AudioDirector(voice_provider=self.voice_provider)
                    master_audio = variant_work_dir / "master_audio.wav"
                    audio_director.mix_storyboard_audio(storyboard, master_audio)

                    emit_progress(
                        stage="rendering",
                        progress_percent=int(((i + 0.8) / total_variants) * 100),
                        message=f"Ensamblando timeline cinemático para Variante {plan.variant_code}...",
                        current_variant=plan.variant_code,
                        completed_variants=i,
                    )

                    # 4. Master Timeline Assembly
                    final_video_file = variant_work_dir / f"final_variant_{plan.variant_code}.mp4"
                    render_start_time = time.time()
                    TimelineAssembler.assemble_storyboard_video(
                        storyboard=storyboard,
                        shot_results=shot_dict,
                        output_master_path=final_video_file,
                        voiceover_audio_path=master_audio,
                    )
                    render_elapsed = round(time.time() - render_start_time, 2)

                    # 5. QA Verification
                    actual_duration = storyboard.total_physical_duration
                    qa_report = self.validator.validate_render(
                        file_path=final_video_file,
                        expected_duration_sec=actual_duration,
                    )

                    file_size = final_video_file.stat().st_size if final_video_file.exists() else 0
                    render_entity = self.repo.register_render(
                        experiment_run_id=run.id,
                        variant_id=var_entity.id,
                        file_path=str(final_video_file),
                        duration_seconds=actual_duration,
                        width=settings.default_width,
                        height=settings.default_height,
                        fps=float(settings.default_fps),
                        codec=self.compositor.video_codec if hasattr(self.compositor, "video_codec") else "h264",
                        file_size_bytes=file_size,
                        render_time_seconds=render_elapsed,
                        qa_passed=qa_report.passed,
                        qa_report=qa_report.to_dict(),
                    )
                    self.repo.link_asset_to_render(render_entity.id, bg_asset.id, "cinematic_multishot_storyboard")
                else:
                    # =========================================================================
                    # FACTUAL CURIOSITY PROCEDURAL PIPELINE
                    # =========================================================================
                    # Script generation
                    script = self.script_provider.generate_script(
                        hypothesis_statement=f"Hypothesis {hypothesis_id}",
                        plan=plan,
                    )

                    variant_work_dir = out_base / f"run_{run.id[:8]}" / f"variant_{plan.variant_code}"
                    variant_work_dir.mkdir(parents=True, exist_ok=True)

                    # Audio generation
                    audio_file = variant_work_dir / "voiceover.wav"
                    vocal_text = script.full_text()
                    audio_result = self.voice_provider.generate_audio(
                        text=vocal_text,
                        voice_id="default_offline",
                        output_path=audio_file,
                    )

                    # Register audio asset with provenance
                    voice_asset = self.repo.register_asset(
                        asset_type="audio",
                        source=f"synthesizer:{audio_result.provider}:{audio_result.voice_id}",
                        license_name="Synthetic Audio Internal",
                        creator=audio_result.provider,
                        allowed_platforms="all",
                        attribution_required=False,
                        metadata={"duration": audio_result.duration_seconds},
                    )

                    # Word timestamps alignment
                    import inspect
                    sig = inspect.signature(self.transcription_provider.transcribe)
                    if "duration_seconds" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                        timestamps = self.transcription_provider.transcribe(
                            audio_path=audio_file,
                            reference_text=vocal_text,
                            duration_seconds=audio_result.duration_seconds,
                        )
                    else:
                        timestamps = self.transcription_provider.transcribe(
                            audio_path=audio_file,
                            reference_text=vocal_text,
                        )

                    # Subtitles (.ass) generation with kinetic active-word highlighting
                    subtitles_file = variant_work_dir / "subtitles.ass"
                    generate_ass_subtitles(
                        timestamps=timestamps,
                        output_path=subtitles_file,
                        font_name="Arial",
                        font_size=56,
                        style_preset="capcut_yellow",
                        enable_kinetic_highlight=True,
                    )

                    # Background video generation (Thematic B-roll or Procedural fallback)
                    bg_file = variant_work_dir / "background.mp4"
                    if hasattr(self.compositor, "generate_procedural_background"):
                        self.compositor.generate_procedural_background(
                            output_path=bg_file,
                            duration_seconds=audio_result.duration_seconds,
                            width=settings.default_width,
                            height=settings.default_height,
                            fps=settings.default_fps,
                            topic=plan.topic,
                        )

                    # Optional local BGM audio track discovery
                    bgm_file = None
                    bgm_dir = settings.assets_dir / "audio" / "bgm"
                    if bgm_dir.exists() and bgm_dir.is_dir():
                        candidate_bgm = sorted(list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav")))
                        if candidate_bgm:
                            bgm_file = candidate_bgm[0]

                    # Rendering milestone
                    emit_progress(
                        stage="rendering",
                        progress_percent=int(((i + 0.5) / total_variants) * 100),
                        message=f"Componiendo y renderizando video para Variante {plan.variant_code} ({i+1}/{total_variants})...",
                        current_variant=plan.variant_code,
                        completed_variants=i,
                    )

                    # Composition and final video render
                    final_video_file = variant_work_dir / f"final_variant_{plan.variant_code}.mp4"
                    render_start_time = time.time()

                    comp_sig = inspect.signature(self.compositor.compose_video)
                    compose_kwargs = {}
                    if "bgm_path" in comp_sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in comp_sig.parameters.values()):
                        compose_kwargs["bgm_path"] = bgm_file
                        compose_kwargs["bgm_volume"] = 0.12

                    self.compositor.compose_video(
                        background_path=bg_file,
                        audio_path=audio_file,
                        subtitles_path=subtitles_file,
                        output_path=final_video_file,
                        duration_seconds=audio_result.duration_seconds,
                        **compose_kwargs,
                    )
                    render_elapsed = round(time.time() - render_start_time, 2)

                    # QA Verification
                    qa_report = self.validator.validate_render(
                        file_path=final_video_file,
                        expected_duration_sec=audio_result.duration_seconds,
                        subtitles_path=subtitles_file,
                    )

                    # Persist render record
                    file_size = final_video_file.stat().st_size if final_video_file.exists() else 0
                    render_entity = self.repo.register_render(
                        experiment_run_id=run.id,
                        variant_id=var_entity.id,
                        file_path=str(final_video_file),
                        duration_seconds=audio_result.duration_seconds,
                        width=settings.default_width,
                        height=settings.default_height,
                        fps=float(settings.default_fps),
                        codec=self.compositor.video_codec if hasattr(self.compositor, "video_codec") else "h264",
                        file_size_bytes=file_size,
                        render_time_seconds=render_elapsed,
                        qa_passed=qa_report.passed,
                        qa_report=qa_report.to_dict(),
                    )

                    # Link provenance assets to this specific render
                    self.repo.link_asset_to_render(render_entity.id, bg_asset.id, "background_video")
                    self.repo.link_asset_to_render(render_entity.id, voice_asset.id, "voiceover")
                    self.repo.link_asset_to_render(render_entity.id, font_asset.id, "subtitle_font")
                    if bgm_file is not None:
                        bgm_asset = self.repo.register_asset(
                            asset_type="audio",
                            source=f"local:bgm:{bgm_file.name}",
                            license_name="Royalty Free / Local Asset",
                            creator="Valiant Raman Sound Library",
                            allowed_platforms="all",
                            attribution_required=False,
                        )
                        self.repo.link_asset_to_render(render_entity.id, bgm_asset.id, "background_music")

                completed_renders.append(render_entity)

                # Variant completed milestone
                emit_progress(
                    stage="variant_completed",
                    progress_percent=int(((i + 1) / total_variants) * 100),
                    message=f"Variante {plan.variant_code} completada y validada por QA ({i+1}/{total_variants}).",
                    current_variant=plan.variant_code,
                    completed_variants=i + 1,
                )

            # Mark run as completed
            updated_run = self.repo.complete_run(run.id, status="completed")
            if updated_run:
                run = updated_run

            # Final completed milestone (100%)
            emit_progress(
                stage="completed",
                progress_percent=100,
                message=f"Pipeline completado exitosamente con {total_variants} variantes generadas.",
                current_variant=None,
                completed_variants=total_variants,
                status="completed",
            )

        except Exception as e:
            self.repo.complete_run(run.id, status="failed", error_message=str(e))
            emit_progress(
                stage="failed",
                progress_percent=100,
                message=f"Fallo en la ejecución del pipeline: {str(e)}",
                current_variant=None,
                completed_variants=len(completed_renders),
                status="failed",
            )
            raise

        return PipelineExecutionResult(run=run, renders=completed_renders)


"""Pipeline orchestrator for the Short-Form Content Engine."""

import hashlib
import json
from pathlib import Path
import time
from typing import List, Optional

from config.settings import settings
from engine.experiments.models import ExperimentRun, Render
from engine.experiments.repository import ExperimentRepository
from engine.media.base import Compositor, TranscriptionProvider, VoiceProvider
from engine.media.compositor import FFmpegCompositor
from engine.media.subtitles import generate_ass_subtitles
from engine.media.transcription import DummyTranscriptionProvider
from engine.media.voice import DummyVoiceProvider
from engine.qa.validator import MediaValidator
from engine.scripting.schema import HookType, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider, ScriptProvider, ScriptwriterService


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
        self.script_provider = script_provider or DummyScriptProvider()
        self.scriptwriter = ScriptwriterService(self.script_provider)
        self.voice_provider = voice_provider or DummyVoiceProvider()
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

        # 1. Initiate Experiment Run in SQLite
        run = self.repo.create_run(
            experiment_id=experiment_id,
            pipeline_version=settings.pipeline_version,
            config_hash=config_hash,
            status="running",
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
            for plan in variant_plans:
                # Find or create variant entity in SQLite
                var_entity = self.repo.create_variant(
                    hypothesis_id=hypothesis_id,
                    name=f"Variant {plan.variant_code} - {plan.hook_type.value}",
                    variant_code=plan.variant_code,
                    hook_type=plan.hook_type.value,
                    parameters=plan.parameters,
                )

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
                timestamps = self.transcription_provider.transcribe(
                    audio_path=audio_file,
                    reference_text=vocal_text,
                )

                # Subtitles (.ass) generation
                subtitles_file = variant_work_dir / "subtitles.ass"
                generate_ass_subtitles(
                    timestamps=timestamps,
                    output_path=subtitles_file,
                    font_name="Arial",
                    font_size=56,
                )

                # Procedural background video generation
                bg_file = variant_work_dir / "background.mp4"
                if hasattr(self.compositor, "generate_procedural_background"):
                    self.compositor.generate_procedural_background(
                        output_path=bg_file,
                        duration_seconds=audio_result.duration_seconds,
                        width=settings.default_width,
                        height=settings.default_height,
                        fps=settings.default_fps,
                    )

                # Composition and final video render
                final_video_file = variant_work_dir / f"final_variant_{plan.variant_code}.mp4"
                render_start_time = time.time()

                self.compositor.compose_video(
                    background_path=bg_file,
                    audio_path=audio_file,
                    subtitles_path=subtitles_file,
                    output_path=final_video_file,
                    duration_seconds=audio_result.duration_seconds,
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

                completed_renders.append(render_entity)

            # Mark run as completed
            updated_run = self.repo.complete_run(run.id, status="completed")
            if updated_run:
                run = updated_run

        except Exception as e:
            self.repo.complete_run(run.id, status="failed", error_message=str(e))
            raise

        return PipelineExecutionResult(run=run, renders=completed_renders)

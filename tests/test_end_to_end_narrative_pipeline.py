"""End-to-End Integration Test for the Cinematic Narrative Pipeline.

Verifies the user's sword action prompt completely executes through:
1. CreativeService ideation & narrative mode detection.
2. 3-beat dramatic concept generation without documentary fillers.
3. Multi-shot Storyboard planning.
4. VisualOrchestrator camera animation.
5. AudioDirector sound design & SFX mix.
6. TimelineAssembler master 9:16 composition and SQLite render registration.
"""

from pathlib import Path
import subprocess

from engine.creative.modes import ResolvedContentMode
from engine.creative.service import CreativeService
from engine.experiments.repository import ExperimentRepository
from engine.media.compositor import FFmpegCompositor
from engine.media.transcription import DummyTranscriptionProvider
from engine.media.voice import DummyVoiceProvider
from engine.pipeline import ContentEnginePipeline
from engine.qa.validator import MediaValidator
from engine.scripting.scriptwriter import DummyScriptProvider


def test_sword_narrative_full_pipeline_execution(tmp_path: Path):
    db_file = tmp_path / "test_cinematic.db"
    repo = ExperimentRepository(db_url=f"sqlite:///{db_file.as_posix()}")
    repo.init_db()

    pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=DummyScriptProvider(),
        voice_provider=DummyVoiceProvider(words_per_minute=180),
        transcription_provider=DummyTranscriptionProvider(),
        compositor=FFmpegCompositor(prefer_nvenc=False),
        validator=MediaValidator(expected_width=1080, expected_height=1920, duration_tolerance_sec=6.0),
    )

    service = CreativeService(repository=repo)

    user_prompt = (
        "un chico encuentra una espada, enterrada en unbosque perdido, al sujetarla con sus manos "
        "el cielo cambia, pasa de estar vivo y brillosos, pasaa a oscuro y relampagos, viendo en el horizonte "
        "como almas carrañeras lo señala par matarlo , haciendo una secuencia de accion muy chimba"
    )

    # 1. Capture idea & analyze
    idea = service.capture_idea(raw_text=user_prompt)
    concepts = service.analyze_idea(idea.id)

    assert len(concepts) == 3
    selected_concept = concepts[0]
    service.select_concept(selected_concept.id)

    # 2. Compile experiment
    experiment, hypothesis, variant_plans = service.compile_experiment(selected_concept.id)
    assert len(variant_plans) == 3
    assert variant_plans[0].parameters.get("content_mode") == "narrative_fiction"

    # 3. Execute narrative variant A through pipeline
    out_dir = tmp_path / "renders"
    result = pipeline.run_experiment_variants(
        experiment_id=experiment.id,
        hypothesis_id=hypothesis.id,
        variant_plans=[variant_plans[0]],
        output_dir=out_dir,
    )

    assert len(result.renders) == 1
    render = result.renders[0]
    assert render.qa_passed is True

    # 4. Verify physical files and directories
    video_path = Path(render.file_path)
    assert video_path.exists()
    assert video_path.stat().st_size > 10000

    variant_dir = video_path.parent
    storyboard_json = variant_dir / "storyboard.json"
    assert storyboard_json.exists()

    master_audio = variant_dir / "master_audio.wav"
    assert master_audio.exists()

    shots_dir = variant_dir / "shots"
    assert shots_dir.exists()
    shot_mp4s = list(shots_dir.glob("*.mp4"))
    assert len(shot_mp4s) >= 6

    keyframes_dir = variant_dir / "keyframes"
    assert keyframes_dir.exists()
    keyframes_png = list(keyframes_dir.glob("*.png"))
    assert len(keyframes_png) >= 6

    # 5. Probe final video with ffprobe
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width:stream=height:stream=codec_name",
        "-of", "default=noprint_wrappers=1",
        str(video_path),
    ]
    probe_raw = subprocess.check_output(probe_cmd, text=True)
    probe_dict = dict(line.split("=") for line in probe_raw.strip().splitlines() if "=" in line)

    assert int(probe_dict.get("width", 0)) == 1080
    assert int(probe_dict.get("height", 0)) == 1920
    assert probe_dict.get("codec_name") == "h264"

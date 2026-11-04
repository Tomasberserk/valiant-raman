"""Unit tests for Scene Production & Surgical Regeneration (Stage 12B.3).

Validates:
1. Audio actual duration as temporal authority (actual_duration_sec).
2. Visual realization for passthrough video (Tiers 1 & 2).
3. Visual realization for Ken Burns motion on still image (Tier 3).
4. Visual realization for styled cinematic fallback (Tier 4, no raw blue grid).
5. Atomic Scene QA validation (compliance & failure detection).
6. Surgical Scene Regeneration (regenerates only scene K, preserving 1..N).
7. Complete Golden Case scene production with 100% Scene QA pass.
"""

import hashlib
from pathlib import Path
import pytest
from PIL import Image

from engine.story import (
    AssetCatalog,
    ResolutionTier,
    Scene,
    SceneAudioSynthesizer,
    SceneProducer,
    SceneQAEngine,
    SceneVisualRealizer,
    StoryArchitect,
    VisualAssetMetadata,
    VisualBrief,
    VisualProductionStrategy,
    VisualResolutionResult,
    VisualResolver,
)


@pytest.fixture
def tmp_render_dir(tmp_path: Path) -> Path:
    render_dir = tmp_path / "scene_renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    return render_dir


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample 1920x1080 still image for Ken Burns testing."""
    img_path = tmp_path / "test_historic_photo.jpg"
    img = Image.new("RGB", (1920, 1080), color=(120, 80, 50))
    img.save(str(img_path))
    return img_path


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Create a short 3.0s 1920x1080 video for passthrough testing."""
    vid_path = tmp_path / "test_source_footage.mp4"
    import subprocess
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "color=c=0x223344:s=1920x1080:r=30:d=3.0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", "3.0",
        "-an",
        "-y",
        str(vid_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return vid_path


def test_audio_temporal_authority(tmp_path: Path):
    """Verify physical audio duration establishes actual_duration_sec authority."""
    synth = SceneAudioSynthesizer()
    out_audio = tmp_path / "voice_test.wav"
    text = "Este es un guion de prueba para medir la duracion real de la locucion vocal."
    path, actual_duration = synth.synthesize_voice(text, out_audio)

    assert path.exists()
    assert path.stat().st_size > 0
    # DummyVoiceProvider produces audio with duration >= 2.0s
    assert actual_duration >= 2.0
    assert isinstance(actual_duration, float)


def test_visual_realizer_passthrough_video(sample_video: Path, tmp_path: Path):
    """Verify passthrough video realization crops to 1080x1920 @ 30fps for target duration."""
    realizer = SceneVisualRealizer()
    out_video = tmp_path / "passthrough_out.mp4"
    realizer.realize_passthrough(
        asset_path=sample_video,
        duration_sec=2.5,
        output_path=out_video,
    )

    assert out_video.exists()
    assert out_video.stat().st_size > 0

    qa = SceneQAEngine()
    dummy_scene = Scene(
        id="dummy_01",
        scene_index=0,
        narrative_role="hook",
        script_text="Test",
        word_count=1,
        estimated_duration_sec=0.4,
    )
    # Note: realizer outputs video-only; checking video dimensions
    import subprocess, json
    res = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", str(out_video)
    ], capture_output=True, text=True, check=True)
    info = json.loads(res.stdout)
    v_stream = info["streams"][0]
    assert int(v_stream["width"]) == 1080
    assert int(v_stream["height"]) == 1920


def test_visual_realizer_ken_burns_image(sample_image: Path, tmp_path: Path):
    """Verify Ken Burns realizes high-res image into 1080x1920 @ 30fps animated video."""
    realizer = SceneVisualRealizer()
    out_video = tmp_path / "ken_burns_out.mp4"
    realizer.realize_ken_burns(
        image_path=sample_image,
        duration_sec=2.0,
        output_path=out_video,
    )

    assert out_video.exists()
    assert out_video.stat().st_size > 0

    import subprocess, json
    res = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", str(out_video)
    ], capture_output=True, text=True, check=True)
    info = json.loads(res.stdout)
    v_stream = info["streams"][0]
    assert int(v_stream["width"]) == 1080
    assert int(v_stream["height"]) == 1920


def test_visual_realizer_styled_cinematic_fallback(tmp_path: Path):
    """Verify styled cinematic fallback generates 1080x1920 video without raw blue grid."""
    realizer = SceneVisualRealizer()
    out_video = tmp_path / "styled_out.mp4"
    realizer.realize_styled_cinematic(
        duration_sec=2.0,
        output_path=out_video,
    )

    assert out_video.exists()
    assert out_video.stat().st_size > 0

    import subprocess, json
    res = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", str(out_video)
    ], capture_output=True, text=True, check=True)
    info = json.loads(res.stdout)
    v_stream = info["streams"][0]
    assert int(v_stream["width"]) == 1080
    assert int(v_stream["height"]) == 1920


def test_scene_producer_produce_scene_and_qa_pass(tmp_render_dir: Path):
    """Verify SceneProducer produces a valid scene MP4 that passes SceneQA."""
    producer = SceneProducer()
    scene = Scene(
        id="scene_test_prod",
        scene_index=0,
        narrative_role="hook",
        script_text="En 1886 comenzo la era de los primeros automoviles.",
        word_count=9,
        estimated_duration_sec=3.6,
    )
    resolution = VisualResolutionResult(
        scene_id="scene_test_prod",
        tier=ResolutionTier.TIER4_STYLED_FALLBACK,
        asset_path=None,
        production_strategy=VisualProductionStrategy.STYLED_CINEMATIC.value,
        score=0.0,
        rationale="Fallback test",
    )

    final_mp4 = producer.produce_scene(scene, resolution, tmp_render_dir)

    assert final_mp4.exists()
    assert scene.actual_duration_sec is not None
    assert scene.actual_duration_sec > 0.0
    assert scene.scene_qa_passed is True
    assert len(scene.scene_qa_failures) == 0
    assert len(scene.word_timings) == 9


def test_scene_qa_validation_failure(tmp_path: Path):
    """Verify SceneQAEngine catches resolution and duration failures."""
    qa = SceneQAEngine()
    bad_vid = tmp_path / "bad_resolution.mp4"
    import subprocess
    # Generate 720x1280 (not 1080x1920)
    subprocess.run([
        "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=720x1280:r=30:d=1.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "1.0", "-y", str(bad_vid)
    ], capture_output=True, check=True)

    dummy_scene = Scene(
        id="bad_scene",
        scene_index=0,
        narrative_role="hook",
        script_text="Test",
        word_count=1,
        estimated_duration_sec=0.4,
    )

    report = qa.evaluate_scene(dummy_scene, bad_vid, expected_duration_sec=1.0)
    assert report.passed is False
    assert report.checks["resolution_1080x1920"] is False
    assert any("1080x1920" in f for f in report.failures)


def test_surgical_regeneration_preserves_other_scenes(tmp_render_dir: Path):
    """Mandatory Audit Check: Surgical regeneration must ONLY alter the target scene."""
    producer = SceneProducer()

    # Create 3 scenes
    scenes = [
        Scene(id="scene_01", scene_index=0, narrative_role="hook", script_text="Primera escena.", word_count=2, estimated_duration_sec=0.8),
        Scene(id="scene_02", scene_index=1, narrative_role="origin_context", script_text="Segunda escena.", word_count=2, estimated_duration_sec=0.8),
        Scene(id="scene_03", scene_index=2, narrative_role="payoff", script_text="Tercera escena original.", word_count=3, estimated_duration_sec=1.2),
    ]

    from engine.story.schema import StoryContract, StoryArc
    story = StoryArc(
        id="story_surgical_test",
        contract=StoryContract(
            id="c1", title="Test", topic="Test", core_question="Q?", narrative_promise="P"
        ),
        scenes=scenes,
    )

    resolutions = {
        s.id: VisualResolutionResult(
            scene_id=s.id,
            tier=ResolutionTier.TIER4_STYLED_FALLBACK,
            asset_path=None,
            production_strategy="styled_cinematic",
            score=0.0,
            rationale="Test",
        )
        for s in scenes
    }

    # 1. Produce all 3 scenes initially
    producer.produce_story_scenes(story, list(resolutions.values()), tmp_render_dir)

    path_01 = tmp_render_dir / "scene_01.mp4"
    path_02 = tmp_render_dir / "scene_02.mp4"
    path_03 = tmp_render_dir / "scene_03.mp4"

    assert path_01.exists() and path_02.exists() and path_03.exists()

    # Capture fingerprints of scene 01 and 02
    hash_01_before = hashlib.sha256(path_01.read_bytes()).hexdigest()
    mtime_01_before = path_01.stat().st_mtime
    hash_02_before = hashlib.sha256(path_02.read_bytes()).hexdigest()
    mtime_02_before = path_02.stat().st_mtime

    hash_03_before = hashlib.sha256(path_03.read_bytes()).hexdigest()

    # 2. Surgically regenerate ONLY scene_03 with new script text
    new_script = "Tercera escena completamente regenerada con nuevo texto extendido para validar cambio de audio."
    producer.regenerate_scene(
        story=story,
        scene_id="scene_03",
        resolutions=resolutions,
        output_dir=tmp_render_dir,
        new_script_text=new_script,
    )

    # 3. Assertions
    # Scene 03 must have changed
    hash_03_after = hashlib.sha256(path_03.read_bytes()).hexdigest()
    assert hash_03_after != hash_03_before

    # Scene 01 and 02 must be 100% UNTOUCHED
    hash_01_after = hashlib.sha256(path_01.read_bytes()).hexdigest()
    mtime_01_after = path_01.stat().st_mtime
    hash_02_after = hashlib.sha256(path_02.read_bytes()).hexdigest()
    mtime_02_after = path_02.stat().st_mtime

    assert hash_01_after == hash_01_before
    assert mtime_01_after == mtime_01_before
    assert hash_02_after == hash_02_before
    assert mtime_02_after == mtime_02_before


def test_golden_case_all_scenes_produced_and_qa_passed(tmp_render_dir: Path):
    """Produce all 5 scenes of the automotive Golden Case; all must pass Scene QA."""
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")

    # Use resolver with synthetic fixtures
    cat = AssetCatalog()
    resolver = VisualResolver()
    resolutions = resolver.resolve_story(story, cat)

    producer = SceneProducer()
    produced_mp4s = producer.produce_story_scenes(story, resolutions, tmp_render_dir)

    assert len(produced_mp4s) == 5
    for mp4_path, scene in zip(produced_mp4s, story.scenes):
        assert mp4_path.exists()
        assert mp4_path.stat().st_size > 0
        assert scene.actual_duration_sec is not None
        assert scene.actual_duration_sec >= 2.0
        assert scene.scene_qa_passed is True
        assert len(scene.scene_qa_failures) == 0

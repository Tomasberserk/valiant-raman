"""Unit tests for Master Timeline & Continuous Audio (Stage 12B.4).

Validates:
1. Physical timeline cumulative offset calculation.
2. Master duration authority from actual scene durations (not estimates).
3. Precision time-shifting and non-overlapping master subtitle merge.
4. Seamless voice stitching without artificial gaps.
5. BGM voice-priority mixing and graceful voice-only fallback.
6. Clean video track concatenation (1080x1920 @ 30fps).
7. Scene boundary integrity validation (monotonicity, aspect ratio, duration sync).
8. End-to-end master assembly of the canonical Golden Case (>=61.0s).
"""

from pathlib import Path
import subprocess
import pytest

from engine.story import (
    AssetCatalog,
    MasterTimeline,
    MasterTimelineAssembler,
    ResolutionTier,
    Scene,
    SceneProducer,
    StoryArc,
    StoryArchitect,
    StoryContract,
    VisualProductionStrategy,
    VisualResolutionResult,
    VisualResolver,
    WordTimestamp,
)


@pytest.fixture
def tmp_master_dir(tmp_path: Path) -> Path:
    out = tmp_path / "master_output"
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def sample_bgm(tmp_path: Path) -> Path:
    """Generate a short 5.0s sample audio track for BGM testing."""
    bgm_path = tmp_path / "test_bgm.wav"
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=5.0",
        "-c:a", "pcm_s16le",
        "-y",
        str(bgm_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return bgm_path


def test_timeline_offset_calculation():
    """Verify physical cumulative offsets: S0=0, S1=d0, S2=d0+d1."""
    scenes = [
        Scene(id="s1", scene_index=0, narrative_role="hook", script_text="Uno", word_count=1, estimated_duration_sec=0.4, actual_duration_sec=8.50),
        Scene(id="s2", scene_index=1, narrative_role="origin_context", script_text="Dos", word_count=1, estimated_duration_sec=0.4, actual_duration_sec=14.25),
        Scene(id="s3", scene_index=2, narrative_role="payoff", script_text="Tres", word_count=1, estimated_duration_sec=0.4, actual_duration_sec=16.00),
    ]
    story = StoryArc(
        id="story_timeline_test",
        contract=StoryContract(id="c1", title="Test", topic="Test", core_question="Q?", narrative_promise="P"),
        scenes=scenes,
    )

    assembler = MasterTimelineAssembler()
    timeline = assembler.calculate_timeline(story)

    assert timeline.scene_order == ["s1", "s2", "s3"]
    assert timeline.scene_offsets["s1"] == 0.0
    assert timeline.scene_offsets["s2"] == 8.50
    assert timeline.scene_offsets["s3"] == 22.75  # 8.50 + 14.25
    assert timeline.total_actual_duration_sec == 38.75  # 22.75 + 16.00


def test_master_duration_uses_actual_scene_duration():
    """Verify total duration is governed strictly by actual physical durations, not estimates."""
    scenes = [
        Scene(id="s1", scene_index=0, narrative_role="hook", script_text="Uno", word_count=1, estimated_duration_sec=99.0, actual_duration_sec=10.0),
        Scene(id="s2", scene_index=1, narrative_role="payoff", script_text="Dos", word_count=1, estimated_duration_sec=99.0, actual_duration_sec=12.0),
    ]
    story = StoryArc(
        id="story_dur_test",
        contract=StoryContract(id="c1", title="Test", topic="Test", core_question="Q?", narrative_promise="P"),
        scenes=scenes,
    )

    assembler = MasterTimelineAssembler()
    timeline = assembler.calculate_timeline(story)

    assert timeline.total_actual_duration_sec == 22.0
    assert timeline.total_actual_duration_sec != 198.0


def test_master_subtitle_time_shifting(tmp_master_dir: Path):
    """Verify master subtitle merge shifts timestamps by scene offsets without overlap."""
    scenes = [
        Scene(
            id="s1",
            scene_index=0,
            narrative_role="hook",
            script_text="Primera palabra",
            word_count=2,
            estimated_duration_sec=1.0,
            actual_duration_sec=5.0,
            word_timings=[
                WordTimestamp(word="Primera", start=0.5, end=1.5),
                WordTimestamp(word="palabra", start=1.6, end=2.5),
            ],
        ),
        Scene(
            id="s2",
            scene_index=1,
            narrative_role="payoff",
            script_text="Segunda palabra",
            word_count=2,
            estimated_duration_sec=1.0,
            actual_duration_sec=4.0,
            word_timings=[
                WordTimestamp(word="Segunda", start=0.2, end=1.0),
                WordTimestamp(word="palabra", start=1.1, end=2.0),
            ],
        ),
    ]
    story = StoryArc(
        id="story_sub_test",
        contract=StoryContract(id="c1", title="Test", topic="Test", core_question="Q?", narrative_promise="P"),
        scenes=scenes,
    )

    assembler = MasterTimelineAssembler()
    timeline = assembler.calculate_timeline(story)
    out_ass = tmp_master_dir / "master.ass"
    assembler.merge_master_subtitles(story, timeline, out_ass)

    assert out_ass.exists()
    content = out_ass.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    # Scene 2 offset is 5.0s, so start=0.2s becomes 5.2s -> 0:00:05.20 in ASS
    assert "0:00:05.20" in content


def test_continuous_voice_stitching(tmp_master_dir: Path):
    """Verify voice tracks are concatenated into a single audio file."""
    producer = SceneProducer()
    s1_audio = tmp_master_dir / "s1_voice.wav"
    s2_audio = tmp_master_dir / "s2_voice.wav"

    _, d1 = producer.audio_synthesizer.synthesize_voice("Primera oracion de prueba.", s1_audio)
    _, d2 = producer.audio_synthesizer.synthesize_voice("Segunda oracion de prueba.", s2_audio)

    scenes = [
        Scene(id="s1", scene_index=0, narrative_role="hook", script_text="Uno", word_count=1, estimated_duration_sec=1.0, actual_duration_sec=d1, voice_audio_path=s1_audio),
        Scene(id="s2", scene_index=1, narrative_role="payoff", script_text="Dos", word_count=1, estimated_duration_sec=1.0, actual_duration_sec=d2, voice_audio_path=s2_audio),
    ]
    story = StoryArc(
        id="story_voice_test",
        contract=StoryContract(id="c1", title="Test", topic="Test", core_question="Q?", narrative_promise="P"),
        scenes=scenes,
    )

    assembler = MasterTimelineAssembler()
    out_stitched = tmp_master_dir / "master_voice.wav"
    assembler.stitch_continuous_voice(story, out_stitched)

    assert out_stitched.exists()
    assert out_stitched.stat().st_size > 0


def test_bgm_optional_fallback(tmp_master_dir: Path, sample_bgm: Path):
    """Verify BGM mixing applies fixed attenuation when present, and falls back to voice-only when absent."""
    producer = SceneProducer()
    voice_audio = tmp_master_dir / "voice.wav"
    _, dur = producer.audio_synthesizer.synthesize_voice("Prueba de mezcla con musica de fondo.", voice_audio)

    assembler = MasterTimelineAssembler()

    # Case 1: BGM Present
    out_with_bgm = tmp_master_dir / "audio_with_bgm.m4a"
    _, bgm_applied = assembler.mix_master_audio(voice_audio, sample_bgm, dur, out_with_bgm, bgm_volume=0.12)
    assert out_with_bgm.exists()
    assert bgm_applied is True

    # Case 2: BGM Absent (None) -> Graceful Fallback to Voice Only
    out_voice_only = tmp_master_dir / "audio_voice_only.m4a"
    _, bgm_applied_none = assembler.mix_master_audio(voice_audio, None, dur, out_voice_only)
    assert out_voice_only.exists()
    assert bgm_applied_none is False

    # Case 3: BGM Corrupt Path -> Graceful Fallback to Voice Only
    out_corrupt = tmp_master_dir / "audio_corrupt_fallback.m4a"
    corrupt_bgm = tmp_master_dir / "nonexistent_bgm.wav"
    _, bgm_applied_corrupt = assembler.mix_master_audio(voice_audio, corrupt_bgm, dur, out_corrupt)
    assert out_corrupt.exists()
    assert bgm_applied_corrupt is False


def test_clean_video_concatenation(tmp_master_dir: Path):
    """Verify concatenation of visual tracks into a clean 1080x1920 @ 30fps stream."""
    producer = SceneProducer()
    v1 = tmp_master_dir / "v1.mp4"
    v2 = tmp_master_dir / "v2.mp4"

    producer.visual_realizer.realize_styled_cinematic(2.0, v1)
    producer.visual_realizer.realize_styled_cinematic(2.0, v2)

    assembler = MasterTimelineAssembler()
    master_v = tmp_master_dir / "master_v.mp4"
    assembler.assemble_master_video_track([v1, v2], master_v)

    assert master_v.exists()
    assert master_v.stat().st_size > 0


def test_scene_boundary_integrity(tmp_master_dir: Path):
    """Verify scene boundary validation checks monotonicity, resolution, and duration sync."""
    producer = SceneProducer()
    v1 = tmp_master_dir / "v1.mp4"
    v2 = tmp_master_dir / "v2.mp4"

    producer.visual_realizer.realize_styled_cinematic(2.0, v1)
    producer.visual_realizer.realize_styled_cinematic(2.0, v2)

    master_v = tmp_master_dir / "master_v.mp4"
    assembler = MasterTimelineAssembler()
    assembler.assemble_master_video_track([v1, v2], master_v)

    scenes = [
        Scene(id="s1", scene_index=0, narrative_role="hook", script_text="Uno", word_count=1, estimated_duration_sec=2.0, actual_duration_sec=2.0),
        Scene(id="s2", scene_index=1, narrative_role="payoff", script_text="Dos", word_count=1, estimated_duration_sec=2.0, actual_duration_sec=2.0),
    ]
    story = StoryArc(
        id="story_boundary_test",
        contract=StoryContract(id="c1", title="Test", topic="Test", core_question="Q?", narrative_promise="P"),
        scenes=scenes,
    )
    timeline = assembler.calculate_timeline(story)

    results = assembler.validate_scene_boundaries(story, timeline, master_v)
    assert results["passed"] is True
    assert results["boundary_offsets_monotonic"] is True
    assert results["resolution_1080x1920"] is True
    assert results["framerate_30fps"] is True
    assert results["duration_matched"] is True


def test_golden_case_master_assembly_e2e(tmp_master_dir: Path):
    """End-to-End Master Assembly: Produce Golden Case, assemble master, verify >=61s and 1080x1920."""
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")

    # 1. Produce scenes in temporary workspace
    cat = AssetCatalog()
    resolver = VisualResolver()
    resolutions = resolver.resolve_story(story, cat)

    producer = SceneProducer()
    scene_dir = tmp_master_dir / "scenes"
    producer.produce_story_scenes(story, resolutions, scene_dir)

    # 2. Assemble Master Timeline
    assembler = MasterTimelineAssembler()
    master_out_dir = tmp_master_dir / "master"
    timeline = assembler.assemble_master_story(
        story=story,
        scene_dir=scene_dir,
        output_dir=master_out_dir,
        bgm_path=None,  # Fallback voice-only mode for offline determinism
    )

    # 3. Assertions
    # Duration must satisfy the 3-tier policy: 61.0s <= total_actual_duration_sec <= 90.0s
    assert 61.0 <= timeline.total_actual_duration_sec <= 90.0

    master_mp4 = timeline.master_video_path
    assert master_mp4 is not None
    assert master_mp4.exists()
    assert master_mp4.stat().st_size > 0

    # Boundary integrity check
    integrity = assembler.validate_scene_boundaries(story, timeline, master_mp4)
    assert integrity["passed"] is True
    assert integrity["resolution_1080x1920"] is True
    assert integrity["framerate_30fps"] is True
    assert integrity["duration_matched"] is True

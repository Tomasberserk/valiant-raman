"""Unit tests for Final Media QA & Publication Certification (Stage 12B.5).

Validates:
1. Forensic stream inspection (1080x1920, 30fps, h264, aac).
2. Hard rejection of masters below 61.0s (monetization threshold).
3. Soft maximum warning for masters exceeding 90.0s.
4. Scene duration reconstruction & sum synchronization (|master - sum(scenes)| <= 0.35s).
5. EBU R128 loudness (-14 LUFS target, [-16, -12] window) and True Peak (<= -1.0 dBTP).
6. Spoken-content subtitle coverage (>= 99.0% target, unintended gap <= 1.0s).
7. Bitstream decode scan via null-sink.
8. Hard Gate: rejected masters are never exported and produce no manifest.
9. Cryptographic manifest.json provenance generation (SHA-256, scene breakdown, checks).
10. End-to-end Golden Case final certification & publication export (>= 61.0s).
"""

import json
from pathlib import Path
import subprocess
import pytest

from engine.story import (
    AssetCatalog,
    FinalMediaQAEngine,
    FinalMediaQAReport,
    MasterTimeline,
    MasterTimelineAssembler,
    PublicationStatus,
    Scene,
    SceneProducer,
    StoryArc,
    StoryArchitect,
    StoryContract,
    VisualResolver,
    WordTimestamp,
)


@pytest.fixture
def tmp_qa_dir(tmp_path: Path) -> Path:
    out = tmp_path / "qa_output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _generate_synthetic_mp4(
    path: Path,
    duration_sec: float,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    v_codec: str = "libx264",
    a_codec: str = "aac",
    tone_freq: int = 440,
) -> Path:
    """Generate a lightweight synthetic MP4 video file with audio for QA tests."""
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:r={fps}:d={duration_sec}",
        "-f", "lavfi",
        "-i", f"sine=frequency={tone_freq}:duration={duration_sec}",
        "-c:v", v_codec,
        "-pix_fmt", "yuv420p",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=7",
        "-c:a", a_codec,
        "-shortest",
        "-y",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return path



def _create_sample_ass(path: Path, events: list[tuple[float, float, str]]):
    """Write a minimal ASS subtitle file for testing."""
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,0,2,20,20,120,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    for start, end, text in events:
        s_h, s_m, s_s = int(start // 3600), int((start % 3600) // 60), start % 60
        e_h, e_m, e_s = int(end // 3600), int((end % 3600) // 60), end % 60
        s_str = f"{s_h}:{s_m:02d}:{s_s:05.2f}"
        e_str = f"{e_h}:{e_m:02d}:{e_s:05.2f}"
        lines.append(f"Dialogue: 0,{s_str},{e_str},Default,,0,0,0,,{text}\n")
    path.write_text("".join(lines), encoding="utf-8")


def test_media_qa_forensic_stream_inspection(tmp_qa_dir: Path):
    """Verify detection and acceptance of 1080x1920, 30fps, h264, and aac."""
    mp4_path = tmp_qa_dir / "valid_master.mp4"
    _generate_synthetic_mp4(mp4_path, duration_sec=65.0)

    ass_path = tmp_qa_dir / "valid_master.ass"
    _create_sample_ass(ass_path, [(0.5, 64.5, "Narración continua")])

    timeline = MasterTimeline(
        story_id="test_forensic",
        target_duration_sec=65.0,
        total_actual_duration_sec=65.0,
        master_video_path=mp4_path,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    report = qa.evaluate_master(timeline)

    assert report.checks["container_and_streams"] is True
    assert report.video_metrics["codec"] == "h264"
    assert report.video_metrics["width"] == 1080
    assert report.video_metrics["height"] == 1920
    assert 29.0 <= report.video_metrics["fps"] <= 31.0
    assert report.audio_metrics["codec"] == "aac"
    assert report.audio_metrics["sample_rate"] >= 44100


def test_media_qa_duration_rejection_under_61s(tmp_qa_dir: Path):
    """Hard gate rejection: Duration < 61.0s MUST produce REJECTED status."""
    mp4_path = tmp_qa_dir / "short_master.mp4"
    _generate_synthetic_mp4(mp4_path, duration_sec=45.0)

    ass_path = tmp_qa_dir / "short_master.ass"
    _create_sample_ass(ass_path, [(0.5, 44.5, "Texto corto")])

    timeline = MasterTimeline(
        story_id="test_short",
        target_duration_sec=45.0,
        total_actual_duration_sec=45.0,
        master_video_path=mp4_path,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    report = qa.evaluate_master(timeline)

    assert report.status == PublicationStatus.REJECTED
    assert report.passed is False
    assert report.checks["duration_policy"] is False
    assert any(f.rule == "duration_hard_minimum" and f.severity == "ERROR" for f in report.findings)


def test_media_qa_duration_soft_maximum_warning(tmp_qa_dir: Path):
    """Masters exceeding 90.0s soft max emit WARNING and CERTIFIED_WITH_WARNINGS."""
    mp4_path = tmp_qa_dir / "long_master.mp4"
    _generate_synthetic_mp4(mp4_path, duration_sec=95.0)

    ass_path = tmp_qa_dir / "long_master.ass"
    _create_sample_ass(ass_path, [(0.0, 95.0, "Texto extendido")])


    timeline = MasterTimeline(
        story_id="test_long",
        target_duration_sec=95.0,
        total_actual_duration_sec=95.0,
        master_video_path=mp4_path,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    report = qa.evaluate_master(timeline)

    assert report.status == PublicationStatus.CERTIFIED_WITH_WARNINGS
    assert report.passed is True
    assert any(f.rule == "duration_soft_maximum" and f.severity == "WARNING" for f in report.findings)


def test_media_qa_scene_sum_and_av_drift(tmp_qa_dir: Path):
    """Detect when master duration deviates from sum of actual scene durations > 0.35s."""
    mp4_path = tmp_qa_dir / "drift_master.mp4"
    _generate_synthetic_mp4(mp4_path, duration_sec=65.0)

    ass_path = tmp_qa_dir / "drift_master.ass"
    _create_sample_ass(ass_path, [(0.5, 64.5, "Texto sincronizado")])

    # Reconstructed scene durations sum to 70.0s, but master is 65.0s (drift 5.0s > 0.35s)
    scenes = [
        Scene(id="s1", scene_index=0, narrative_role="hook", script_text="Uno", word_count=1, estimated_duration_sec=1.0, actual_duration_sec=35.0),
        Scene(id="s2", scene_index=1, narrative_role="payoff", script_text="Dos", word_count=1, estimated_duration_sec=1.0, actual_duration_sec=35.0),
    ]
    story = StoryArc(
        id="story_drift",
        contract=StoryContract(id="c1", title="Drift", topic="Test", core_question="Q?", narrative_promise="P"),
        scenes=scenes,
    )

    timeline = MasterTimeline(
        story_id="story_drift",
        target_duration_sec=70.0,
        total_actual_duration_sec=70.0,
        scene_durations={"s1": 35.0, "s2": 35.0},
        scene_offsets={"s1": 0.0, "s2": 35.0},
        master_video_path=mp4_path,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    report = qa.evaluate_master(timeline, story_arc=story)

    assert report.checks["scene_sum_consistency"] is False
    assert any(f.rule == "scene_sum_consistency" and f.severity == "ERROR" for f in report.findings)
    assert report.status == PublicationStatus.REJECTED


def test_media_qa_ebur128_loudness_and_true_peak(tmp_qa_dir: Path):
    """Verify EBU R128 loudness and True Peak analysis."""
    mp4_path = tmp_qa_dir / "loudness_master.mp4"
    _generate_synthetic_mp4(mp4_path, duration_sec=65.0)

    ass_path = tmp_qa_dir / "loudness_master.ass"
    _create_sample_ass(ass_path, [(0.5, 64.5, "Texto")])

    timeline = MasterTimeline(
        story_id="test_ebur128",
        target_duration_sec=65.0,
        total_actual_duration_sec=65.0,
        master_video_path=mp4_path,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    report = qa.evaluate_master(timeline)

    assert report.checks["loudness_ebur128"] is True
    assert "integrated_lufs" in report.audio_metrics
    assert report.audio_metrics["integrated_lufs"] is not None
    assert "true_peak_dbtp" in report.audio_metrics


def test_media_qa_spoken_content_subtitle_coverage(tmp_qa_dir: Path):
    """Verify spoken-content coverage: >= 99% passes, dropped scene triggers low coverage error."""
    mp4_path = tmp_qa_dir / "sub_cov_master.mp4"
    _generate_synthetic_mp4(mp4_path, duration_sec=65.0)

    # Subtitles only cover first 20s out of 65s spoken
    ass_path = tmp_qa_dir / "incomplete.ass"
    _create_sample_ass(ass_path, [(0.5, 20.0, "Solo un tercio cubierto")])

    scenes = [
        Scene(id="s1", scene_index=0, narrative_role="hook", script_text="Uno", word_count=1, estimated_duration_sec=1.0, actual_duration_sec=65.0),
    ]
    story = StoryArc(
        id="story_sub_cov",
        contract=StoryContract(id="c1", title="SubCov", topic="Test", core_question="Q?", narrative_promise="P"),
        scenes=scenes,
    )

    timeline = MasterTimeline(
        story_id="story_sub_cov",
        target_duration_sec=65.0,
        total_actual_duration_sec=65.0,
        scene_durations={"s1": 65.0},
        scene_offsets={"s1": 0.0},
        master_video_path=mp4_path,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    report = qa.evaluate_master(timeline, story_arc=story)

    assert report.checks["subtitles_coverage"] is False
    assert report.subtitle_metrics["spoken_coverage_percent"] < 50.0
    assert any("subtitle_spoken_coverage" in f.rule for f in report.findings)
    assert report.status == PublicationStatus.REJECTED


def test_media_qa_decode_integrity_scan(tmp_qa_dir: Path):
    """Verify FFmpeg null-sink frame decode scan passes on clean video."""
    mp4_path = tmp_qa_dir / "decode_master.mp4"
    _generate_synthetic_mp4(mp4_path, duration_sec=62.0)

    qa = FinalMediaQAEngine()
    findings = []
    ok = qa._scan_bitstream_decode(mp4_path, findings)

    assert ok is True
    assert len(findings) == 0


def test_media_qa_hard_gate_rejection_no_export(tmp_qa_dir: Path):
    """Hard Gate: an invalid master (720x1280) MUST NOT be exported and manifest MUST NOT exist."""
    invalid_mp4 = tmp_qa_dir / "invalid_resolution.mp4"
    # Generate 720x1280 (horizontal/non-compliant resolution)
    _generate_synthetic_mp4(invalid_mp4, duration_sec=65.0, width=720, height=1280)

    ass_path = tmp_qa_dir / "invalid_master.ass"
    _create_sample_ass(ass_path, [(0.5, 64.5, "Texto")])

    timeline = MasterTimeline(
        story_id="test_rejection_gate",
        target_duration_sec=65.0,
        total_actual_duration_sec=65.0,
        master_video_path=invalid_mp4,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    export_dir = tmp_qa_dir / "rejected_export_dir"

    report = qa.certify_and_export(timeline, export_dir=export_dir)

    assert report.status == PublicationStatus.REJECTED
    assert report.passed is False
    assert report.certified_output_path is None
    assert report.manifest_path is None
    # Crucial assertion: no certified video or manifest exists in export dir
    assert not (export_dir / "test_rejection_gate_certified_master.mp4").exists()
    assert not (export_dir / "manifest.json").exists()


def test_media_qa_manifest_provenance_generation(tmp_qa_dir: Path):
    """Verify rich cryptographic manifest.json is created upon successful certification."""
    valid_mp4 = tmp_qa_dir / "cert_master.mp4"
    _generate_synthetic_mp4(valid_mp4, duration_sec=65.0)

    ass_path = tmp_qa_dir / "cert_master.ass"
    _create_sample_ass(ass_path, [(0.5, 64.5, "Subtítulo completo")])

    timeline = MasterTimeline(
        story_id="story_manifest_test",
        target_duration_sec=65.0,
        total_actual_duration_sec=65.0,
        scene_order=["s1"],
        scene_durations={"s1": 65.0},
        scene_offsets={"s1": 0.0},
        master_video_path=valid_mp4,
        master_subtitles_path=ass_path,
    )

    qa = FinalMediaQAEngine()
    export_dir = tmp_qa_dir / "certified_golden_export"

    report = qa.certify_and_export(timeline, export_dir=export_dir)

    assert report.passed is True
    assert report.certified_output_path is not None
    assert report.certified_output_path.exists()
    assert report.manifest_path is not None
    assert report.manifest_path.exists()
    assert report.master_sha256 is not None
    assert len(report.master_sha256) == 64

    # Validate contents of manifest.json
    manifest = json.loads(report.manifest_path.read_text(encoding="utf-8"))
    assert manifest["story_id"] == "story_manifest_test"
    assert manifest["master_sha256"] == report.master_sha256
    assert "duration" in manifest
    assert "video" in manifest
    assert manifest["video"]["width"] == 1080
    assert manifest["video"]["height"] == 1920
    assert "audio" in manifest
    assert "subtitles" in manifest
    assert "scenes" in manifest
    assert "checks" in manifest


def test_e2e_golden_case_final_certification(tmp_qa_dir: Path):
    """Full End-to-End Pipeline: Story -> Visual -> Scenes -> Master -> Final Media QA Certification."""
    # 1. Synthesize Story Arc
    architect = StoryArchitect()
    story = architect.synthesize_story("La evolución del automóvil")

    # 2. Resolve Visual Assets
    catalog = AssetCatalog()
    resolver = VisualResolver()
    resolutions = resolver.resolve_story(story, catalog)

    # 3. Produce Scenes
    producer = SceneProducer()
    scene_dir = tmp_qa_dir / "e2e_scenes"
    producer.produce_story_scenes(story, resolutions, scene_dir)

    # 4. Assemble Master Story
    assembler = MasterTimelineAssembler()
    master_dir = tmp_qa_dir / "e2e_master"
    timeline = assembler.assemble_master_story(
        story=story,
        scene_dir=scene_dir,
        output_dir=master_dir,
        bgm_path=None,  # Offline deterministic voice-only
    )

    # 5. Final Media QA & Certification Gate
    qa = FinalMediaQAEngine()
    golden_pub_dir = tmp_qa_dir / "golden_publication"
    report = qa.certify_and_export(timeline, export_dir=golden_pub_dir, story_arc=story)

    # Assertions
    assert report.passed is True
    assert report.status in [PublicationStatus.CERTIFIED_FOR_PUBLICATION, PublicationStatus.CERTIFIED_WITH_WARNINGS]
    assert 61.0 <= report.duration_sec <= 90.0
    assert report.duration_drift_sec <= 0.35
    assert report.video_metrics["width"] == 1080
    assert report.video_metrics["height"] == 1920
    assert report.video_metrics["codec"] == "h264"
    assert report.audio_metrics["codec"] == "aac"
    assert report.checks["container_and_streams"] is True
    assert report.checks["duration_policy"] is True
    assert report.checks["scene_sum_consistency"] is True
    assert report.checks["bitstream_decode"] is True

    # Artifacts in golden publication dir
    assert report.certified_output_path is not None
    assert report.certified_output_path.exists()
    assert report.certified_output_path.stat().st_size > 0
    assert report.manifest_path is not None
    assert report.manifest_path.exists()

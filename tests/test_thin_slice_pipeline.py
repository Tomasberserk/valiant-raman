"""Thin-Slice Integration Test for Phase 1.

Validates the complete end-to-end cinematic pipeline:
1. StoryboardPlanner produces a canonical 6-beat Storyboard for the sword prompt.
2. MockVisualRenderer renders diagnostic 9:16 keyframes and smooth camera motion (Ken Burns).
3. TimelineAssembler sequences all shots into a certified 9:16 master MP4.
4. ffprobe verifies resolution, codec, duration, and stream integrity.
"""

import json
from pathlib import Path
import subprocess
import pytest

from engine.creative.modes import ResolvedContentMode
from engine.story.mock_visual_renderer import MockVisualRenderer
from engine.story.storyboard import Storyboard
from engine.story.storyboard_planner import StoryboardPlanner
from engine.story.timeline_assembler import TimelineAssembler

SWORD_PROMPT = (
    "Un chico encuentra una espada, enterrada en un bosque perdido. "
    "Al sujetarla con sus manos el cielo cambia, pasa de estar vivo y brilloso "
    "a oscuro con relámpagos, viendo en el horizonte cómo almas carroñeras lo "
    "señalan para matarlo, haciendo una secuencia de acción muy chimba."
)


def test_thin_slice_end_to_end_sword_pipeline(tmp_path: Path):
    """Execute end-to-end thin-slice pipeline for the cursed sword prompt."""
    planner = StoryboardPlanner()

    # 1. Plan Storyboard
    storyboard = planner.plan_storyboard(SWORD_PROMPT, target_duration_sec=25.0)
    assert isinstance(storyboard, Storyboard)
    assert storyboard.mode == ResolvedContentMode.NARRATIVE_FICTION
    assert len(storyboard.scenes) == 6
    assert abs(storyboard.total_physical_duration - 25.0) < 0.2

    # Verify character consistency anchor exists
    assert len(storyboard.characters) >= 1
    assert "warrior" in storyboard.characters[0].visual_anchor.lower()

    # 2. Render all shots with MockVisualRenderer & CameraEngine
    renderer = MockVisualRenderer(output_dir=tmp_path / "shots")
    shot_results = {}

    for scene in storyboard.scenes:
        for shot in scene.shots:
            res = renderer.render_shot(
                shot=shot,
                style_bible=storyboard.style_bible,
                characters=storyboard.characters,
                scene_id=scene.scene_id,
            )
            assert Path(res.video_path).exists()
            assert res.duration_seconds == shot.duration_sec
            shot_results[shot.shot_id] = res

    assert len(shot_results) == 6

    # 3. Assemble Master Video
    master_out = tmp_path / "master_sword_epic.mp4"
    assembly = TimelineAssembler.assemble_storyboard_video(
        storyboard=storyboard,
        shot_results=shot_results,
        output_master_path=master_out,
    )

    assert assembly.qa_passed
    assert master_out.exists()
    assert master_out.stat().st_size > 50000  # Significant file size

    # 4. Probe master output with ffprobe to verify technical compliance
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size:stream=width,height,codec_name",
        "-of", "json",
        str(master_out),
    ]
    res_probe = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(res_probe.stdout)

    # Resolution 1080x1920 (9:16)
    video_stream = next(s for s in probe_data["streams"] if s["codec_name"] == "h264")
    assert video_stream["width"] == 1080
    assert video_stream["height"] == 1920

    # Duration ~25.0s
    actual_duration = float(probe_data["format"]["duration"])
    assert abs(actual_duration - 25.0) < 1.0

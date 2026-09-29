"""Unit tests for Phase E: MediaValidator and QAReport checks."""

from pathlib import Path
import subprocess
import pytest

from engine.qa.validator import MediaValidator


def test_qa_missing_file(tmp_path: Path):
    """Verify that inspecting a non-existent file produces a failed QAReport."""
    validator = MediaValidator()
    missing_file = tmp_path / "does_not_exist.mp4"
    report = validator.validate_render(missing_file, expected_duration_sec=10.0)

    assert report.passed is False
    integrity_check = next(c for c in report.checks if c.name == "file_integrity")
    assert integrity_check.passed is False


def test_qa_valid_synthetic_video(tmp_path: Path):
    """Verify that a validly formed MP4 passes resolution, fps, audio, and duration checks."""
    test_video = tmp_path / "test_valid.mp4"
    duration = 2.0

    # Render a 2-second vertical test clip with audio using FFmpeg
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s=1080x1920:r=30:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(test_video),
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0

    validator = MediaValidator(expected_width=1080, expected_height=1920, duration_tolerance_sec=1.0)
    report = validator.validate_render(test_video, expected_duration_sec=duration)

    assert report.passed is True
    res_check = next(c for c in report.checks if c.name == "resolution")
    assert res_check.passed is True
    assert res_check.actual == "1080x1920"

    audio_check = next(c for c in report.checks if c.name == "audio_track")
    assert audio_check.passed is True

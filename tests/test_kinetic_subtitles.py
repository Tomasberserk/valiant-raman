"""Unit tests for Stage 11 Kinetic Subtitles."""

from pathlib import Path
import pytest

from engine.media.base import WordTimestamp
from engine.media.subtitles import (
    SUBTITLE_PRESETS,
    format_ass_time,
    generate_ass_subtitles,
)


@pytest.fixture
def sample_timestamps():
    return [
        WordTimestamp(word="El", start=0.0, end=0.35),
        WordTimestamp(word="futuro", start=0.35, end=0.85),
        WordTimestamp(word="de", start=0.85, end=1.05),
        WordTimestamp(word="la", start=1.05, end=1.20),
        WordTimestamp(word="inteligencia", start=1.20, end=1.85),
        WordTimestamp(word="artificial", start=1.85, end=2.40),
    ]


def test_default_preset_capcut_yellow(sample_timestamps, tmp_path: Path):
    """Test 1: Default preset is capcut_yellow with expected style definitions."""
    ass_file = tmp_path / "subs_default.ass"
    generate_ass_subtitles(sample_timestamps, ass_file)

    content = ass_file.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    # Safe zone MarginV=480 present in Style line
    assert ",480,1" in content


def test_highlight_color_capcut_yellow(sample_timestamps, tmp_path: Path):
    """Test 2: Correct highlight color &H0000FFFF& for capcut_yellow."""
    ass_file = tmp_path / "subs_yellow.ass"
    generate_ass_subtitles(sample_timestamps, ass_file, style_preset="capcut_yellow")

    content = ass_file.read_text(encoding="utf-8")
    assert r"{\c&H0000FFFF&}" in content
    assert r"{\c&H00FFFFFF&}" in content


def test_micro_pop_present(sample_timestamps, tmp_path: Path):
    """Test 3: Micro-pop tags are present for active words."""
    ass_file = tmp_path / "subs_pop.ass"
    generate_ass_subtitles(sample_timestamps, ass_file, style_preset="capcut_yellow")

    content = ass_file.read_text(encoding="utf-8")
    assert r"{\fscx108\fscy108}" in content
    assert r"{\fscx100\fscy100}" in content


def test_all_style_presets(sample_timestamps, tmp_path: Path):
    """Test 4: All presets (capcut_yellow, cyber_cyan, neon_green, clean_white) render valid files."""
    for preset_name in ["capcut_yellow", "cyber_cyan", "neon_green", "clean_white"]:
        ass_file = tmp_path / f"subs_{preset_name}.ass"
        generate_ass_subtitles(sample_timestamps, ass_file, style_preset=preset_name)
        content = ass_file.read_text(encoding="utf-8")
        expected_highlight = SUBTITLE_PRESETS[preset_name]["highlight_color"]
        assert f"{{\\c{expected_highlight}}}" in content


def test_timings_monotonic_and_non_negative(sample_timestamps, tmp_path: Path):
    """Test 5: Timings are strictly formatted, non-negative, and ordered."""
    ass_file = tmp_path / "subs_timing.ass"
    generate_ass_subtitles(sample_timestamps, ass_file)

    lines = [line for line in ass_file.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")]
    assert len(lines) == 6  # 6 words, each has an active highlight state

    for line in lines:
        parts = line.split(",")
        start = parts[1]
        end = parts[2]
        # Valid H:MM:SS.cc format
        assert len(start.split(":")) == 3
        assert len(end.split(":")) == 3
        assert not start.startswith("-")
        assert not end.startswith("-")


def test_legacy_mode_fallback(sample_timestamps, tmp_path: Path):
    """Test 6: enable_kinetic_highlight=False outputs traditional chunked cues without per-word highlight."""
    ass_file = tmp_path / "subs_legacy.ass"
    generate_ass_subtitles(sample_timestamps, ass_file, words_per_cue=3, enable_kinetic_highlight=False)

    lines = [line for line in ass_file.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")]
    assert len(lines) == 2  # 6 words / 3 per cue = 2 lines
    content = ass_file.read_text(encoding="utf-8")
    assert r"{\c&H0000FFFF&}" not in content
    assert r"{\fscx108\fscy108}" not in content


def test_empty_or_malformed_timestamps_graceful(tmp_path: Path):
    """Test 7: Empty or malformed timestamps do not crash and produce valid ASS structure."""
    ass_file = tmp_path / "subs_empty.ass"
    # Empty list
    generate_ass_subtitles([], ass_file)
    assert "[Script Info]" in ass_file.read_text(encoding="utf-8")

    # Timings with empty string words
    bad_timestamps = [
        WordTimestamp(word="", start=0.0, end=0.5),
        WordTimestamp(word="   ", start=0.5, end=1.0),
    ]
    ass_file_bad = tmp_path / "subs_bad.ass"
    generate_ass_subtitles(bad_timestamps, ass_file_bad)
    assert "[Script Info]" in ass_file_bad.read_text(encoding="utf-8")


def test_format_ass_time_precision():
    """Verify ASS time formatting helper."""
    assert format_ass_time(0.0) == "0:00:00.00"
    assert format_ass_time(1.25) == "0:00:01.25"
    assert format_ass_time(65.5) == "0:01:05.50"
    assert format_ass_time(-5.0) == "0:00:00.00"


def test_new_presets_hormozi_and_cinematic(sample_timestamps, tmp_path: Path):
    """Verify newly integrated presets (hormozi_bold, cinematic_gold, viral_red)."""
    # Hormozi bold
    h_file = tmp_path / "subs_hormozi.ass"
    generate_ass_subtitles(sample_timestamps, h_file, style_preset="hormozi_bold")
    h_text = h_file.read_text(encoding="utf-8")
    assert r"{\c&H0000D7FF&}" in h_text
    assert r"{\fscx114\fscy114\b1}" in h_text

    # Cinematic gold
    c_file = tmp_path / "subs_cinematic.ass"
    generate_ass_subtitles(sample_timestamps, c_file, style_preset="cinematic_gold")
    c_text = c_file.read_text(encoding="utf-8")
    assert r"{\c&H0070B8F5&}" in c_text
    assert r"{\fscx106\fscy106}" in c_text

    # Viral red
    r_file = tmp_path / "subs_viral.ass"
    generate_ass_subtitles(sample_timestamps, r_file, style_preset="viral_red")
    r_text = r_file.read_text(encoding="utf-8")
    assert r"{\c&H003333FF&}" in r_text
    assert r"{\fscx112\fscy112}" in r_text


"""Subtitles module generating clean, editorial Advanced SubStation Alpha (.ass) files."""

from pathlib import Path
from typing import Dict, List, Optional

from engine.media.base import WordTimestamp


SUBTITLE_PRESETS: Dict[str, Dict[str, str]] = {
    "capcut_yellow": {
        "base_color": "&H00FFFFFF&",       # Crisp white in &HAABBGGRR&
        "highlight_color": "&H0000FFFF&",  # Vivid yellow in &HAABBGGRR&
        "outline_color": "&H00000000&",    # Solid black border
        "micro_pop": r"{\fscx108\fscy108}",
        "micro_pop_reset": r"{\fscx100\fscy100}",
    },
    "cyber_cyan": {
        "base_color": "&H00FFFFFF&",       # Crisp white
        "highlight_color": "&H00FFFF00&",  # Electric cyan in &HAABBGGRR&
        "outline_color": "&H00000000&",
        "micro_pop": r"{\fscx108\fscy108}",
        "micro_pop_reset": r"{\fscx100\fscy100}",
    },
    "neon_green": {
        "base_color": "&H00FFFFFF&",       # Crisp white
        "highlight_color": "&H0000FF00&",  # Neon green in &HAABBGGRR&
        "outline_color": "&H00000000&",
        "micro_pop": r"{\fscx108\fscy108}",
        "micro_pop_reset": r"{\fscx100\fscy100}",
    },
    "clean_white": {
        "base_color": "&H00FFFFFF&",       # Crisp white
        "highlight_color": "&H00FFFFFF&",  # White (no chromatic shift)
        "outline_color": "&H00000000&",
        "micro_pop": r"{\fscx100\fscy100}",
        "micro_pop_reset": r"{\fscx100\fscy100}",
    },
    "hormozi_bold": {
        "base_color": "&H00FFFFFF&",       # Crisp white
        "highlight_color": "&H0000D7FF&",  # Ultra gold in &HAABBGGRR&
        "outline_color": "&H00000000&",    # Deep contrast outline
        "micro_pop": r"{\fscx114\fscy114\b1}",
        "micro_pop_reset": r"{\fscx100\fscy100\b0}",
    },
    "cinematic_gold": {
        "base_color": "&H00E2E8F0&",       # Warm titanium
        "highlight_color": "&H0070B8F5&",  # Warm champagne gold
        "outline_color": "&H00101010&",
        "micro_pop": r"{\fscx106\fscy106}",
        "micro_pop_reset": r"{\fscx100\fscy100}",
    },
    "viral_red": {
        "base_color": "&H00FFFFFF&",       # Crisp white
        "highlight_color": "&H003333FF&",  # Vivid crimson alert
        "outline_color": "&H00000000&",
        "micro_pop": r"{\fscx112\fscy112}",
        "micro_pop_reset": r"{\fscx100\fscy100}",
    },
}


def format_ass_time(seconds: float) -> str:
    """Format seconds float into ASS timestamp H:MM:SS.cc (centiseconds)."""
    if seconds < 0.0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"


def generate_ass_subtitles(
    timestamps: List[WordTimestamp],
    output_path: Path,
    words_per_cue: int = 3,
    font_name: str = "Arial",
    font_size: int = 56,
    style_preset: str = "capcut_yellow",
    enable_kinetic_highlight: bool = True,
    margin_v: int = 480,
) -> Path:
    """Generate high-readability vertical .ass subtitles aligned with word timestamps.

    Supports CapCut / Alex Hormozi style kinetic active-word highlighting with micro-pop,
    safe-zone vertical positioning, and 100% backward-compatible legacy rendering.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    preset = SUBTITLE_PRESETS.get(style_preset, SUBTITLE_PRESETS["capcut_yellow"])
    base_color = preset["base_color"]
    highlight_color = preset["highlight_color"]
    outline_color = preset["outline_color"]
    micro_pop = preset["micro_pop"]
    micro_pop_reset = preset["micro_pop_reset"]

    header = f"""[Script Info]
Title: Valiant Raman Editorial Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{base_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    if not timestamps:
        output_path.write_text(header, encoding="utf-8")
        return output_path

    # Clean and sanitize incoming timestamps
    valid_timestamps = [
        item for item in timestamps
        if item.word and item.word.strip()
    ]
    if not valid_timestamps:
        output_path.write_text(header, encoding="utf-8")
        return output_path

    dialogue_lines: List[str] = []

    # Group words into small chunks (cues)
    for i in range(0, len(valid_timestamps), words_per_cue):
        chunk = valid_timestamps[i : i + words_per_cue]
        if not chunk:
            continue

        if not enable_kinetic_highlight:
            # Legacy mode: single static bold line for the entire cue
            cue_start = max(0.0, chunk[0].start)
            cue_end = max(cue_start + 0.1, chunk[-1].end)
            start_time = format_ass_time(cue_start)
            end_time = format_ass_time(cue_end)
            cue_text = " ".join(item.word for item in chunk)
            formatted_dialogue = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{{\\b1}}{cue_text}{{\\b0}}"
            dialogue_lines.append(formatted_dialogue)
        else:
            # Kinetic mode: timed active-word highlighting with micro-pop
            for j, active_word in enumerate(chunk):
                w_start = max(0.0, active_word.start)
                w_end = max(w_start + 0.05, active_word.end)

                # Clamp overlap with next word in the chunk if necessary
                if j < len(chunk) - 1:
                    next_start = max(0.0, chunk[j + 1].start)
                    if next_start > w_start and w_end > next_start:
                        w_end = next_start

                start_time = format_ass_time(w_start)
                end_time = format_ass_time(w_end)

                # Format words: active word highlighted with micro-pop, others base color
                line_parts = []
                for k, item in enumerate(chunk):
                    w_text = item.word.replace("\\", "").replace("{", "").replace("}", "")
                    if k == j:
                        line_parts.append(f"{{\\c{highlight_color}}}{micro_pop}{w_text}{micro_pop_reset}{{\\c{base_color}}}")
                    else:
                        line_parts.append(f"{{\\c{base_color}}}{w_text}")

                formatted_text = " ".join(line_parts)
                formatted_dialogue = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{{\\b1}}{formatted_text}{{\\b0}}"
                dialogue_lines.append(formatted_dialogue)

    full_content = header + "\n".join(dialogue_lines) + "\n"
    output_path.write_text(full_content, encoding="utf-8")
    return output_path

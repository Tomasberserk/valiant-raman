"""Subtitles module generating clean, editorial Advanced SubStation Alpha (.ass) files."""

from pathlib import Path
from typing import List

from engine.media.base import WordTimestamp


def format_ass_time(seconds: float) -> str:
    """Format seconds float into ASS timestamp H:MM:SS.cc (centiseconds)."""
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
) -> Path:
    """Generate high-readability vertical .ass subtitles aligned with word timestamps."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines: List[str] = []

    # Group words into small chunks (cues)
    for i in range(0, len(timestamps), words_per_cue):
        chunk = timestamps[i : i + words_per_cue]
        if not chunk:
            continue
        start_time = format_ass_time(chunk[0].start)
        end_time = format_ass_time(chunk[-1].end)
        cue_text = " ".join(item.word for item in chunk)
        # Use simple bold style tag
        formatted_dialogue = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{{\\b1}}{cue_text}{{\\b0}}"
        dialogue_lines.append(formatted_dialogue)

    full_content = header + "\n".join(dialogue_lines) + "\n"
    output_path.write_text(full_content, encoding="utf-8")
    return output_path

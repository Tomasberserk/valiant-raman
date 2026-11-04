"""Visual provider module: Procedural backgrounds, thematic B-roll clips, and local asset visual tracks."""

from abc import ABC, abstractmethod
import logging
from pathlib import Path
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)


class VisualProvider(ABC):
    """Abstract interface for background visual generation."""

    @abstractmethod
    def generate_background(
        self,
        output_path: Path,
        duration_seconds: float,
        topic: str = "",
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        codec: str = "libx264",
    ) -> Path:
        """Create or select a vertical background video file."""
        pass


class ProceduralVisualProvider(VisualProvider):
    """Generates high-definition, stylistically dynamic vertical video backgrounds using FFmpeg lavfi."""

    def __init__(self, default_codec: str = "libx264"):
        self.default_codec = default_codec

    def _determine_palette(self, topic: str) -> tuple[str, str, int]:
        """Select a cohesive dark studio color palette based on thematic topic keywords."""
        topic_lower = topic.lower()

        # Astronomy, Cosmos, Physics
        if any(w in topic_lower for w in ["universo", "cosmos", "espacio", "telescopio", "estrella", "galaxia", "cuántica", "cuantic", "fisica", "space", "planet"]):
            base_color = "0x070b14"  # Deep space midnight
            grid_color = "0x0ea5e9@0.25"  # Soft cosmic cyan grid
            grid_size = 140
        # Technology, AI, Computing, Innovation
        elif any(w in topic_lower for w in ["tecnologia", "computad", "ia", "artificial", "algoritmo", "codigo", "digital", "tech", "software", "robot"]):
            base_color = "0x090e17"  # Deep slate cyber
            grid_color = "0x10b981@0.22"  # Subtle tech emerald grid
            grid_size = 120
        # History, Mysteries, Curiosities
        elif any(w in topic_lower for w in ["misterio", "historia", "antiguo", "secreto", "descubrimiento", "history", "ancient", "war", "empire"]):
            base_color = "0x0e0c18"  # Obsidian violet
            grid_color = "0xf59e0b@0.20"  # Subtle amber glow grid
            grid_size = 130
        # Nature, Earth, Animals
        elif any(w in topic_lower for w in ["naturaleza", "tierra", "mar", "oceano", "selva", "bosque", "fauna", "nature", "animal", "forest", "ocean", "earth"]):
            base_color = "0x06140d"  # Deep forest obsidian
            grid_color = "0x22c55e@0.22"  # Subtle emerald nature grid
            grid_size = 125
        else:
            base_color = "0x0b0f19"  # Studio dark slate
            grid_color = "0x38bdf8@0.22"  # Studio cyan
            grid_size = 120

        return base_color, grid_color, grid_size

    def generate_background(
        self,
        output_path: Path,
        duration_seconds: float,
        topic: str = "",
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        codec: Optional[str] = None,
    ) -> Path:
        """Render a vertical procedural background video using FFmpeg lavfi."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chosen_codec = codec or self.default_codec

        base_color, grid_color, grid_size = self._determine_palette(topic)

        # High-definition vertical filter graph with geometric motion and continuous smooth digital zoom
        lavfi_graph = (
            f"color=c={base_color}:s={width}x{height}:r={fps}:d={duration_seconds},"
            f"drawgrid=w={grid_size}:h={grid_size}:t=1:c={grid_color},"
            f"zoompan=z='min(zoom+0.0006,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps},"
            f"format=yuv420p"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", lavfi_graph,
            "-c:v", chosen_codec,
        ]

        if chosen_codec == "libx264":
            cmd.extend(["-preset", "veryfast", "-crf", "22"])

        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-t", str(duration_seconds),
            str(output_path),
        ])

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg procedural visual generation failed: {res.stderr}")
            raise RuntimeError(f"Procedural visual generation failed: {res.stderr}")

        return output_path


class ThematicBrollVisualProvider(VisualProvider):
    """Categorized B-roll footage provider with 9:16 normalization and resilient procedural fallback."""

    CATEGORIES = ("tech", "space", "history", "nature", "general")

    def __init__(
        self,
        assets_dir: Optional[Path] = None,
        fallback_provider: Optional[VisualProvider] = None,
    ):
        from config.settings import settings
        self.assets_dir = assets_dir or (settings.assets_dir / "broll")
        self.fallback_provider = fallback_provider or ProceduralVisualProvider()

    @classmethod
    def detect_category(cls, topic: str) -> str:
        """Deterministic keyword-based category matcher for editorial topics."""
        import re
        topic_lower = topic.lower()
        tokens = set(re.findall(r"[a-záéíóúñ]+", topic_lower))

        def has_match(keywords: list[str], prefixes: list[str]) -> bool:
            if any(k in topic_lower for k in keywords):
                return True
            for t in tokens:
                if any(t.startswith(p) for p in prefixes):
                    return True
            return False

        # Tech
        if has_match(
            keywords=["machine learning", "artificial intelligence", "inteligencia artificial", "deep learning"],
            prefixes=["ai", "ia", "tech", "tecnolog", "computad", "software", "robot", "internet", "cod", "digit", "algoritm", "program", "dato"],
        ):
            return "tech"

        # Space
        if has_match(
            keywords=["deep space", "james webb", "via lactea"],
            prefixes=["space", "planet", "nasa", "galax", "univers", "star", "espacio", "cosmos", "telescop", "estrell", "fisic", "cuantic"],
        ):
            return "space"

        # History
        if has_match(
            keywords=["imperio romano", "edad media", "antigua roma", "antiguo egipto"],
            prefixes=["histor", "ancient", "war", "empir", "civiliz", "antigu", "misteri", "secret", "descubri", "guerr", "imperi", "siglo", "arqueol"],
        ):
            return "history"

        # Nature
        if has_match(
            keywords=["medio ambiente", "fauna silvestre", "vida marina"],
            prefixes=["natur", "animal", "forest", "ocean", "earth", "climat", "tierra", "oceano", "selva", "bosque", "faun"],
        ) or "mar" in tokens:
            return "nature"

        return "general"

        return "general"

    def discover_clips(self, category: str) -> List[Path]:
        """Find local MP4 video clips matching category, falling back to general or root."""
        if not self.assets_dir.exists() or not self.assets_dir.is_dir():
            return []

        # 1. Check category subfolder
        cat_dir = self.assets_dir / category
        if cat_dir.exists() and cat_dir.is_dir():
            clips = sorted(list(cat_dir.glob("*.mp4")))
            if clips:
                return clips

        # 2. Check 'general' subfolder
        if category != "general":
            general_dir = self.assets_dir / "general"
            if general_dir.exists() and general_dir.is_dir():
                clips = sorted(list(general_dir.glob("*.mp4")))
                if clips:
                    return clips

        # 3. Check root broll directory
        root_clips = sorted(list(self.assets_dir.glob("*.mp4")))
        return root_clips

    def generate_background(
        self,
        output_path: Path,
        duration_seconds: float,
        topic: str = "",
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        codec: str = "libx264",
    ) -> Path:
        """Render vertical B-roll montage or loop, falling back seamlessly to procedural generator."""
        category = self.detect_category(topic)
        clips = self.discover_clips(category)

        if not clips:
            logger.info(f"No B-roll clips found for category '{category}'. Falling back to procedural visuals.")
            return self.fallback_provider.generate_background(
                output_path=output_path,
                duration_seconds=duration_seconds,
                topic=topic,
                width=width,
                height=height,
                fps=fps,
                codec=codec,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if len(clips) == 1:
                # Single clip: loop seamlessly and scale/crop to vertical 9:16
                source_video = clips[0]
                filter_chain = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},setsar=1,fps={fps}"
                )
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-stream_loop", "-1",
                    "-i", str(source_video),
                    "-vf", filter_chain,
                    "-c:v", codec,
                    "-preset", "veryfast",
                    "-t", str(duration_seconds),
                    "-pix_fmt", "yuv420p",
                    str(output_path),
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return output_path
                logger.warning(f"Single B-roll processing failed: {res.stderr}. Trying procedural fallback.")
            else:
                # Multi-clip sequencing: cut every 3.5 to 5.0 seconds
                num_clips = len(clips)
                segment_duration = max(3.0, duration_seconds / num_clips)

                cmd = ["ffmpeg", "-y"]
                filter_parts = []
                concat_inputs = []

                for i, clip in enumerate(clips):
                    cmd.extend(["-stream_loop", "-1", "-i", str(clip)])
                    filter_parts.append(
                        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height},setsar=1,fps={fps},"
                        f"trim=duration={segment_duration:.2f},setpts=PTS-STARTPTS[v{i}]"
                    )
                    concat_inputs.append(f"[v{i}]")

                filter_complex = ";".join(filter_parts) + f";{''.join(concat_inputs)}concat=n={num_clips}:v=1:a=0[vout]"
                cmd.extend([
                    "-filter_complex", filter_complex,
                    "-map", "[vout]",
                    "-c:v", codec,
                    "-preset", "veryfast",
                    "-t", str(duration_seconds),
                    "-pix_fmt", "yuv420p",
                    str(output_path),
                ])

                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return output_path
                logger.warning(f"Multi-clip B-roll montage failed: {res.stderr}. Trying procedural fallback.")

        except Exception as e:
            logger.warning(f"Error during B-roll assembly: {e}. Falling back to procedural visuals.")

        # Fallback to procedural visual provider
        return self.fallback_provider.generate_background(
            output_path=output_path,
            duration_seconds=duration_seconds,
            topic=topic,
            width=width,
            height=height,
            fps=fps,
            codec=codec,
        )


class LocalAssetVisualProvider(ThematicBrollVisualProvider):
    """Backwards-compatible alias for ThematicBrollVisualProvider."""
    pass


def get_default_visual_provider() -> VisualProvider:
    """Resolve default visual provider according to configuration."""
    import os
    provider_type = os.getenv("VISUAL_PROVIDER", "procedural").lower()
    if provider_type in ["broll", "local"]:
        return ThematicBrollVisualProvider()
    return ProceduralVisualProvider()

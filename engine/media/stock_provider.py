"""Stock video provider module integrating royalty-free stock footage (Pexels / Pixabay) with LRU caching.

Inspired by MoneyPrinterTurbo's material acquisition pipeline, refactored into Clean Architecture
with strict offline procedural fallback, 9:16 vertical normalization, and zero hard dependencies.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Optional
import urllib.parse
import urllib.request

from engine.media.visuals import ProceduralVisualProvider, VisualProvider

logger = logging.getLogger(__name__)


class StockVideoProvider(VisualProvider):
    """Acquires high-resolution vertical B-roll from Pexels/Pixabay with local caching and procedural fallback."""

    def __init__(
        self,
        pexels_api_key: Optional[str] = None,
        pixabay_api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        fallback_provider: Optional[VisualProvider] = None,
        default_codec: str = "libx264",
    ):
        self.pexels_api_key = pexels_api_key or os.getenv("PEXELS_API_KEY")
        self.pixabay_api_key = pixabay_api_key or os.getenv("PIXABAY_API_KEY")
        self.default_codec = default_codec

        if cache_dir is None:
            from config.settings import STORAGE_DIR
            self.cache_dir = STORAGE_DIR / "materials_cache"
        else:
            self.cache_dir = Path(cache_dir)

        self.fallback_provider = fallback_provider or ProceduralVisualProvider(default_codec=default_codec)

    def _compute_cache_key(self, topic: str, duration: float) -> str:
        """Create a deterministic hash key for cached footage based on query and duration."""
        normalized_query = " ".join(topic.lower().split())
        raw_key = f"{normalized_query}_{round(duration, 1)}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

    def _search_pexels(self, query: str) -> Optional[str]:
        """Query Pexels Video Search API for vertical or landscape HD video URL."""
        if not self.pexels_api_key:
            return None

        # Clean query: extract first 3 substantive words
        words = [w for w in query.split() if len(w) > 2][:3]
        clean_query = " ".join(words) or query

        encoded_q = urllib.parse.quote(clean_query)
        # Try portrait orientation first for native 9:16
        url = f"https://api.pexels.com/videos/search?query={encoded_q}&per_page=5&orientation=portrait"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self.pexels_api_key,
                "User-Agent": "ValiantRamanStudio/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                videos = data.get("videos", [])
                if not videos:
                    # Fallback search without orientation restriction
                    alt_url = f"https://api.pexels.com/videos/search?query={encoded_q}&per_page=5"
                    alt_req = urllib.request.Request(alt_url, headers=req.headers)
                    with urllib.request.urlopen(alt_req, timeout=8.0) as alt_resp:
                        data = json.loads(alt_resp.read().decode("utf-8"))
                        videos = data.get("videos", [])

                for video in videos:
                    files = video.get("video_files", [])
                    # Pick highest resolution MP4
                    mp4_files = [f for f in files if f.get("file_type") == "video/mp4" or "mp4" in f.get("link", "")]
                    if mp4_files:
                        best = sorted(mp4_files, key=lambda x: (x.get("width", 0) * x.get("height", 0)), reverse=True)[0]
                        return best.get("link")
        except Exception as e:
            logger.warning(f"Pexels search failed for '{clean_query}': {e}")

        return None

    def _search_pixabay(self, query: str) -> Optional[str]:
        """Query Pixabay Video Search API as secondary stock provider."""
        if not self.pixabay_api_key:
            return None

        words = [w for w in query.split() if len(w) > 2][:3]
        clean_query = " ".join(words) or query
        encoded_q = urllib.parse.quote(clean_query)
        url = f"https://pixabay.com/api/videos/?key={self.pixabay_api_key}&q={encoded_q}&per_page=5&video_type=film"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ValiantRamanStudio/1.0"})
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                hits = data.get("hits", [])
                for hit in hits:
                    videos = hit.get("videos", {})
                    # Prefer large or medium
                    for size in ["large", "medium", "small"]:
                        v = videos.get(size)
                        if v and v.get("url"):
                            return v.get("url")
        except Exception as e:
            logger.warning(f"Pixabay search failed for '{clean_query}': {e}")

        return None

    def _download_file(self, url: str, dest: Path) -> Path:
        """Download remote media file to destination path."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "ValiantRamanStudio/1.0"})
        with urllib.request.urlopen(req, timeout=20.0) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return dest

    def _normalize_video_format(
        self,
        src: Path,
        dest: Path,
        duration: float,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        codec: str = "libx264",
    ) -> Path:
        """Standardize raw stock video into exactly 9:16 aspect ratio, target duration, and remove audio."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Scale to fill 1080x1920 then center-crop, loop if shorter than duration
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"setsar=1,fps={fps}"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1",  # Loop clip seamlessly if shorter than target duration
            "-i", str(src),
            "-t", str(duration),
            "-vf", vf,
            "-an",  # Strip original stock audio
            "-c:v", codec,
            "-pix_fmt", "yuv420p",
            str(dest),
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg normalization failed: {res.stderr}")

        return dest

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
        """Generate or retrieve vertical video background matching scene topic."""
        # Check if we have credentials for stock retrieval
        if not self.pexels_api_key and not self.pixabay_api_key:
            logger.info("No stock media API keys configured. Delegating to procedural fallback.")
            return self.fallback_provider.generate_background(
                output_path=output_path,
                duration_seconds=duration_seconds,
                topic=topic,
                width=width,
                height=height,
                fps=fps,
                codec=codec,
            )

        cache_key = self._compute_cache_key(topic, duration_seconds)
        cached_file = self.cache_dir / f"{cache_key}.mp4"

        # 1. Cache hit check
        if cached_file.exists() and cached_file.stat().st_size > 50:
            logger.info(f"Stock video cache hit for query '{topic}' -> {cached_file}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached_file, output_path)
            return output_path

        # 2. Search Pexels or Pixabay
        video_url = self._search_pexels(topic)
        if not video_url:
            video_url = self._search_pixabay(topic)

        if not video_url:
            logger.info(f"No stock video found for '{topic}'. Falling back to procedural provider.")
            return self.fallback_provider.generate_background(
                output_path=output_path,
                duration_seconds=duration_seconds,
                topic=topic,
                width=width,
                height=height,
                fps=fps,
                codec=codec,
            )

        # 3. Download and normalize
        try:
            temp_raw = self.cache_dir / f"raw_{cache_key}.tmp"
            self._download_file(video_url, temp_raw)
            self._normalize_video_format(
                src=temp_raw,
                dest=cached_file,
                duration=duration_seconds,
                width=width,
                height=height,
                fps=fps,
                codec=codec,
            )
            if temp_raw.exists():
                temp_raw.unlink()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached_file, output_path)
            return output_path
        except Exception as e:
            logger.warning(f"Error processing stock video from {video_url}: {e}. Falling back to procedural.")
            return self.fallback_provider.generate_background(
                output_path=output_path,
                duration_seconds=duration_seconds,
                topic=topic,
                width=width,
                height=height,
                fps=fps,
                codec=codec,
            )

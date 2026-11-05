"""Visual Asset Cache for idempotent shot rendering and credit preservation."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VisualAssetCache:
    """Manages disk-backed caching of generated keyframe images and rendered shots."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("storage/cache/visuals")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def compute_shot_hash(
        cls,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        seed: Optional[int] = None,
        provider_name: str = "default",
    ) -> str:
        """Calculate deterministic SHA256 hash for visual generation parameters."""
        raw_key = f"{provider_name}:{prompt}:{negative_prompt}:{width}x{height}:{seed}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get_cached_keyframe(self, shot_hash: str) -> Optional[Path]:
        """Return path to cached keyframe if it exists and is non-empty."""
        candidate = self.cache_dir / f"{shot_hash}.png"
        if candidate.exists() and candidate.stat().st_size > 0:
            logger.debug(f"VisualAssetCache hit for hash {shot_hash[:10]}")
            return candidate
        return None

    def store_cached_keyframe(self, shot_hash: str, source_path: Path) -> Path:
        """Store keyframe into cache directory."""
        target = self.cache_dir / f"{shot_hash}.png"
        if source_path != target:
            target.write_bytes(source_path.read_bytes())
        return target

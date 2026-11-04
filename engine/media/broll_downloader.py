"""Auxiliary tooling for downloading and cataloging royalty-free B-roll clips and BGM.

NOTE: This script is purely an offline/manual developer utility and is NEVER executed
automatically in the critical path of video rendering or API endpoints.
"""

import argparse
import logging
import os
from pathlib import Path
from typing import Optional
import urllib.request

logger = logging.getLogger(__name__)


def download_clip_from_url(url: str, output_path: Path) -> Optional[Path]:
    """Download an asset from a direct URL into the local catalog."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, str(output_path))
        logger.info(f"Downloaded asset to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to download asset from {url}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Valiant Raman B-Roll Asset Tool")
    parser.add_argument("--category", choices=["tech", "space", "history", "nature", "general"], default="tech")
    parser.add_argument("--url", type=str, help="Direct URL to MP4 clip")
    parser.add_argument("--filename", type=str, help="Target filename (e.g. clip_01.mp4)")
    args = parser.parse_args()

    from config.settings import settings
    target_dir = settings.assets_dir / "broll" / args.category

    if args.url and args.filename:
        dest = target_dir / args.filename
        download_clip_from_url(args.url, dest)
    else:
        print(f"B-roll target directory for '{args.category}': {target_dir}")
        print("To download: python -m engine.media.broll_downloader --category tech --url <URL> --filename clip.mp4")


if __name__ == "__main__":
    main()

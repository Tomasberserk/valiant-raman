"""Configuration settings for valiant-raman Short-Form Content Engine."""

from pathlib import Path
from pydantic import BaseModel, Field

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
ASSETS_DIR = STORAGE_DIR / "assets"
OUTPUT_DIR = STORAGE_DIR / "output"
DB_PATH = STORAGE_DIR / "experiments.db"

# Ensure storage directories exist
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class EngineSettings(BaseModel):
    """Core settings and hardware configuration."""

    database_url: str = Field(
        default=f"sqlite:///{DB_PATH.as_posix()}",
        description="SQLAlchemy database URL",
    )
    pipeline_version: str = Field(default="0.1.0-mvp", description="Version of the pipeline")
    default_width: int = Field(default=1080, description="Target video width")
    default_height: int = Field(default=1920, description="Target video height")
    default_fps: int = Field(default=30, description="Target frames per second")
    prefer_nvenc: bool = Field(default=True, description="Attempt NVENC before fallback to libx264")
    assets_dir: Path = Field(default=ASSETS_DIR)
    output_dir: Path = Field(default=OUTPUT_DIR)
    db_path: Path = Field(default=DB_PATH)


settings = EngineSettings()

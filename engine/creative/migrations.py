"""Idempotent, non-destructive SQLite database migrations for Phase 2 Creative Workspace."""

from typing import List, Optional, Union
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import settings
from engine.experiments.models import Base
# Import creative models to register them with Base.metadata
import engine.creative.models  # noqa: F401


def get_table_columns(engine: Engine, table_name: str) -> List[str]:
    """Retrieve list of column names for a given SQLite table via PRAGMA table_info."""
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        return [row[1] for row in result.fetchall()]


def table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists in the SQLite database."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
            ),
            {"name": table_name},
        )
        return result.fetchone() is not None


def migrate_db(engine_or_url: Optional[Union[Engine, str]] = None) -> None:
    """Apply non-destructive, idempotent schema updates.
    
    1. Checks if 'experiments' table exists.
    2. Safely executes ALTER TABLE for 'source_concept_id' and 'series_id' if missing.
    3. Safely creates new tables (series, ideas, concepts) via metadata.create_all.
    4. Preserves all preexisting rows and indices completely intact.
    """
    if engine_or_url is None:
        target_engine = create_engine(settings.database_url, echo=False)
    elif isinstance(engine_or_url, str):
        target_engine = create_engine(engine_or_url, echo=False)
    else:
        target_engine = engine_or_url

    # Step 1: Ensure existing tables or create from scratch
    # First create any tables in metadata (this creates series, ideas, concepts if new)
    Base.metadata.create_all(target_engine)

    # Step 2: If 'experiments' table already existed from Phase 1, ensure new columns are present
    if table_exists(target_engine, "experiments"):
        cols = get_table_columns(target_engine, "experiments")
        with target_engine.begin() as conn:
            if "source_concept_id" not in cols:
                conn.execute(
                    text("ALTER TABLE experiments ADD COLUMN source_concept_id VARCHAR(36) REFERENCES concepts(id)")
                )
            if "series_id" not in cols:
                conn.execute(
                    text("ALTER TABLE experiments ADD COLUMN series_id VARCHAR(36) REFERENCES series(id)")
                )

    # Step 3: Ensure concepts table has generation column and active concept uniqueness
    if table_exists(target_engine, "concepts"):
        with target_engine.connect() as conn:
            concept_count = conn.execute(text("SELECT COUNT(*) FROM concepts")).scalar() or 0
        if concept_count == 0:
            # Table is empty; recreate cleanly with generation and generation-scoped unique constraint
            with target_engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS concepts"))
            Base.metadata.tables["concepts"].create(target_engine)
        else:
            cols_c = get_table_columns(target_engine, "concepts")
            if "generation" not in cols_c:
                with target_engine.begin() as conn:
                    conn.execute(text("ALTER TABLE concepts ADD COLUMN generation INTEGER NOT NULL DEFAULT 1"))

        # Create partial unique index to enforce at most 1 active concept per (idea_id, concept_number)
        with target_engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_idea_active_concept "
                    "ON concepts (idea_id, concept_number) "
                    "WHERE status IN ('proposed', 'selected')"
                )
            )


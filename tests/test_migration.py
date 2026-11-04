"""Unit tests for Phase 2: Non-destructive and idempotent SQLite migration."""

from pathlib import Path
import sqlite3
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from engine.creative.migrations import get_table_columns, migrate_db, table_exists
from engine.creative.models import Concept, Idea, Series
from engine.experiments.models import Experiment


def create_phase1_database(db_file: Path) -> None:
    """Simulate a pure Phase 1 database strictly without any Phase 2 tables or columns."""
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE experiments (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        status VARCHAR(50) NOT NULL,
        created_at DATETIME,
        updated_at DATETIME
    );
    """)

    cur.execute("""
    CREATE TABLE hypotheses (
        id VARCHAR(36) PRIMARY KEY,
        experiment_id VARCHAR(36) NOT NULL REFERENCES experiments(id),
        statement TEXT NOT NULL,
        independent_variable VARCHAR(255) NOT NULL,
        primary_metric VARCHAR(255) NOT NULL,
        success_criterion TEXT NOT NULL,
        baseline_description TEXT NOT NULL,
        created_at DATETIME
    );
    """)

    cur.execute("""
    CREATE TABLE variants (
        id VARCHAR(36) PRIMARY KEY,
        hypothesis_id VARCHAR(36) NOT NULL REFERENCES hypotheses(id),
        name VARCHAR(255) NOT NULL,
        variant_code VARCHAR(10) NOT NULL,
        hook_type VARCHAR(50) NOT NULL,
        parameters_json TEXT NOT NULL,
        created_at DATETIME
    );
    """)

    # Insert a real preexisting experiment and hypothesis
    cur.execute("""
    INSERT INTO experiments (id, name, description, status)
    VALUES ('exp-orig-001', 'James Webb Original', 'Legacy experiment from Phase 1', 'active');
    """)

    cur.execute("""
    INSERT INTO hypotheses (id, experiment_id, statement, independent_variable, primary_metric, success_criterion, baseline_description)
    VALUES ('hyp-orig-001', 'exp-orig-001', 'Testing hook', 'hook_type', 'retention_at_3s', 'criterion', 'baseline');
    """)

    cur.execute("""
    INSERT INTO variants (id, hypothesis_id, name, variant_code, hook_type, parameters_json)
    VALUES ('var-orig-001', 'hyp-orig-001', 'Variant A', 'A', 'QUESTION', '{}');
    """)

    conn.commit()
    conn.close()


def test_sqlite_migration_idempotent_and_non_destructive(tmp_path: Path):
    """Test full migration lifecycle on a simulated preexisting database."""
    test_db_path = tmp_path / "legacy_experiments.db"
    create_phase1_database(test_db_path)

    db_url = f"sqlite:///{test_db_path.as_posix()}"
    engine = create_engine(db_url)

    # 1. Pre-migration verification: confirm Phase 2 columns and tables DO NOT exist
    assert table_exists(engine, "experiments") is True
    assert table_exists(engine, "series") is False
    assert table_exists(engine, "ideas") is False
    assert table_exists(engine, "concepts") is False

    orig_cols = get_table_columns(engine, "experiments")
    assert "source_concept_id" not in orig_cols
    assert "series_id" not in orig_cols

    # 2. Run Migration #1
    migrate_db(engine)

    # 3. Post-migration verification: tables and columns exist
    assert table_exists(engine, "series") is True
    assert table_exists(engine, "ideas") is True
    assert table_exists(engine, "concepts") is True

    new_cols = get_table_columns(engine, "experiments")
    assert "source_concept_id" in new_cols
    assert "series_id" in new_cols

    # 4. Data preservation: original records MUST remain intact
    with Session(engine) as session:
        exp = session.get(Experiment, "exp-orig-001")
        assert exp is not None
        assert exp.name == "James Webb Original"
        assert exp.source_concept_id is None
        assert exp.series_id is None
        assert len(exp.hypotheses) == 1
        assert len(exp.hypotheses[0].variants) == 1

        # 5. Insert new Phase 2 entities linked to existing data
        series = Series(name="Mitos del Espacio", premise="Desmontando mitos espaciales")
        session.add(series)
        session.flush()

        idea = Idea(
            raw_input="El sol es amarillo",
            theme="Astronomía",
            editorial_angle="El sol en realidad emite luz blanca",
            series_id=series.id,
        )
        session.add(idea)
        session.flush()

        concept_1 = Concept(
            idea_id=idea.id,
            concept_number=1,
            title="Te mintieron sobre el color del sol",
            hook_text="¿De qué color crees que es el sol?",
            hook_type="QUESTION",
            angle_description="Explicación atmosférica",
        )
        session.add(concept_1)
        session.flush()

        saved_series_id = series.id
        saved_idea_id = idea.id
        saved_concept_id = concept_1.id

        # Link legacy experiment to new concept and series
        exp.source_concept_id = saved_concept_id
        exp.series_id = saved_series_id
        session.commit()

    # 6. Verify constraints in SQLite (concept_number 1..3 and UNIQUE idea_id, concept_number)
    with Session(engine) as session:
        # Test out-of-range concept_number
        with pytest.raises(Exception):
            invalid_concept = Concept(
                idea_id=saved_idea_id,
                concept_number=4,  # CHECK constraint violation
                title="Invalid",
                hook_text="Invalid",
                hook_type="SURPRISE",
                angle_description="Invalid",
            )
            session.add(invalid_concept)
            session.commit()
        session.rollback()

        # Test duplicate concept_number for same idea
        with pytest.raises(Exception):
            dup_concept = Concept(
                idea_id=saved_idea_id,
                concept_number=1,  # Duplicate of concept_1
                title="Duplicate",
                hook_text="Duplicate",
                hook_type="STATEMENT",
                angle_description="Duplicate",
            )
            session.add(dup_concept)
            session.commit()
        session.rollback()

    # 7. Idempotence: execute migrate_db 2nd and 3rd time
    migrate_db(engine)
    migrate_db(engine)

    # Confirm all data and schema remain perfectly intact
    with Session(engine) as session:
        re_checked_exp = session.get(Experiment, "exp-orig-001")
        assert re_checked_exp is not None
        assert re_checked_exp.source_concept_id == saved_concept_id
        assert re_checked_exp.series_id == saved_series_id
        assert re_checked_exp.source_concept.title == "Te mintieron sobre el color del sol"


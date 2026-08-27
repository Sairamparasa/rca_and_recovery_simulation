"""
Tests for Relational Database Schema and Ingestion Pipeline.
"""

from pathlib import Path
import pytest
from sqlmodel import SQLModel, create_engine, Session, select

from arth_rca.db.models import Snapshot, Activity, Relationship, CalendarModel
from arth_rca.ingestion.pipeline import IngestionPipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session():
    """Create in-memory SQLite / Postgres test session with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_ingestion_pipeline_end_to_end(db_session):
    pipeline = IngestionPipeline(db_session)
    fixture_path = FIXTURES_DIR / "fixture_standard_cpm.xer"

    snapshot, val_res = pipeline.ingest_xer_file(
        file_path=fixture_path,
        org_name="Test Enterprise",
        project_name="Standard CPM Project",
    )

    assert val_res.is_valid is True
    assert snapshot.id is not None
    assert snapshot.source_filename == "fixture_standard_cpm.xer"

    # Verify Activities Count & Integrity
    activities = db_session.exec(
        select(Activity).where(Activity.snapshot_id == snapshot.id)
    ).all()
    assert len(activities) == 6

    # Verify Relationships Count & Hashes
    relationships = db_session.exec(
        select(Relationship).where(Relationship.snapshot_id == snapshot.id)
    ).all()
    assert len(relationships) == 6
    for rel in relationships:
        assert len(rel.relationship_key) == 32  # SHA256 stable key

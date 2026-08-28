"""
Test Suite for Snapshot Ingestion Pipeline & API Endpoints.
Verifies parsing, relational table loading, integrity validation, and API uploads.
"""

import pytest
from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine
from fastapi.testclient import TestClient

from arth_rca.api.app import app
from arth_rca.ingestion.pipeline import IngestionPipeline
from arth_rca.db.database import get_db
from arth_rca.db.models import Snapshot, Project, Activity, Relationship

from sqlalchemy.pool import StaticPool

FIXTURE_PATH = Path("tests/fixtures/fixture_standard_cpm.xer")


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_db):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_ingestion_pipeline_direct_execution(test_db):
    pipeline = IngestionPipeline(test_db)
    snapshot, val_res = pipeline.ingest_xer_file(
        file_path=FIXTURE_PATH,
        org_name="Test Engineering Org",
        project_name="Test Substation Project",
        is_baseline=True,
        strict_validation=True,
    )

    assert snapshot is not None
    assert snapshot.id is not None
    assert snapshot.is_baseline is True
    assert val_res.is_valid is True

    # Verify activities and relationships loaded
    acts = test_db.query(Activity).filter(Activity.snapshot_id == snapshot.id).all()
    rels = test_db.query(Relationship).filter(Relationship.snapshot_id == snapshot.id).all()

    assert len(acts) >= 3
    assert len(rels) >= 2


def test_ingestion_api_endpoints(client):
    # 1. Test ingest by server-side path
    path_payload = {
        "file_path": str(FIXTURE_PATH),
        "org_name": "API Test Org",
        "project_name": "API Ingest Project",
        "is_baseline": True,
        "strict_validation": True,
    }
    res = client.post("/api/v1/snapshots/ingest_path", json=path_payload)
    if res.status_code != 200:
        print("API ERROR DETAIL:", res.json())
    assert res.status_code == 200
    data = res.json()
    assert data["snapshot_id"] is not None
    assert data["project_name"] == "API Ingest Project"
    assert data["is_baseline"] is True
    assert data["activity_count"] >= 3

    # 2. Test multipart file upload
    with open(FIXTURE_PATH, "rb") as f:
        upload_res = client.post(
            "/api/v1/snapshots/upload",
            files={"file": ("uploaded_schedule.xer", f, "application/octet-stream")},
            data={"org_name": "Upload Org", "is_baseline": "false"},
        )
    assert upload_res.status_code == 200
    up_data = upload_res.json()
    assert up_data["snapshot_id"] is not None
    assert up_data["is_baseline"] is False
    assert up_data["source_filename"] == "uploaded_schedule.xer"

    # 3. Test list snapshots endpoint
    list_res = client.get("/api/v1/snapshots")
    assert list_res.status_code == 200
    snaps = list_res.json()
    assert len(snaps) >= 2

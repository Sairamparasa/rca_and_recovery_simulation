"""
API route tests for Phase 1 endpoints:
- Health check
- Scoring config GET / PUT
- Drivers and DCMA assessment on ingested fixtures
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine

from arth_rca.api.app import app
from arth_rca.db.database import get_db
from arth_rca.ingestion.pipeline import IngestionPipeline


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_scoring_config_crud(client):
    # GET default config
    res_get = client.get("/api/v1/projects/999/scoring-config")
    assert res_get.status_code == 200
    assert res_get.json()["float_magnitude_weight"] == 1.0

    # PUT custom config
    payload = {
        "project_id": 999,
        "float_magnitude_weight": 2.5,
        "milestone_weight": 4.0,
        "downstream_count_weight": 1.2,
    }
    res_put = client.put("/api/v1/projects/999/scoring-config", json=payload)
    assert res_put.status_code == 200
    assert res_put.json()["milestone_weight"] == 4.0

    # GET updated config
    res_get_updated = client.get("/api/v1/projects/999/scoring-config")
    assert res_get_updated.status_code == 200
    assert res_get_updated.json()["float_magnitude_weight"] == 2.5


def test_snapshot_drivers_and_dcma_api(client, test_db):
    pipeline = IngestionPipeline(test_db)
    fixture_path = Path("tests/fixtures/fixture_standard_cpm.xer")
    snapshot, project = pipeline.ingest_xer_file(fixture_path, project_name="API Test Proj")
    snap_id = snapshot.id

    # Test Drivers endpoint
    drivers_res = client.get(f"/api/v1/snapshots/{snap_id}/drivers")
    assert drivers_res.status_code == 200
    drivers_data = drivers_res.json()
    assert "drivers" in drivers_data
    assert "convergence_nodes" in drivers_data

    # Test DCMA endpoint
    dcma_res = client.get(f"/api/v1/snapshots/{snap_id}/dcma")
    assert dcma_res.status_code == 200
    dcma_data = dcma_res.json()
    assert "overall_health_score" in dcma_data
    assert len(dcma_data["metrics"]) == 14

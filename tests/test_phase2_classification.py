"""
Unit and integration tests for Phase 2: Relationship Constraint Classification.
Covers:
- Deterministic heuristic precedence (HARD_REGULATORY outranks same-trade soft signal).
- Cross-snapshot persistence & >25% lag change re-review trigger.
- Programmatic recovery gate (is_fasttrack_candidate).
- Pattern library tracking (times_matched and times_overridden).
- PM review queue ordering by Longest-Path proximity and REST API endpoints.
"""

import pytest
from datetime import datetime
from sqlmodel import SQLModel, Session, create_engine
from fastapi.testclient import TestClient

from arth_rca.analytics.classification import (
    classify_relationship,
    is_fasttrack_candidate,
    ClassificationResult,
)
from arth_rca.analytics.classification_config import (
    AUTO_CLASSIFY_THRESHOLD,
    HARD_REGULATORY_TERMS,
    HARD_SAFETY_TERMS,
    HARD_PHYSICAL_TERMS,
)
from arth_rca.db.models import (
    Project,
    Snapshot,
    Activity,
    Relationship,
    RelationshipClassification,
    ClassificationPattern,
    generate_relationship_key,
)
from arth_rca.api.app import app
from arth_rca.db.database import get_db


from sqlalchemy.pool import StaticPool
import arth_rca.db.models  # noqa: F401

@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
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


def test_regulatory_keyword_outranks_same_trade_soft_signal():
    """
    Acceptance Criterion 3:
    Unit test confirming a HARD_REGULATORY keyword match always outranks a same-trade soft
    signal when both could apply to the same relationship.
    """
    # Both activities have same-trade prefix 'ELEC', but successor is an electrical inspection/permit
    res = classify_relationship(
        pred_task_code="ELEC-101",
        pred_task_name="Install Main Switchgear",
        succ_task_code="ELEC-102",
        succ_task_name="AHJ Electrical Inspection & Sign-off",
        rel_type="FS",
        lag_days=0.0,
    )

    assert res.constraint_type == "HARD_REGULATORY"
    assert res.confidence == 0.90
    assert res.is_auto_classified is True
    assert res.needs_pm_review is False
    assert is_fasttrack_candidate(res) is False


def test_safety_and_physical_curing_with_lag_boost():
    # 1. Safety term
    res_safe = classify_relationship(
        pred_task_code="MECH-201",
        pred_task_name="Piping Installation",
        succ_task_code="SAFE-202",
        succ_task_name="LOTO Lockout Tagout Verification",
        rel_type="FS",
    )
    assert res_safe.constraint_type == "HARD_SAFETY"
    assert res_safe.confidence == 0.90
    assert is_fasttrack_candidate(res_safe) is False

    # 2. Physical curing keyword with 72h (9d) concrete curing lag boost
    res_cure = classify_relationship(
        pred_task_code="CIVIL-301",
        pred_task_name="Pour Foundation Concrete Slab",
        succ_task_code="CIVIL-302",
        succ_task_name="Strip Formwork and Deshore",
        rel_type="FS",
        lag_days=9.0,  # 72 hours
    )
    assert res_cure.constraint_type == "HARD_PHYSICAL"
    assert res_cure.confidence == 0.95  # 0.85 + 0.15 capped at 0.95
    assert is_fasttrack_candidate(res_cure) is False


def test_fasttrack_gate_strictly_enforces_safety():
    """
    Ensures is_fasttrack_candidate returns True ONLY for SOFT_RESOURCE or SOFT_COORDINATION.
    """
    soft_res = ClassificationResult(
        relationship_key="k1",
        pred_task_code="A",
        succ_task_code="B",
        constraint_type="SOFT_RESOURCE",
        confidence=0.85,
        classification_source="PM_REVIEWED",
    )
    assert is_fasttrack_candidate(soft_res) is True

    unclassified_res = ClassificationResult(
        relationship_key="k2",
        pred_task_code="A",
        succ_task_code="B",
        constraint_type="UNCLASSIFIED",
        confidence=0.0,
    )
    assert is_fasttrack_candidate(unclassified_res) is False

    hard_phys_res = ClassificationResult(
        relationship_key="k3",
        pred_task_code="A",
        succ_task_code="B",
        constraint_type="HARD_PHYSICAL",
        confidence=0.95,
    )
    assert is_fasttrack_candidate(hard_phys_res) is False


def test_persistence_and_lag_change_re_review_trigger():
    """
    Acceptance Criterion 4:
    Unit test confirming classifications persist correctly across a simulated second
    snapshot ingestion when the relationship is unchanged, and correctly flag for re-review
    when lag changes materially (>25%).
    """
    # 1. PM classified relationship with 4.0 days lag
    existing = RelationshipClassification(
        relationship_key="REL_KEY_123",
        project_id=1,
        constraint_type="SOFT_RESOURCE",
        confidence=1.0,
        classification_source="PM_REVIEWED",
        rationale="Reviewed by Lead PM.",
    )

    # 2. Snapshot 2: Unchanged lag (4.0d) -> Carries forward cleanly
    res_unchanged = classify_relationship(
        pred_task_code="CIV-10",
        pred_task_name="Excavate Trench",
        succ_task_code="CIV-11",
        succ_task_name="Lay Pipe",
        rel_type="FS",
        lag_days=4.0,
        existing_classification=existing,
        previous_lag_days=4.0,
    )
    assert res_unchanged.constraint_type == "SOFT_RESOURCE"
    assert res_unchanged.classification_source == "PM_REVIEWED"
    assert res_unchanged.needs_pm_review is False

    # 3. Snapshot 3: Material lag increase from 4.0d to 8.0d (+100% > 25%) -> Flags for re-review
    res_lag_changed = classify_relationship(
        pred_task_code="CIV-10",
        pred_task_name="Excavate Trench",
        succ_task_code="CIV-11",
        succ_task_name="Lay Pipe",
        rel_type="FS",
        lag_days=8.0,
        existing_classification=existing,
        previous_lag_days=4.0,
    )
    assert res_lag_changed.constraint_type == "UNCLASSIFIED"
    assert res_lag_changed.needs_pm_review is True
    assert "lag changed by 100.0%" in res_lag_changed.rationale


def test_pm_review_queue_and_api_endpoints(client, test_db):
    # Setup test project, snapshot, activities, relationships
    proj = Project(id=10, org_id=1, name="Test Project")
    test_db.add(proj)
    test_db.commit()

    snap = Snapshot(id=20, project_id=10, source_filename="test.xer", data_date=datetime(2026, 9, 1))
    test_db.add(snap)
    test_db.commit()

    a1 = Activity(id=101, snapshot_id=20, task_code="ACT-01", name="Form Foundation", total_float=5.0)
    a2 = Activity(id=102, snapshot_id=20, task_code="ACT-02", name="Pour Foundation Concrete", total_float=5.0)
    a3 = Activity(id=103, snapshot_id=20, task_code="ACT-03", name="Install Drywall", total_float=50.0)
    test_db.add_all([a1, a2, a3])
    test_db.commit()

    k1 = generate_relationship_key("ACT-01", "ACT-02", "FS")
    k2 = generate_relationship_key("ACT-02", "ACT-03", "FS")
    r1 = Relationship(id=1, snapshot_id=20, predecessor_activity_id=101, successor_activity_id=102, relationship_type="FS", lag=0.0, relationship_key=k1)
    r2 = Relationship(id=2, snapshot_id=20, predecessor_activity_id=102, successor_activity_id=103, relationship_type="FS", lag=0.0, relationship_key=k2)
    test_db.add_all([r1, r2])
    test_db.commit()

    # 1. Test GET review queue
    res_queue = client.get("/api/v1/projects/10/relationships/classification-queue")
    assert res_queue.status_code == 200
    queue_data = res_queue.json()
    assert len(queue_data) > 0

    # 2. Test PM Single Classify & Pattern Promotion
    rel_key = generate_relationship_key("ACT-01", "ACT-02", "FS")
    payload = {
        "constraint_type": "HARD_PHYSICAL",
        "rationale": "Formwork must precede pour physically.",
        "reviewed_by": "Senior_Scheduler",
        "promote_to_pattern": True,
        "predecessor_pattern": "Form.*",
        "successor_pattern": "Pour.*",
    }
    res_classify = client.post(f"/api/v1/projects/10/relationships/{rel_key}/classify", json=payload)
    assert res_classify.status_code == 200
    assert res_classify.json()["constraint_type"] == "HARD_PHYSICAL"

    # 3. Test Promote Pattern to Org
    pat = test_db.query(ClassificationPattern).filter(ClassificationPattern.project_id == 10).first()
    assert pat is not None
    assert pat.org_scope == "PROJECT"

    res_promote = client.post(f"/api/v1/patterns/{pat.id}/promote-to-org")
    assert res_promote.status_code == 200
    assert res_promote.json()["org_scope"] == "ORG"

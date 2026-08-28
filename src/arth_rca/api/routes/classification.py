"""
FastAPI REST routes for Phase 2: Relationship Constraint Classification & PM Review Queue.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

from arth_rca.db.database import get_db
from arth_rca.analytics.classification import (
    classify_relationship,
    ClassificationResult,
    is_fasttrack_candidate,
)
from arth_rca.analytics.classification_config import AUTO_CLASSIFY_THRESHOLD
from arth_rca.db.models import (
    Project,
    Snapshot,
    Activity,
    Relationship,
    RelationshipClassification,
    ClassificationPattern,
    generate_relationship_key,
    utc_now,
)

router = APIRouter(prefix="/api/v1", tags=["Constraint Classification & Review Queue"])


class ClassifyRequest(BaseModel):
    constraint_type: str  # HARD_PHYSICAL | HARD_REGULATORY | HARD_SAFETY | SOFT_RESOURCE | SOFT_COORDINATION
    rationale: Optional[str] = None
    reviewed_by: str = "PM_USER"
    promote_to_pattern: bool = False
    predecessor_pattern: Optional[str] = None
    successor_pattern: Optional[str] = None


class BatchClassifyItem(BaseModel):
    relationship_key: str
    constraint_type: str
    rationale: Optional[str] = None
    reviewed_by: str = "PM_USER"


class BatchClassifyRequest(BaseModel):
    items: List[BatchClassifyItem]


class ClassificationDistribution(BaseModel):
    project_id: int
    total_relationships: int
    hard_physical_count: int
    hard_regulatory_count: int
    hard_safety_count: int
    soft_resource_count: int
    soft_coordination_count: int
    unclassified_count: int
    auto_classified_pct: float
    queue_count: int


@router.get("/projects/{project_id}/relationships/classification-queue", response_model=List[ClassificationResult])
def get_classification_review_queue(
    project_id: int,
    snapshot_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Retrieve unclassified or low-confidence relationships in the PM review queue,
    ordered by Longest-Path proximity first, then confidence.
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    snap = None
    if snapshot_id:
        snap = db.query(Snapshot).filter(Snapshot.id == snapshot_id, Snapshot.project_id == project_id).first()
    else:
        snap = db.query(Snapshot).filter(Snapshot.project_id == project_id).order_by(Snapshot.id.desc()).first()

    if not snap:
        return []

    tasks = {t.id: t for t in db.query(Activity).filter(Activity.snapshot_id == snap.id).all()}
    rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()
    patterns = db.query(ClassificationPattern).filter(
        (ClassificationPattern.project_id == project_id) | (ClassificationPattern.org_scope == "ORG")
    ).all()
    existing_records = {
        r.relationship_key: r for r in db.query(RelationshipClassification).filter(RelationshipClassification.project_id == project_id).all()
    }

    queue: List[ClassificationResult] = []

    for r in rels:
        pred_t = tasks.get(r.predecessor_activity_id)
        succ_t = tasks.get(r.successor_activity_id)
        if not pred_t or not succ_t:
            continue

        rel_key = generate_relationship_key(pred_t.task_code, succ_t.task_code, r.relationship_type or "FS")
        existing = existing_records.get(rel_key)

        res = classify_relationship(
            pred_task_code=pred_t.task_code,
            pred_task_name=pred_t.name or "",
            succ_task_code=succ_t.task_code,
            succ_task_name=succ_t.name or "",
            rel_type=r.relationship_type or "FS",
            lag_days=r.lag,
            patterns=patterns,
            existing_classification=existing,
        )

        if res.needs_pm_review:
            # Longest path distance proximity: tasks with small float or driving path are prioritized
            proximity = int(min(pred_t.total_float or 0.0, succ_t.total_float or 0.0))
            res.longest_path_distance = proximity
            queue.append(res)

    # Order by longest path proximity (smallest total float first), then confidence
    queue.sort(key=lambda x: (x.longest_path_distance if x.longest_path_distance is not None else 9999, -x.confidence))
    return queue[:limit]


@router.get("/relationships/classification-queue", response_model=List[ClassificationResult])
@router.get("/snapshots/{snapshot_id}/classification-queue", response_model=List[ClassificationResult])
def get_snapshot_classification_queue(
    snapshot_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Convenience endpoint resolving project_id directly from snapshot_id or active snapshot."""
    if snapshot_id:
        snap = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    else:
        snap = db.query(Snapshot).order_by(Snapshot.id.desc()).first()

    if not snap:
        return []
    return get_classification_review_queue(project_id=snap.project_id, snapshot_id=snap.id, limit=limit, db=db)


@router.post("/relationships/{relationship_key}/classify", response_model=ClassificationResult)
def submit_classification_direct(
    relationship_key: str,
    req: ClassifyRequest,
    db: Session = Depends(get_db),
):
    """Direct classification submission without requiring explicit project_id in route path."""
    snap = db.query(Snapshot).order_by(Snapshot.id.desc()).first()
    proj_id = snap.project_id if snap else 1
    return submit_classification(project_id=proj_id, relationship_key=relationship_key, req=req, db=db)


@router.post("/projects/{project_id}/relationships/{relationship_key}/classify", response_model=ClassificationResult)
def submit_classification(
    project_id: int,
    relationship_key: str,
    req: ClassifyRequest,
    db: Session = Depends(get_db),
):
    """
    PM classification submission for a specific relationship key.
    Records review metadata and optionally promotes to a reusable project-scoped pattern.
    """
    valid_types = {"HARD_PHYSICAL", "HARD_REGULATORY", "HARD_SAFETY", "SOFT_RESOURCE", "SOFT_COORDINATION"}
    if req.constraint_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid constraint_type: {req.constraint_type}")

    record = db.query(RelationshipClassification).filter(
        RelationshipClassification.project_id == project_id,
        RelationshipClassification.relationship_key == relationship_key,
    ).first()

    # Track pattern overrides if PM disagrees with a matched pattern
    if record and record.library_pattern_id:
        if record.constraint_type != req.constraint_type:
            pat = db.query(ClassificationPattern).filter(ClassificationPattern.id == record.library_pattern_id).first()
            if pat:
                pat.times_overridden += 1
                db.add(pat)

    if not record:
        record = RelationshipClassification(
            relationship_key=relationship_key,
            project_id=project_id,
            constraint_type=req.constraint_type,
            confidence=1.0,
            classification_source="PM_REVIEWED",
            rationale=req.rationale or "Classified by PM review.",
            reviewed_by=req.reviewed_by,
            reviewed_at=utc_now(),
        )
        db.add(record)
    else:
        record.constraint_type = req.constraint_type
        record.confidence = 1.0
        record.classification_source = "PM_REVIEWED"
        record.rationale = req.rationale or "Updated by PM review."
        record.reviewed_by = req.reviewed_by
        record.reviewed_at = utc_now()

    # Promote to project pattern if requested
    if req.promote_to_pattern and req.predecessor_pattern and req.successor_pattern:
        new_pat = ClassificationPattern(
            project_id=project_id,
            match_type="NAME_PAIR_REGEX",
            predecessor_pattern=req.predecessor_pattern,
            successor_pattern=req.successor_pattern,
            constraint_type=req.constraint_type,
            source="PM_CONFIRMED",
            org_scope="PROJECT",
            times_matched=1,
            times_overridden=0,
        )
        db.add(new_pat)

    db.commit()
    db.refresh(record)

    return ClassificationResult(
        relationship_key=relationship_key,
        pred_task_code="",
        succ_task_code="",
        relationship_type="FS",
        lag_days=0.0,
        constraint_type=record.constraint_type,
        confidence=record.confidence,
        classification_source=record.classification_source,
        rationale=record.rationale or "",
        is_auto_classified=True,
        needs_pm_review=False,
    )


@router.post("/projects/{project_id}/relationships/batch-classify")
def batch_classify_relationships(
    project_id: int,
    req: BatchClassifyRequest,
    db: Session = Depends(get_db),
):
    """Batch classify multiple relationships in a single atomic transaction."""
    valid_types = {"HARD_PHYSICAL", "HARD_REGULATORY", "HARD_SAFETY", "SOFT_RESOURCE", "SOFT_COORDINATION"}
    updated = 0
    for item in req.items:
        if item.constraint_type not in valid_types:
            continue
        rec = db.query(RelationshipClassification).filter(
            RelationshipClassification.project_id == project_id,
            RelationshipClassification.relationship_key == item.relationship_key,
        ).first()

        if not rec:
            rec = RelationshipClassification(
                relationship_key=item.relationship_key,
                project_id=project_id,
                constraint_type=item.constraint_type,
                confidence=1.0,
                classification_source="PM_REVIEWED",
                rationale=item.rationale or "Batch reviewed by PM.",
                reviewed_by=item.reviewed_by,
                reviewed_at=utc_now(),
            )
            db.add(rec)
        else:
            rec.constraint_type = item.constraint_type
            rec.confidence = 1.0
            rec.classification_source = "PM_REVIEWED"
            rec.rationale = item.rationale or "Batch updated by PM."
            rec.reviewed_by = item.reviewed_by
            rec.reviewed_at = utc_now()
        updated += 1

    db.commit()
    return {"status": "success", "updated_count": updated}


@router.post("/patterns/{pattern_id}/promote-to-org")
def promote_pattern_to_org(pattern_id: int, db: Session = Depends(get_db)):
    """Explicit action promoting a pattern from PROJECT scope to ORG-wide scope."""
    pat = db.query(ClassificationPattern).filter(ClassificationPattern.id == pattern_id).first()
    if not pat:
        raise HTTPException(status_code=404, detail="Pattern not found")

    pat.org_scope = "ORG"
    db.commit()
    db.refresh(pat)
    return {"status": "promoted", "pattern_id": pat.id, "org_scope": pat.org_scope}

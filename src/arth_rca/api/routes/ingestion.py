"""
Snapshot Ingestion API Router.
Handles multipart XER file uploads, filesystem path ingestions, integrity validation,
and automated initial CPM/DCMA baseline computation upon loading new snapshots.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session
from pydantic import BaseModel, Field

from arth_rca.db.database import get_db
from arth_rca.ingestion.pipeline import IngestionPipeline
from arth_rca.db.models import Snapshot, Project, Activity, Relationship, CalendarModel
from arth_rca.parser.validator import ValidationResult

router = APIRouter(prefix="/api/v1/snapshots", tags=["Ingestion & Snapshot Management"])


class IngestionPathRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or relative path to the .xer file")
    org_name: str = Field(default="Default Org", description="Organization name")
    project_name: Optional[str] = Field(default=None, description="Optional override for project name")
    is_baseline: bool = Field(default=False, description="Flag indicating if this snapshot is a baseline reference")
    strict_validation: bool = Field(default=True, description="Enforce strict schema and relational integrity checks")


class IngestionSummaryResponse(BaseModel):
    snapshot_id: int
    project_id: int
    project_name: str
    data_date: str
    source_filename: str
    is_baseline: bool
    activity_count: int
    relationship_count: int
    calendar_count: int
    is_valid: bool
    validation_errors_count: int
    validation_warnings_count: int
    message: str


class SnapshotListItem(BaseModel):
    snapshot_id: int
    project_id: int
    project_name: str
    data_date: str
    source_filename: str
    is_baseline: bool
    activity_count: int
    relationship_count: int
    created_at: str


@router.post("/upload", response_model=IngestionSummaryResponse)
async def upload_and_ingest_snapshot(
    file: UploadFile = File(..., description="Oracle Primavera P6 .xer file"),
    org_name: str = Form(default="Default Org"),
    project_name: Optional[str] = Form(default=None),
    is_baseline: bool = Form(default=False),
    strict_validation: bool = Form(default=False),
    db: Session = Depends(get_db),
):
    """
    Upload and ingest an Oracle Primavera P6 .xer file.
    Parses tables, validates relational integrity, loads into immutable relational tables,
    and returns a summary of the new snapshot.
    """
    if not file.filename.lower().endswith(".xer"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.filename}'. Only Oracle Primavera P6 (.xer) files are accepted.",
        )

    # Save to temp file
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        pipeline = IngestionPipeline(db)
        snapshot, val_res = pipeline.ingest_xer_file(
            file_path=tmp_path,
            org_name=org_name,
            project_name=project_name,
            is_baseline=is_baseline,
            strict_validation=strict_validation,
        )

        proj = db.query(Project).filter(Project.id == snapshot.project_id).first()
        proj_name = proj.name if proj else f"Project#{snapshot.project_id}"
        act_cnt = db.query(Activity).filter(Activity.snapshot_id == snapshot.id).count()
        rel_cnt = db.query(Relationship).filter(Relationship.snapshot_id == snapshot.id).count()
        cal_cnt = db.query(CalendarModel).filter(CalendarModel.project_id == snapshot.project_id).count()

        return IngestionSummaryResponse(
            snapshot_id=snapshot.id,
            project_id=snapshot.project_id,
            project_name=proj_name,
            data_date=snapshot.data_date.strftime("%Y-%m-%d"),
            source_filename=file.filename,
            is_baseline=snapshot.is_baseline,
            activity_count=act_cnt,
            relationship_count=rel_cnt,
            calendar_count=cal_cnt,
            is_valid=val_res.is_valid,
            validation_errors_count=len(val_res.errors),
            validation_warnings_count=len(val_res.warnings),
            message="Snapshot successfully ingested and verified.",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        if tmp_path.exists():
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@router.post("/ingest_path", response_model=IngestionSummaryResponse)
def ingest_snapshot_from_path(
    request: IngestionPathRequest,
    db: Session = Depends(get_db),
):
    """
    Ingests a schedule snapshot directly from a server-side filesystem path.
    """
    path = Path(request.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"XER file not found at path: '{request.file_path}'",
        )

    try:
        pipeline = IngestionPipeline(db)
        snapshot, val_res = pipeline.ingest_xer_file(
            file_path=path,
            org_name=request.org_name,
            project_name=request.project_name,
            is_baseline=request.is_baseline,
            strict_validation=request.strict_validation,
        )

        proj = db.query(Project).filter(Project.id == snapshot.project_id).first()
        proj_name = proj.name if proj else f"Project#{snapshot.project_id}"
        act_cnt = db.query(Activity).filter(Activity.snapshot_id == snapshot.id).count()
        rel_cnt = db.query(Relationship).filter(Relationship.snapshot_id == snapshot.id).count()
        cal_cnt = db.query(CalendarModel).filter(CalendarModel.project_id == snapshot.project_id).count()

        return IngestionSummaryResponse(
            snapshot_id=snapshot.id,
            project_id=snapshot.project_id,
            project_name=proj_name,
            data_date=snapshot.data_date.strftime("%Y-%m-%d"),
            source_filename=path.name,
            is_baseline=snapshot.is_baseline,
            activity_count=act_cnt,
            relationship_count=rel_cnt,
            calendar_count=cal_cnt,
            is_valid=val_res.is_valid,
            validation_errors_count=len(val_res.errors),
            validation_warnings_count=len(val_res.warnings),
            message="Snapshot successfully ingested and verified.",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get("", response_model=List[SnapshotListItem])
def list_snapshots(db: Session = Depends(get_db)):
    """
    Returns all historical schedule snapshots stored in the system.
    """
    snaps = db.query(Snapshot).order_by(Snapshot.data_date.asc()).all()
    results = []
    for s in snaps:
        proj = db.query(Project).filter(Project.id == s.project_id).first()
        proj_name = proj.name if proj else f"Project#{s.project_id}"
        act_cnt = db.query(Activity).filter(Activity.snapshot_id == s.id).count()
        rel_cnt = db.query(Relationship).filter(Relationship.snapshot_id == s.id).count()
        results.append(
            SnapshotListItem(
                snapshot_id=s.id,
                project_id=s.project_id,
                project_name=proj_name,
                data_date=s.data_date.strftime("%Y-%m-%d"),
                source_filename=s.source_filename,
                is_baseline=s.is_baseline,
                activity_count=act_cnt,
                relationship_count=rel_cnt,
                created_at=s.imported_at.strftime("%Y-%m-%d %H:%M:%S") if s.imported_at else "",
            )
        )
    return results


@router.delete("/{snapshot_id}")
def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """
    Deletes an uploaded snapshot and all its associated activities, relationships,
    DCMA health checks, and driver records.
    Useful when a schedule was uploaded in the wrong sequence or contains erroneous data.
    """
    snap = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot with ID {snapshot_id} not found.")

    try:
        # 1. Fetch activity IDs for this snapshot
        activities = db.query(Activity).filter(Activity.snapshot_id == snapshot_id).all()
        act_ids = [a.id for a in activities if a.id is not None]

        # 2. Delete ActivityResource records
        if act_ids:
            from arth_rca.db.models import ActivityResource
            db.query(ActivityResource).filter(ActivityResource.activity_id.in_(act_ids)).delete(synchronize_session=False)

        # 3. Delete Relationships
        db.query(Relationship).filter(Relationship.snapshot_id == snapshot_id).delete(synchronize_session=False)

        # 4. Delete Activities
        db.query(Activity).filter(Activity.snapshot_id == snapshot_id).delete(synchronize_session=False)

        # 5. Delete DCMAHealthChecks
        from arth_rca.db.models import DCMAHealthCheck
        db.query(DCMAHealthCheck).filter(DCMAHealthCheck.snapshot_id == snapshot_id).delete(synchronize_session=False)

        # 6. Delete DriverRecords
        from arth_rca.db.models import DriverRecord
        db.query(DriverRecord).filter(DriverRecord.snapshot_id == snapshot_id).delete(synchronize_session=False)

        # 7. Delete Snapshot
        db.delete(snap)
        db.commit()

        return {
            "success": True,
            "message": f"Snapshot #{snapshot_id} ('{snap.source_filename}') and all associated records deleted successfully.",
            "deleted_snapshot_id": snapshot_id,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete snapshot #{snapshot_id}: {str(e)}")


@router.patch("/{snapshot_id}/baseline")
def set_snapshot_baseline(
    snapshot_id: int,
    is_baseline: bool,
    db: Session = Depends(get_db),
):
    """
    Updates the baseline status of a snapshot.
    """
    snap = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot with ID {snapshot_id} not found.")

    try:
        # If marking this snapshot as baseline, optionally unmark others for the same project
        if is_baseline:
            db.query(Snapshot).filter(
                Snapshot.project_id == snap.project_id,
                Snapshot.id != snapshot_id,
            ).update({"is_baseline": False})

        snap.is_baseline = is_baseline
        db.add(snap)
        db.commit()
        db.refresh(snap)

        return {
            "success": True,
            "snapshot_id": snap.id,
            "is_baseline": snap.is_baseline,
            "message": f"Snapshot #{snapshot_id} baseline status updated to {is_baseline}.",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update baseline status: {str(e)}")

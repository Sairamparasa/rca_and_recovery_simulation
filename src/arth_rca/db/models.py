"""
PostgreSQL relational data models implementing Section 2.1 of Complete_Implementation_Plan.md.
Uses SQLModel (SQLAlchemy 2.0 + Pydantic v2).
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
import hashlib
from sqlmodel import SQLModel, Field, Relationship as SQLRelationship
from sqlalchemy import Column, JSON, Text, Index


def utc_now() -> datetime:
    """Return timezone-naive UTC datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_relationship_key(pred_code: str, succ_code: str, rel_type: str) -> str:
    """
    Generate stable relationship hash key: hash(predecessor_task_code, successor_task_code, relationship_type)
    Used to carry classifications and change tracking across immutable snapshots.
    """
    raw_str = f"{pred_code.strip()}|{succ_code.strip()}|{rel_type.strip()}".upper()
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:32]


# -----------------------------------------------------------------------------
# 1. Organization & Project Hierarchy
# -----------------------------------------------------------------------------

class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)

    projects: List["Project"] = SQLRelationship(back_populates="organization")


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organizations.id", index=True)
    name: str = Field(index=True)
    p6_project_id: Optional[str] = Field(default=None, index=True)
    calendar_default_id: Optional[int] = None
    created_at: datetime = Field(default_factory=utc_now)

    organization: Optional[Organization] = SQLRelationship(back_populates="projects")
    snapshots: List["Snapshot"] = SQLRelationship(back_populates="project")
    calendars: List["CalendarModel"] = SQLRelationship(back_populates="project")


# -----------------------------------------------------------------------------
# 2. Immutable Snapshot Store
# -----------------------------------------------------------------------------

class Snapshot(SQLModel, table=True):
    __tablename__ = "snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    imported_at: datetime = Field(default_factory=utc_now, index=True)
    source_filename: str
    data_date: datetime = Field(index=True)
    is_baseline: bool = Field(default=False, index=True)
    baseline_revision_reason: Optional[str] = None
    raw_file_ref: Optional[str] = None

    project: Optional[Project] = SQLRelationship(back_populates="snapshots")
    activities: List["Activity"] = SQLRelationship(back_populates="snapshot")
    relationships: List["Relationship"] = SQLRelationship(back_populates="snapshot")
    health_checks: List["DCMAHealthCheck"] = SQLRelationship(back_populates="snapshot")
    driver_records: List["DriverRecord"] = SQLRelationship(back_populates="snapshot")


# -----------------------------------------------------------------------------
# 3. Calendars, Activities & Relationships
# -----------------------------------------------------------------------------

class CalendarModel(SQLModel, table=True):
    __tablename__ = "calendars"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    p6_clndr_id: Optional[int] = None
    name: str
    is_default: bool = Field(default=False)
    working_days_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    exceptions_json: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)

    project: Optional[Project] = SQLRelationship(back_populates="calendars")


class Activity(SQLModel, table=True):
    __tablename__ = "activities"
    __table_args__ = (
        Index("idx_snapshot_task_code", "snapshot_id", "task_code"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="snapshots.id", index=True)
    p6_task_id: Optional[int] = None
    task_code: str = Field(index=True)
    name: str
    wbs_path: Optional[str] = None
    calendar_id: Optional[int] = None
    
    # Durations
    original_duration: float = 0.0
    remaining_duration: float = 0.0
    percent_complete: float = 0.0
    status: str = "NOT_STARTED"
    
    # Dates
    early_start: Optional[datetime] = None
    early_finish: Optional[datetime] = None
    late_start: Optional[datetime] = None
    late_finish: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_finish: Optional[datetime] = None
    
    # Float & Logic
    total_float: float = 0.0
    free_float: float = 0.0
    is_driving_path: bool = False
    
    # Constraints
    constraint_type: Optional[str] = None
    constraint_date: Optional[datetime] = None
    is_milestone: bool = False

    snapshot: Optional[Snapshot] = SQLRelationship(back_populates="activities")
    resource_assignments: List["ActivityResource"] = SQLRelationship(back_populates="activity")


class Relationship(SQLModel, table=True):
    __tablename__ = "relationships"
    __table_args__ = (
        Index("idx_snapshot_rel_key", "snapshot_id", "relationship_key"),
        Index("idx_pred_succ", "predecessor_activity_id", "successor_activity_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="snapshots.id", index=True)
    predecessor_activity_id: int = Field(foreign_key="activities.id", index=True)
    successor_activity_id: int = Field(foreign_key="activities.id", index=True)
    relationship_type: str = "FS"
    lag: float = 0.0
    is_driving: bool = Field(default=False, index=True)
    relationship_key: str = Field(index=True)

    snapshot: Optional[Snapshot] = SQLRelationship(back_populates="relationships")


# -----------------------------------------------------------------------------
# 4. Resources & Activity Resource Assignments
# -----------------------------------------------------------------------------

class Resource(SQLModel, table=True):
    __tablename__ = "resources"

    id: Optional[int] = Field(default=None, primary_key=True)
    p6_rsrc_id: Optional[int] = None
    name: str
    short_name: str
    resource_type: str = "LABOR"
    unit_of_measure: Optional[str] = None

    assignments: List["ActivityResource"] = SQLRelationship(back_populates="resource")


class ActivityResource(SQLModel, table=True):
    __tablename__ = "activity_resources"

    id: Optional[int] = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activities.id", index=True)
    resource_id: int = Field(foreign_key="resources.id", index=True)
    budgeted_units: float = 0.0
    remaining_units: float = 0.0
    actual_units: float = 0.0
    budgeted_cost: float = 0.0
    actual_cost: float = 0.0

    activity: Optional[Activity] = SQLRelationship(back_populates="resource_assignments")
    resource: Optional[Resource] = SQLRelationship(back_populates="assignments")


# -----------------------------------------------------------------------------
# 5. DCMA 14-Point Health Check Records
# -----------------------------------------------------------------------------

class DCMAHealthCheck(SQLModel, table=True):
    __tablename__ = "dcma_health_checks"

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="snapshots.id", index=True)
    missing_logic_pct: float = 0.0
    negative_float_pct: float = 0.0
    high_float_outlier_pct: float = 0.0
    hard_constraint_count: int = 0
    negative_lag_count: int = 0
    critical_path_length_index: float = 0.0
    invalid_date_count: int = 0
    score_summary_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    computed_at: datetime = Field(default_factory=utc_now)

    snapshot: Optional[Snapshot] = SQLRelationship(back_populates="health_checks")


# -----------------------------------------------------------------------------
# 6. Schemas for Later Phases
# -----------------------------------------------------------------------------

class DriverRecord(SQLModel, table=True):
    __tablename__ = "driver_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="snapshots.id", index=True)
    head_activity_id: int = Field(foreign_key="activities.id", index=True)
    root_cause_type: str = "unresolved"
    float_days: float = 0.0
    downstream_activity_count: int = 0
    impact_score: float = 0.0
    milestones_blocked_json: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)

    snapshot: Optional[Snapshot] = SQLRelationship(back_populates="driver_records")
    chains: List["DrivingChain"] = SQLRelationship(back_populates="driver_record")


class DrivingChain(SQLModel, table=True):
    __tablename__ = "driving_chains"

    id: Optional[int] = Field(default=None, primary_key=True)
    driver_record_id: int = Field(foreign_key="driver_records.id", index=True)
    activity_id: int = Field(foreign_key="activities.id", index=True)
    parent_activity_id: Optional[int] = Field(default=None, foreign_key="activities.id", index=True)
    direction: str = "backward_root_trace"
    relationship_type: str = "FS"
    lag: float = 0.0
    is_convergence_node: bool = False

    driver_record: Optional[DriverRecord] = SQLRelationship(back_populates="chains")


class RelationshipClassification(SQLModel, table=True):
    __tablename__ = "relationship_classifications"

    id: Optional[int] = Field(default=None, primary_key=True)
    relationship_key: str = Field(index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    constraint_type: str = "UNCLASSIFIED"
    confidence: float = 0.0
    classification_source: str = "HEURISTIC_KEYWORD"
    rationale: Optional[str] = Field(default=None, sa_column=Column(Text))
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    library_pattern_id: Optional[int] = None


class ClassificationPattern(SQLModel, table=True):
    __tablename__ = "classification_patterns"

    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: Optional[int] = Field(default=None, foreign_key="organizations.id", index=True)
    project_id: Optional[int] = Field(default=None, foreign_key="projects.id", index=True)
    match_type: str = "NAME_PAIR_REGEX"
    predecessor_pattern: str
    successor_pattern: str
    constraint_type: str
    min_lag_hrs: Optional[float] = None
    source: str = "SEEDED"
    times_matched: int = 0
    times_overridden: int = 0
    org_scope: str = "PROJECT"


class Scenario(SQLModel, table=True):
    __tablename__ = "scenarios"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    baseline_snapshot_id: int = Field(foreign_key="snapshots.id", index=True)
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    levers_applied_json: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "proposed"
    result_finish_date: Optional[datetime] = None
    result_float_summary_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result_cost_delta: float = 0.0
    engine_version: str = "1.0.0"


class EvidenceLedgerEntry(SQLModel, table=True):
    __tablename__ = "evidence_ledger"

    id: Optional[int] = Field(default=None, primary_key=True)
    driver_record_id: Optional[int] = Field(default=None, foreign_key="driver_records.id", index=True)
    scenario_id: Optional[int] = Field(default=None, foreign_key="scenarios.id", index=True)
    claim_text: str = Field(sa_column=Column(Text))
    certainty_tier: str = "FACT"
    source_ref: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

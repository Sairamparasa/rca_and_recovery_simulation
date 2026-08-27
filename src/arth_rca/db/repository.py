"""
Database repository for persisting and loading immutable schedule snapshots.
"""

from datetime import datetime
from typing import Optional, List, Dict
from sqlmodel import Session, select

from arth_rca.db.models import (
    Organization,
    Project,
    Snapshot,
    Activity,
    Relationship,
    CalendarModel,
    Resource,
    ActivityResource,
    DCMAHealthCheck,
    generate_relationship_key,
)
from arth_rca.parser.xer_models import XERParsedFile


class SnapshotRepository:
    """Handles database persistence for immutable schedule snapshots."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_organization(self, name: str = "Default Org") -> Organization:
        """Get or create the root Organization record."""
        stmt = select(Organization).where(Organization.name == name)
        org = self.session.exec(stmt).first()
        if not org:
            org = Organization(name=name)
            self.session.add(org)
            self.session.commit()
            self.session.refresh(org)
        return org

    def get_or_create_project(
        self,
        org_id: int,
        name: str,
        p6_project_id: Optional[str] = None,
    ) -> Project:
        """Get or create a Project record."""
        stmt = select(Project).where(
            Project.org_id == org_id,
            Project.name == name,
        )
        proj = self.session.exec(stmt).first()
        if not proj:
            proj = Project(
                org_id=org_id,
                name=name,
                p6_project_id=p6_project_id,
            )
            self.session.add(proj)
            self.session.commit()
            self.session.refresh(proj)
        return proj

    def create_snapshot_from_xer(
        self,
        project_id: int,
        parsed_xer: XERParsedFile,
        source_filename: str,
        data_date: Optional[datetime] = None,
        is_baseline: bool = False,
        raw_file_ref: Optional[str] = None,
    ) -> Snapshot:
        """
        Persist an entire parsed XER dataset into the database as a new immutable Snapshot.
        Maintains relational mapping and generates stable relationship keys.
        """
        # Determine data date from project record if not provided
        if not data_date:
            for p in parsed_xer.projects.values():
                data_date = p.last_recalc_date or p.plan_start_date
                break
        if not data_date:
            data_date = datetime.utcnow()

        snapshot = Snapshot(
            project_id=project_id,
            source_filename=source_filename,
            data_date=data_date,
            is_baseline=is_baseline,
            raw_file_ref=raw_file_ref,
        )
        self.session.add(snapshot)
        self.session.flush()  # Populates snapshot.id

        # 1. Calendars
        clndr_map: Dict[int, int] = {}  # p6_clndr_id -> db_id
        for clndr in parsed_xer.calendars.values():
            db_clndr = CalendarModel(
                project_id=project_id,
                p6_clndr_id=clndr.clndr_id,
                name=clndr.clndr_name,
                is_default=clndr.default_flag,
                working_days_json={"day_hr_cnt": clndr.day_hr_cnt, "week_hr_cnt": clndr.week_hr_cnt},
                exceptions_json=[],
            )
            self.session.add(db_clndr)
            self.session.flush()
            clndr_map[clndr.clndr_id] = db_clndr.id

        # 2. Activities
        task_id_to_activity_id: Dict[int, int] = {}  # p6_task_id -> db_activity_id
        task_code_map: Dict[int, str] = {}           # p6_task_id -> task_code

        for task in parsed_xer.tasks.values():
            wbs_path = ""
            if task.wbs_id and task.wbs_id in parsed_xer.wbs:
                wbs_path = parsed_xer.wbs[task.wbs_id].wbs_name

            status_map = {
                "TK_NotStart": "NOT_STARTED",
                "TK_Active": "IN_PROGRESS",
                "TK_Complete": "COMPLETED",
            }
            status = status_map.get(task.status_code, "NOT_STARTED")

            act = Activity(
                snapshot_id=snapshot.id,
                p6_task_id=task.task_id,
                task_code=task.task_code,
                name=task.task_name,
                wbs_path=wbs_path,
                calendar_id=clndr_map.get(task.clndr_id),
                original_duration=task.target_durn_hr_cnt / 8.0,
                remaining_duration=task.remain_durn_hr_cnt / 8.0,
                percent_complete=task.phys_complete_pct,
                status=status,
                early_start=task.early_start_date,
                early_finish=task.early_end_date,
                late_start=task.late_start_date,
                late_finish=task.late_end_date,
                actual_start=task.act_start_date,
                actual_finish=task.act_end_date,
                total_float=task.total_float_hr_cnt / 8.0,
                free_float=task.free_float_hr_cnt / 8.0,
                is_driving_path=task.driving_path_flag,
                constraint_type=task.cstr_type,
                constraint_date=task.cstr_date,
                is_milestone="Mile" in task.task_type,
            )
            self.session.add(act)
            self.session.flush()
            task_id_to_activity_id[task.task_id] = act.id
            task_code_map[task.task_id] = task.task_code

        # 3. Relationships
        for pred in parsed_xer.predecessors:
            pred_act_id = task_id_to_activity_id.get(pred.pred_task_id)
            succ_act_id = task_id_to_activity_id.get(pred.task_id)
            if not pred_act_id or not succ_act_id:
                continue

            rel_type_map = {
                "PR_FS": "FS",
                "PR_SS": "SS",
                "PR_FF": "FF",
                "PR_SF": "SF",
            }
            rel_type = rel_type_map.get(pred.pred_type, "FS")

            pred_code = task_code_map.get(pred.pred_task_id, "")
            succ_code = task_code_map.get(pred.task_id, "")
            rel_key = generate_relationship_key(pred_code, succ_code, rel_type)

            rel = Relationship(
                snapshot_id=snapshot.id,
                predecessor_activity_id=pred_act_id,
                successor_activity_id=succ_act_id,
                relationship_type=rel_type,
                lag=pred.lag_hr_cnt / 8.0,
                is_driving=False,  # Computed by CPM engine
                relationship_key=rel_key,
            )
            self.session.add(rel)

        # 4. Resources
        rsrc_map: Dict[int, int] = {}
        for rsrc in parsed_xer.resources.values():
            r = Resource(
                p6_rsrc_id=rsrc.rsrc_id,
                name=rsrc.rsrc_name,
                short_name=rsrc.rsrc_short_name,
                resource_type="LABOR" if "Labor" in rsrc.rsrc_type else "NON_LABOR",
                unit_of_measure=rsrc.unit_of_measure,
            )
            self.session.add(r)
            self.session.flush()
            rsrc_map[rsrc.rsrc_id] = r.id

        # 5. Task Resources
        for tr in parsed_xer.task_resources:
            act_id = task_id_to_activity_id.get(tr.task_id)
            r_id = rsrc_map.get(tr.rsrc_id)
            if act_id and r_id:
                assignment = ActivityResource(
                    activity_id=act_id,
                    resource_id=r_id,
                    budgeted_units=tr.target_qty,
                    remaining_units=tr.remain_qty,
                    actual_units=tr.act_qty,
                    budgeted_cost=tr.target_cost,
                    actual_cost=tr.act_cost,
                )
                self.session.add(assignment)

        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

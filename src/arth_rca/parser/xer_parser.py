"""
High-performance parser for Primavera P6 XER export files.
Handles tab-delimited %T, %F, %R, %E blocks and builds structured models.
"""

from typing import Dict, List, Optional, Union, TextIO
import io
from pathlib import Path

from arth_rca.parser.xer_models import (
    XERParsedFile,
    XERProject,
    XERCalendar,
    XERWBS,
    XERTask,
    XERPredecessor,
    XERResource,
    XERTaskResource,
    parse_p6_date,
    parse_float,
    parse_int,
    parse_bool,
)


class XERParserError(Exception):
    """Raised when an XER file is malformed, corrupt, or unparseable."""
    pass


class XERParser:
    """Parses Primavera P6 XER files into typed in-memory structures."""

    def __init__(self):
        pass

    def parse_file(self, file_path: Union[str, Path]) -> XERParsedFile:
        """Parse XER from a file path with encoding auto-detection."""
        path = Path(file_path)
        if not path.exists():
            raise XERParserError(f"XER file not found: {file_path}")

        # Try utf-8 first, fallback to windows-1252 / latin-1
        for encoding in ["utf-8", "cp1252", "latin-1"]:
            try:
                with open(path, "r", encoding=encoding) as f:
                    return self.parse_stream(f)
            except UnicodeDecodeError:
                continue
            except XERParserError:
                raise
            except Exception as e:
                raise XERParserError(f"Failed to parse XER file {file_path}: {e}") from e

        raise XERParserError(f"Could not decode XER file {file_path} with supported encodings.")

    def parse_content(self, text_content: str) -> XERParsedFile:
        """Parse XER from raw string content."""
        return self.parse_stream(io.StringIO(text_content))

    def parse_stream(self, stream: TextIO) -> XERParsedFile:
        """Parse XER tokens from an open text stream."""
        lines = stream.readlines()
        if not lines:
            raise XERParserError("Empty XER content")

        header = lines[0].strip()
        if not header.startswith("ERMHDR"):
            raise XERParserError(f"Invalid XER header: '{header[:30]}...'. Expected 'ERMHDR'")

        raw_tables: Dict[str, List[Dict[str, str]]] = {}
        current_table: Optional[str] = None
        current_fields: List[str] = []

        for line_num, line in enumerate(lines[1:], start=2):
            line = line.rstrip("\r\n")
            if not line:
                continue

            parts = line.split("\t")
            tag = parts[0].strip()

            if tag == "%T":
                if len(parts) < 2 or not parts[1].strip():
                    raise XERParserError(f"Line {line_num}: Malformed %T tag without table name")
                current_table = parts[1].strip().upper()
                current_fields = []
                if current_table not in raw_tables:
                    raw_tables[current_table] = []

            elif tag == "%F":
                if not current_table:
                    raise XERParserError(f"Line {line_num}: %F tag encountered before %T table declaration")
                current_fields = [f.strip() for f in parts[1:]]

            elif tag == "%R":
                if not current_table:
                    raise XERParserError(f"Line {line_num}: %R record encountered before %T table declaration")
                if not current_fields:
                    raise XERParserError(f"Line {line_num}: %R record encountered before %F field headers")

                values = parts[1:]
                # Pad values if line had trailing empty tabs
                if len(values) < len(current_fields):
                    values.extend([""] * (len(current_fields) - len(values)))
                elif len(values) > len(current_fields):
                    values = values[: len(current_fields)]

                record = dict(zip(current_fields, values))
                raw_tables[current_table].append(record)

            elif tag == "%E":
                # End of export marker
                break

        parsed = XERParsedFile(header=header, raw_tables=raw_tables)
        self._populate_typed_models(parsed)
        return parsed

    def _populate_typed_models(self, parsed: XERParsedFile) -> None:
        """Convert raw dictionary tables into typed domain models."""
        # 1. Projects
        for row in parsed.raw_tables.get("PROJECT", []):
            proj_id = parse_int(row.get("proj_id"))
            if not proj_id:
                continue
            
            # Map P6 sched_options or individual columns
            f_calc_mode_raw = row.get("f_calc_mode", row.get("float_calc_mode", "CS_Start")).upper()
            if "FINISH" in f_calc_mode_raw or "CS_FINISH" in f_calc_mode_raw:
                f_calc_mode = "FINISH_DATES"
            elif "MIN" in f_calc_mode_raw or "CS_MIN" in f_calc_mode_raw:
                f_calc_mode = "MIN_START_FINISH"
            else:
                f_calc_mode = "START_DATES"

            oos_mode_raw = row.get("oos_mode", "RL").upper()
            if oos_mode_raw in ("PO", "PROGRESS_OVERRIDE"):
                oos_mode = "PROGRESS_OVERRIDE"
            elif oos_mode_raw in ("AD", "ACTUAL_DATES"):
                oos_mode = "ACTUAL_DATES"
            else:
                oos_mode = "RETAINED_LOGIC"

            critical_path_raw = row.get("critical_path_type", row.get("critical_type", "TOTAL_FLOAT")).upper()
            critical_path_type = "LONGEST_PATH" if "LONG" in critical_path_raw else "TOTAL_FLOAT"

            parsed.projects[proj_id] = XERProject(
                proj_id=proj_id,
                proj_short_name=row.get("proj_short_name", f"PROJ-{proj_id}"),
                clndr_id=parse_int(row.get("clndr_id")),
                plan_start_date=parse_p6_date(row.get("plan_start_date")),
                plan_end_date=parse_p6_date(row.get("plan_end_date")),
                must_finish_by_date=parse_p6_date(row.get("must_finish_by_date") or row.get("target_end_date")),
                last_recalc_date=parse_p6_date(row.get("last_recalc_date") or row.get("scd_end_date")),
                f_calc_mode=f_calc_mode,
                oos_mode=oos_mode,
                critical_path_type=critical_path_type,
                critical_float_hr_cnt=parse_float(row.get("critical_float_hr_cnt", "0.0")),
                use_expect_end_flag=parse_bool(row.get("use_expect_end_flag")),
                raw_fields=row,
            )

        # 2. Calendars
        for row in parsed.raw_tables.get("CALENDAR", []):
            clndr_id = parse_int(row.get("clndr_id"))
            if not clndr_id:
                continue
            parsed.calendars[clndr_id] = XERCalendar(
                clndr_id=clndr_id,
                clndr_name=row.get("clndr_name", f"Calendar-{clndr_id}"),
                default_flag=parse_bool(row.get("default_flag")),
                clndr_type=row.get("clndr_type", "CA_Base"),
                day_hr_cnt=parse_float(row.get("day_hr_cnt", "8.0")),
                week_hr_cnt=parse_float(row.get("week_hr_cnt", "40.0")),
                month_hr_cnt=parse_float(row.get("month_hr_cnt", "173.33")),
                year_hr_cnt=parse_float(row.get("year_hr_cnt", "2080.0")),
                clndr_data=row.get("clndr_data"),
                raw_fields=row,
            )

        # 3. WBS
        for row in parsed.raw_tables.get("PROJWBS", []):
            wbs_id = parse_int(row.get("wbs_id"))
            if not wbs_id:
                continue
            parsed.wbs[wbs_id] = XERWBS(
                wbs_id=wbs_id,
                proj_id=parse_int(row.get("proj_id")),
                wbs_short_name=row.get("wbs_short_name", ""),
                wbs_name=row.get("wbs_name", ""),
                parent_wbs_id=parse_int(row.get("parent_wbs_id")),
                seq_num=parse_int(row.get("seq_num", "0")),
                raw_fields=row,
            )

        # 4. Tasks (Activities)
        for row in parsed.raw_tables.get("TASK", []):
            task_id = parse_int(row.get("task_id"))
            if not task_id:
                continue
            parsed.tasks[task_id] = XERTask(
                task_id=task_id,
                proj_id=parse_int(row.get("proj_id")),
                wbs_id=parse_int(row.get("wbs_id")),
                clndr_id=parse_int(row.get("clndr_id")),
                task_code=row.get("task_code", f"ACT-{task_id}"),
                task_name=row.get("task_name", ""),
                task_type=row.get("task_type", "TT_Task"),
                status_code=row.get("status_code", "TK_NotStart"),
                target_durn_hr_cnt=parse_float(row.get("target_durn_hr_cnt", "0.0")),
                remain_durn_hr_cnt=parse_float(row.get("remain_durn_hr_cnt", "0.0")),
                act_work_qty=parse_float(row.get("act_work_qty", "0.0")),
                phys_complete_pct=parse_float(row.get("phys_complete_pct", "0.0")),
                target_start_date=parse_p6_date(row.get("target_start_date")),
                target_end_date=parse_p6_date(row.get("target_end_date")),
                early_start_date=parse_p6_date(row.get("early_start_date")),
                early_end_date=parse_p6_date(row.get("early_end_date")),
                late_start_date=parse_p6_date(row.get("late_start_date")),
                late_end_date=parse_p6_date(row.get("late_end_date")),
                act_start_date=parse_p6_date(row.get("act_start_date")),
                act_end_date=parse_p6_date(row.get("act_end_date")),
                restart_date=parse_p6_date(row.get("restart_date")),
                reend_date=parse_p6_date(row.get("reend_date")),
                expect_end_date=parse_p6_date(row.get("expect_end_date")),
                total_float_hr_cnt=parse_float(row.get("total_float_hr_cnt", "0.0")),
                free_float_hr_cnt=parse_float(row.get("free_float_hr_cnt", "0.0")),
                driving_path_flag=parse_bool(row.get("driving_path_flag")),
                cstr_type=row.get("cstr_type"),
                cstr_date=parse_p6_date(row.get("cstr_date")),
                cstr_type2=row.get("cstr_type2"),
                cstr_date2=parse_p6_date(row.get("cstr_date2")),
                raw_fields=row,
            )

        # 5. Predecessors / Relationships
        for row in parsed.raw_tables.get("TASKPRED", []):
            pred_id = parse_int(row.get("task_pred_id"))
            if not pred_id:
                continue
            parsed.predecessors.append(
                XERPredecessor(
                    task_pred_id=pred_id,
                    task_id=parse_int(row.get("task_id")),
                    pred_task_id=parse_int(row.get("pred_task_id")),
                    proj_id=parse_int(row.get("proj_id")),
                    pred_type=row.get("pred_type", "PR_FS"),
                    lag_hr_cnt=parse_float(row.get("lag_hr_cnt", "0.0")),
                    comments=row.get("comments"),
                    raw_fields=row,
                )
            )

        # 6. Resources & Assignments
        for row in parsed.raw_tables.get("RSRC", []):
            rsrc_id = parse_int(row.get("rsrc_id"))
            if not rsrc_id:
                continue
            parsed.resources[rsrc_id] = XERResource(
                rsrc_id=rsrc_id,
                rsrc_short_name=row.get("rsrc_short_name", f"RSRC-{rsrc_id}"),
                rsrc_name=row.get("rsrc_name", ""),
                rsrc_type=row.get("rsrc_type", "RT_Labor"),
                clndr_id=parse_int(row.get("clndr_id")),
                unit_of_measure=row.get("unit_of_measure"),
                raw_fields=row,
            )

        for row in parsed.raw_tables.get("TASKRSRC", []):
            taskrsrc_id = parse_int(row.get("taskrsrc_id"))
            if not taskrsrc_id:
                continue
            parsed.task_resources.append(
                XERTaskResource(
                    taskrsrc_id=taskrsrc_id,
                    task_id=parse_int(row.get("task_id")),
                    proj_id=parse_int(row.get("proj_id")),
                    rsrc_id=parse_int(row.get("rsrc_id")),
                    target_qty=parse_float(row.get("target_qty", "0.0")),
                    target_cost=parse_float(row.get("target_cost", "0.0")),
                    remain_qty=parse_float(row.get("remain_qty", "0.0")),
                    remain_cost=parse_float(row.get("remain_cost", "0.0")),
                    act_qty=parse_float(row.get("act_qty", "0.0")),
                    act_cost=parse_float(row.get("act_cost", "0.0")),
                    raw_fields=row,
                )
            )

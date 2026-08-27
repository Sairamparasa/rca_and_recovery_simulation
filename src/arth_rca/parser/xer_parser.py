"""
High-performance parser for Primavera P6 XER export files powered by PyP6Xer (HassanEmam/PyP6Xer).
Maps raw P6 XER structures into typed immutable domain models.
"""

from typing import Dict, List, Optional, Union, TextIO, Any
from datetime import datetime
import io
import tempfile
from pathlib import Path
from xerparser.reader import Reader

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


def ensure_datetime(val: Any) -> Optional[datetime]:
    """Coerce string or datetime into a datetime object."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return parse_p6_date(val)
    return None


class XERParserError(Exception):
    """Raised when an XER file is malformed, corrupt, or unparseable."""
    pass


class XERParser:
    """Parses Primavera P6 XER files into typed in-memory structures using PyP6Xer."""

    def __init__(self):
        pass

    def parse_file(self, file_path: Union[str, Path]) -> XERParsedFile:
        """Parse XER from a file path using PyP6Xer with robust fallback."""
        path = Path(file_path)
        if not path.exists():
            raise XERParserError(f"XER file not found: {file_path}")

        # Quick header check
        try:
            with open(path, "rb") as f:
                header_line = f.readline().decode("latin-1", errors="ignore").strip()
                if not header_line.startswith("ERMHDR"):
                    raise XERParserError(f"Invalid XER header: '{header_line[:30]}...'. Expected 'ERMHDR'")
        except XERParserError:
            raise
        except Exception as e:
            raise XERParserError(f"Cannot read XER file {file_path}: {e}") from e

        # 1. Try PyP6Xer Reader
        try:
            reader = Reader(str(path))
            return self._convert_reader_to_domain(reader, header=header_line)
        except Exception:
            # 2. Fallback to direct stream parser
            for enc in ["utf-8", "cp1252", "latin-1"]:
                try:
                    with open(path, "r", encoding=enc) as f:
                        return self.parse_stream(f)
                except UnicodeDecodeError:
                    continue
                except Exception as stream_err:
                    raise XERParserError(f"Failed to parse XER file {file_path}: {stream_err}") from stream_err

        raise XERParserError(f"Could not parse XER file: {file_path}")

    def parse_content(self, text_content: str) -> XERParsedFile:
        """Parse XER from raw string content."""
        if not text_content or not text_content.strip():
            raise XERParserError("Empty XER content")
        if not text_content.strip().startswith("ERMHDR"):
            raise XERParserError("Invalid XER header: Expected 'ERMHDR'")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xer", delete=False, encoding="utf-8") as tmp:
            tmp.write(text_content)
            tmp_path = Path(tmp.name)

        try:
            return self.parse_file(tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def parse_stream(self, stream: TextIO) -> XERParsedFile:
        """Parse XER tokens directly from an open text stream."""
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
                if len(values) < len(current_fields):
                    values.extend([""] * (len(current_fields) - len(values)))
                elif len(values) > len(current_fields):
                    values = values[: len(current_fields)]

                record = dict(zip(current_fields, values))
                raw_tables[current_table].append(record)

            elif tag == "%E":
                break

        parsed = XERParsedFile(header=header, raw_tables=raw_tables)
        self._populate_typed_models_from_tables(parsed)
        return parsed

    def _convert_reader_to_domain(self, reader: Reader, header: str = "ERMHDR") -> XERParsedFile:
        """Convert PyP6Xer Reader object model into our strongly-typed domain model."""
        parsed = XERParsedFile(header=header)

        # 1. Projects
        for p in reader.projects:
            proj_id = parse_int(getattr(p, "proj_id", None) or getattr(p, "id", None))
            if not proj_id:
                continue
            
            cp_raw = str(getattr(p, "critical_path_type", "TOTAL_FLOAT")).upper()
            critical_path_type = "LONGEST_PATH" if "LONG" in cp_raw else "TOTAL_FLOAT"

            parsed.projects[proj_id] = XERProject(
                proj_id=proj_id,
                proj_short_name=getattr(p, "proj_short_name", None) or getattr(p, "short_name", f"PROJ-{proj_id}"),
                clndr_id=parse_int(getattr(p, "clndr_id", None)),
                plan_start_date=ensure_datetime(getattr(p, "plan_start_date", None)),
                plan_end_date=ensure_datetime(getattr(p, "plan_end_date", None)),
                must_finish_by_date=ensure_datetime(getattr(p, "scd_end_date", None) or getattr(p, "target_end_date", None)),
                last_recalc_date=ensure_datetime(getattr(p, "last_recalc_date", None)),
                f_calc_mode="START_DATES",
                oos_mode="RETAINED_LOGIC",
                critical_path_type=critical_path_type,
                critical_float_hr_cnt=parse_float(getattr(p, "critical_drtn_hr_cnt", 0.0)),
                use_expect_end_flag=False,
                raw_fields=getattr(p, "data", {}),
            )

        # 2. Calendars
        for c in reader.calendars:
            cid = parse_int(getattr(c, "clndr_id", None) or getattr(c, "id", None))
            if not cid:
                continue
            parsed.calendars[cid] = XERCalendar(
                clndr_id=cid,
                clndr_name=getattr(c, "clndr_name", None) or getattr(c, "name", f"Cal-{cid}"),
                default_flag=parse_bool(getattr(c, "default_flag", False)),
                clndr_type=str(getattr(c, "clndr_type", "CA_Base")),
                day_hr_cnt=parse_float(getattr(c, "day_hr_cnt", 8.0)),
                week_hr_cnt=parse_float(getattr(c, "week_hr_cnt", 40.0)),
                month_hr_cnt=parse_float(getattr(c, "month_hr_cnt", 173.33)),
                year_hr_cnt=parse_float(getattr(c, "year_hr_cnt", 2080.0)),
                clndr_data=getattr(c, "clndr_data", None),
                raw_fields=getattr(c, "data", {}),
            )

        # 3. WBS
        for w in reader.wbss:
            wid = parse_int(getattr(w, "wbs_id", None) or getattr(w, "id", None))
            if not wid:
                continue
            parsed.wbs[wid] = XERWBS(
                wbs_id=wid,
                proj_id=parse_int(getattr(w, "proj_id", 0)),
                wbs_short_name=getattr(w, "wbs_short_name", "") or getattr(w, "code", ""),
                wbs_name=getattr(w, "wbs_name", "") or getattr(w, "name", ""),
                parent_wbs_id=parse_int(getattr(w, "parent_wbs_id", None)),
                seq_num=parse_int(getattr(w, "seq_num", 0)),
                raw_fields=getattr(w, "data", {}),
            )

        # 4. Tasks (Activities)
        for a in reader.activities:
            tid = parse_int(getattr(a, "task_id", None) or getattr(a, "id", None))
            if not tid:
                continue
            
            target_dur = parse_float(getattr(a, "target_drtn_hr_cnt", None) or getattr(a, "target_durn_hr_cnt", 0.0))
            remain_dur = parse_float(getattr(a, "remain_drtn_hr_cnt", None) or getattr(a, "remain_durn_hr_cnt", 0.0))

            parsed.tasks[tid] = XERTask(
                task_id=tid,
                proj_id=parse_int(getattr(a, "proj_id", 0)),
                wbs_id=parse_int(getattr(a, "wbs_id", 0)),
                clndr_id=parse_int(getattr(a, "clndr_id", None)),
                task_code=getattr(a, "task_code", "") or getattr(a, "code", f"ACT-{tid}"),
                task_name=getattr(a, "task_name", "") or getattr(a, "name", ""),
                task_type=str(getattr(a, "task_type", "TT_Task")),
                status_code=str(getattr(a, "status_code", "TK_NotStart")),
                target_durn_hr_cnt=target_dur,
                remain_durn_hr_cnt=remain_dur,
                act_work_qty=parse_float(getattr(a, "act_work_qty", 0.0)),
                phys_complete_pct=parse_float(getattr(a, "phys_complete_pct", 0.0)),
                target_start_date=ensure_datetime(getattr(a, "target_start_date", None)),
                target_end_date=ensure_datetime(getattr(a, "target_end_date", None)),
                early_start_date=ensure_datetime(getattr(a, "early_start_date", None)),
                early_end_date=ensure_datetime(getattr(a, "early_end_date", None)),
                late_start_date=ensure_datetime(getattr(a, "late_start_date", None)),
                late_end_date=ensure_datetime(getattr(a, "late_end_date", None)),
                act_start_date=ensure_datetime(getattr(a, "act_start_date", None)),
                act_end_date=ensure_datetime(getattr(a, "act_end_date", None)),
                restart_date=ensure_datetime(getattr(a, "restart_date", None)),
                reend_date=ensure_datetime(getattr(a, "reend_date", None)),
                expect_end_date=ensure_datetime(getattr(a, "expect_end_date", None)),
                total_float_hr_cnt=parse_float(getattr(a, "total_float_hr_cnt", 0.0)),
                free_float_hr_cnt=parse_float(getattr(a, "free_float_hr_cnt", 0.0)),
                driving_path_flag=parse_bool(getattr(a, "driving_path_flag", False)),
                cstr_type=getattr(a, "cstr_type", None),
                cstr_date=ensure_datetime(getattr(a, "cstr_date", None)),
                cstr_type2=getattr(a, "cstr_type2", None),
                cstr_date2=ensure_datetime(getattr(a, "cstr_date2", None)),
                raw_fields=getattr(a, "data", {}),
            )

        # 5. Predecessors
        for r in reader.relations:
            pid = parse_int(getattr(r, "task_pred_id", None) or getattr(r, "id", None))
            if not pid:
                continue
            parsed.predecessors.append(
                XERPredecessor(
                    task_pred_id=pid,
                    task_id=parse_int(getattr(r, "task_id", 0)),
                    pred_task_id=parse_int(getattr(r, "pred_task_id", 0)),
                    proj_id=parse_int(getattr(r, "proj_id", 0)),
                    pred_type=str(getattr(r, "pred_type", None) or getattr(r, "type", "PR_FS")),
                    lag_hr_cnt=parse_float(getattr(r, "lag_hr_cnt", None) or getattr(r, "lag", 0.0)),
                    comments=getattr(r, "comments", None),
                    raw_fields=getattr(r, "data", {}),
                )
            )

        # Ensure raw tables are referenced for validator
        parsed.raw_tables = {
            "PROJECT": [p.raw_fields for p in parsed.projects.values()],
            "CALENDAR": [c.raw_fields for c in parsed.calendars.values()],
            "TASK": [t.raw_fields for t in parsed.tasks.values()],
            "TASKPRED": [r.raw_fields for r in parsed.predecessors],
        }

        return parsed

    def _populate_typed_models_from_tables(self, parsed: XERParsedFile) -> None:
        """Populate typed models from raw table dictionaries."""
        for row in parsed.raw_tables.get("PROJECT", []):
            proj_id = parse_int(row.get("proj_id"))
            if not proj_id:
                continue
            parsed.projects[proj_id] = XERProject(
                proj_id=proj_id,
                proj_short_name=row.get("proj_short_name", f"PROJ-{proj_id}"),
                clndr_id=parse_int(row.get("clndr_id")),
                plan_start_date=parse_p6_date(row.get("plan_start_date")),
                plan_end_date=parse_p6_date(row.get("plan_end_date")),
                must_finish_by_date=parse_p6_date(row.get("must_finish_by_date") or row.get("target_end_date")),
                last_recalc_date=parse_p6_date(row.get("last_recalc_date") or row.get("scd_end_date")),
                f_calc_mode="START_DATES",
                oos_mode="RETAINED_LOGIC",
                critical_path_type="TOTAL_FLOAT",
                critical_float_hr_cnt=parse_float(row.get("critical_float_hr_cnt", "0.0")),
                use_expect_end_flag=parse_bool(row.get("use_expect_end_flag")),
                raw_fields=row,
            )

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

        for row in parsed.raw_tables.get("TASK", []):
            task_id = parse_int(row.get("task_id"))
            if not task_id:
                continue
            target_durn = parse_float(row.get("target_drtn_hr_cnt") or row.get("target_durn_hr_cnt", "0.0"))
            remain_durn = parse_float(row.get("remain_drtn_hr_cnt") or row.get("remain_durn_hr_cnt", "0.0"))

            parsed.tasks[task_id] = XERTask(
                task_id=task_id,
                proj_id=parse_int(row.get("proj_id")),
                wbs_id=parse_int(row.get("wbs_id")),
                clndr_id=parse_int(row.get("clndr_id")),
                task_code=row.get("task_code", f"ACT-{task_id}"),
                task_name=row.get("task_name", ""),
                task_type=row.get("task_type", "TT_Task"),
                status_code=row.get("status_code", "TK_NotStart"),
                target_durn_hr_cnt=target_durn,
                remain_durn_hr_cnt=remain_durn,
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

        for row in parsed.raw_tables.get("TASKPRED", []):
            pred_id = parse_int(row.get("task_pred_id"))
            if not pred_id:
                continue
            lag = parse_float(row.get("lag_drtn_hr_cnt") or row.get("lag_hr_cnt", "0.0"))
            parsed.predecessors.append(
                XERPredecessor(
                    task_pred_id=pred_id,
                    task_id=parse_int(row.get("task_id")),
                    pred_task_id=parse_int(row.get("pred_task_id")),
                    proj_id=parse_int(row.get("proj_id")),
                    pred_type=row.get("pred_type", "PR_FS"),
                    lag_hr_cnt=lag,
                    comments=row.get("comments"),
                    raw_fields=row,
                )
            )

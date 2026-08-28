"""
CLI Ingestion Utility for ARTH RCA.
Usage:
    uv run python ingest_snapshot.py "path/to/schedule.xer" [--baseline] [--project "Project Name"] [--org "Org Name"]
"""

import sys
import argparse
from pathlib import Path
from sqlmodel import Session

from arth_rca.db.database import default_engine, init_db
from arth_rca.ingestion.pipeline import IngestionPipeline


def main():
    parser = argparse.ArgumentParser(description="Ingest an Oracle Primavera P6 .xer snapshot into ARTH RCA.")
    parser.add_argument("file_path", type=str, help="Path to the .xer file")
    parser.add_argument("--baseline", action="store_true", help="Flag this snapshot as the project baseline")
    parser.add_argument("--project", type=str, default=None, help="Override project name")
    parser.add_argument("--org", type=str, default="Default Org", help="Organization name")
    parser.add_argument("--lenient", action="store_true", help="Allow ingestion even if non-critical validation warnings exist")

    args = parser.parse_args()
    path = Path(args.file_path)

    if not path.exists():
        print(f"Error: File not found at '{path}'")
        sys.exit(1)

    print(f"\n[ARTH Ingestion] Initializing database and parsing: {path.name}")
    init_db()

    with Session(default_engine) as session:
        pipeline = IngestionPipeline(session)
        try:
            snapshot, val_res = pipeline.ingest_xer_file(
                file_path=path,
                org_name=args.org,
                project_name=args.project,
                is_baseline=args.baseline,
                strict_validation=not args.lenient,
            )

            print("\n" + "=" * 55)
            print("  SNAPSHOT INGESTED SUCCESSFULLY")
            print("=" * 55)
            print(f"  Snapshot ID      : {snapshot.id}")
            print(f"  Project ID       : {snapshot.project_id}")
            print(f"  Data Date        : {snapshot.data_date.strftime('%Y-%m-%d')}")
            print(f"  Is Baseline      : {snapshot.is_baseline}")
            print(f"  Activities Count : {len(snapshot.activities)}")
            print(f"  Relations Count  : {len(snapshot.relationships)}")
            print(f"  Validation Status: {'PASSED (0 Errors)' if val_res.is_valid else 'FAILED'}")
            print("=" * 55 + "\n")

        except Exception as e:
            print(f"\n[Ingestion Failed]: {str(e)}")
            sys.exit(1)


if __name__ == "__main__":
    main()

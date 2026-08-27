"""
End-to-end ingestion pipeline: Parse XER -> Validate Integrity -> Load Immutable Snapshot.
"""

from typing import Union, Optional, Tuple
from pathlib import Path
from sqlmodel import Session

from arth_rca.parser.xer_parser import XERParser
from arth_rca.parser.validator import XERValidator, ValidationResult, XERValidationError
from arth_rca.db.repository import SnapshotRepository
from arth_rca.db.models import Snapshot


class IngestionPipeline:
    """Coordinates parsing, validation, and database persistence for schedule snapshots."""

    def __init__(self, session: Session):
        self.session = session
        self.parser = XERParser()
        self.validator = XERValidator()
        self.repository = SnapshotRepository(session)

    def ingest_xer_file(
        self,
        file_path: Union[str, Path],
        org_name: str = "Default Org",
        project_name: Optional[str] = None,
        is_baseline: bool = False,
        strict_validation: bool = True,
    ) -> Tuple[Snapshot, ValidationResult]:
        """
        Execute end-to-end ingestion pipeline on a file path.
        Fails fast if validation fails in strict mode.
        """
        path = Path(file_path)
        # 1. Parse
        parsed_xer = self.parser.parse_file(path)

        # 2. Validate
        validation_result = self.validator.validate(parsed_xer, strict=strict_validation)

        # 3. Resolve Project & Org
        org = self.repository.get_or_create_organization(org_name)
        
        # Derive project name from XER if not supplied
        if not project_name:
            for p in parsed_xer.projects.values():
                project_name = p.proj_short_name
                break
        if not project_name:
            project_name = path.stem

        p6_proj_id = None
        for p in parsed_xer.projects.values():
            p6_proj_id = str(p.proj_id)
            break

        project = self.repository.get_or_create_project(
            org_id=org.id,
            name=project_name,
            p6_project_id=p6_proj_id,
        )

        # 4. Persist Snapshot
        snapshot = self.repository.create_snapshot_from_xer(
            project_id=project.id,
            parsed_xer=parsed_xer,
            source_filename=path.name,
            is_baseline=is_baseline,
        )

        return snapshot, validation_result

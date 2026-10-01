"""Local input and evidence-pack export for Trace Signal."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import re
import zipfile

import defusedxml
import pandas as pd

from .analysis import JourneyResult
from .design import JourneyAudit
from .errors import DataProblem

defusedxml.defuse_stdlib()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_WORKBOOK_BYTES = 200 * 1024 * 1024
MAX_TABLE_ROWS = 250_000
MAX_TABLE_COLUMNS = 200
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _safe_cell(value: object) -> object:
    if isinstance(value, str):
        cleaned = _ILLEGAL_XML.sub("", value)
        if cleaned.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + cleaned
        return cleaned
    return value


def safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Neutralize spreadsheet formulas in object cells and column headers."""
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].map(_safe_cell)
    result.columns = [_safe_cell(str(column)) for column in result.columns]
    return result


def read_table(filename: str, payload: bytes, sheet_name: str = "events") -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if not payload:
        raise DataProblem("This file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise DataProblem("Uploads are limited to 50 MB. Reduce the log to the needed columns and period.")
    try:
        if suffix == ".csv":
            frame = pd.read_csv(BytesIO(payload))
        elif suffix in {".xlsx", ".xlsm"}:
            with zipfile.ZipFile(BytesIO(payload)) as workbook_zip:
                expanded = sum(member.file_size for member in workbook_zip.infolist())
            if expanded > MAX_EXPANDED_WORKBOOK_BYTES:
                raise DataProblem("This workbook expands beyond 200 MB. Remove unrelated sheets before upload.")
            workbook = pd.ExcelFile(BytesIO(payload))
            selected = sheet_name if sheet_name in workbook.sheet_names else workbook.sheet_names[0]
            frame = pd.read_excel(workbook, sheet_name=selected)
        else:
            raise DataProblem("Upload a CSV or XLSX file.")
    except DataProblem:
        raise
    except Exception as exc:  # pragma: no cover - parser messages vary by dependency
        raise DataProblem(f"Could not read {filename}: {exc}") from exc
    if len(frame) > MAX_TABLE_ROWS:
        raise DataProblem(f"The table exceeds the {MAX_TABLE_ROWS:,}-row safety limit; sample or shorten the log.")
    if len(frame.columns) > MAX_TABLE_COLUMNS:
        raise DataProblem(f"The table exceeds the {MAX_TABLE_COLUMNS}-column safety limit; keep the needed columns.")
    return frame


def dataframe_csv_bytes(frame: pd.DataFrame) -> bytes:
    return safe_frame(frame).to_csv(index=False).encode("utf-8")


def _metadata_frame(values: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "field": key,
                "value": json.dumps(value) if isinstance(value, (dict, list, tuple)) else value,
            }
            for key, value in values.items()
        ]
    )


def _excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with timezone-aware timestamps serialized as ISO-8601 text."""

    safe = frame.copy()
    for column in safe.columns:
        if isinstance(safe[column].dtype, pd.DatetimeTZDtype):
            safe[column] = safe[column].map(lambda value: value.isoformat() if pd.notna(value) else None)
    return safe


def build_evidence_workbook(
    *, metadata: dict[str, object], audit: JourneyAudit, result: JourneyResult
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sheets = {
            "read_me": _metadata_frame(metadata),
            "analysis_config": _metadata_frame(asdict(result.config)),
            "data_audit": audit.overview,
            "sequence_overview": result.overview,
            "transitions": result.transitions,
            "transition_entropy": result.transition_entropy,
            "positional_roles": result.roles,
            "dropoff": result.dropoff,
            "depth": result.depth,
            "paths": result.paths,
            "subgroup_summary": result.subgroup_summary,
            "subgroup_paths": result.subgroup_paths,
            "outcome_transitions": result.outcome_transition_comparison,
            "markov_summary": result.markov_summary,
            "removal_sensitivity": result.markov_removal,
            "memory_diagnostic": result.memory_diagnostic,
            "journeys": _excel_safe(result.journeys.drop(columns="sequence")),
            "event_positions": result.event_positions,
            "limitations": pd.DataFrame({"warning": result.warnings}),
        }
        for sheet_name, frame in sheets.items():
            safe_frame(frame).to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

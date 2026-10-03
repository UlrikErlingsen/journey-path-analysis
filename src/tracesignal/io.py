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
from .errors import DataProblem, out_of_memory_message
from .limits import active, demo_limit

defusedxml.defuse_stdlib()

# Size, row and column caps exist only in a public demo (SIGNAL_PUBLIC=1); see limits.py.
CSV_CHUNK_ROWS = 500_000
# Excel holds at most 1,048,576 rows per sheet (one is the header), and writing millions of cells into a workbook
# takes minutes and gigabytes. A sheet above either bound carries a note instead; every table is also offered as a
# CSV download with all rows.
EXCEL_SHEET_ROWS = 1_048_575
EXCEL_SHEET_CELLS = 2_000_000
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


def _check_shape(rows: int, columns: int) -> None:
    limits = active()
    if limits.table_rows is not None and rows > limits.table_rows:
        raise DataProblem(demo_limit(f"The table exceeds the demo's {limits.table_rows:,}-row limit."))
    if limits.table_columns is not None and columns > limits.table_columns:
        raise DataProblem(demo_limit(f"The table exceeds the demo's {limits.table_columns}-column limit."))


def read_table(filename: str, payload: bytes, sheet_name: str = "events") -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    limits = active()
    if not payload:
        raise DataProblem("This file is empty.")
    if limits.upload_bytes is not None and len(payload) > limits.upload_bytes:
        raise DataProblem(demo_limit(f"Uploads are limited to {limits.upload_bytes // (1024 * 1024)} MB in this demo."))
    try:
        if suffix == ".csv":
            chunks: list[pd.DataFrame] = []
            rows = 0
            for chunk in pd.read_csv(BytesIO(payload), chunksize=CSV_CHUNK_ROWS):
                rows += len(chunk)
                _check_shape(rows, len(chunk.columns))
                chunks.append(chunk)
            frame = chunks[0] if len(chunks) == 1 else pd.concat(chunks, ignore_index=True)
            del chunks
        elif suffix in {".xlsx", ".xlsm"}:
            if limits.expanded_workbook_bytes is not None:
                with zipfile.ZipFile(BytesIO(payload)) as workbook_zip:
                    expanded = sum(member.file_size for member in workbook_zip.infolist())
                if expanded > limits.expanded_workbook_bytes:
                    raise DataProblem(
                        demo_limit(f"Workbooks may expand to at most {limits.expanded_workbook_bytes // (1024 * 1024)} MB.")
                    )
            workbook = pd.ExcelFile(BytesIO(payload))
            selected = sheet_name if sheet_name in workbook.sheet_names else workbook.sheet_names[0]
            frame = pd.read_excel(workbook, sheet_name=selected)
        else:
            raise DataProblem("Upload a CSV or XLSX file.")
    except DataProblem:
        raise
    except MemoryError as exc:
        raise DataProblem(out_of_memory_message("this file")) from exc
    except Exception as exc:  # pragma: no cover - parser messages vary by dependency
        raise DataProblem(f"Could not read {filename}: {exc}") from exc
    _check_shape(len(frame), len(frame.columns))
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
            if len(frame) > EXCEL_SHEET_ROWS or frame.size > EXCEL_SHEET_CELLS:
                frame = pd.DataFrame(
                    {
                        "note": [
                            f"This table has {len(frame):,} rows × {len(frame.columns)} columns, too large for a "
                            "workbook sheet. Download its CSV from the Evidence pack page: it contains every row."
                        ]
                    }
                )
            safe_frame(frame).to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

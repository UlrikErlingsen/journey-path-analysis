"""Data limits: none locally, demo caps only with SIGNAL_PUBLIC=1, and large outputs stay complete.

Every test is fast: inputs beyond the demo caps are built by lowering the caps, never by building a huge file.
"""

from __future__ import annotations

from io import BytesIO
import zipfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tracesignal import JourneyConfig, analyze_journeys, validate_event_log
from tracesignal import limits
from tracesignal.design import audit_event_log
from tracesignal.errors import DataProblem, friendly_message
from tracesignal.io import build_evidence_workbook, read_table
from tracesignal.limits import Limits


TINY_DEMO = Limits(
    upload_bytes=2_000_000,
    expanded_workbook_bytes=1024,
    table_rows=100,
    table_columns=5,
    touchpoints=5,
    bootstrap_repetitions=100,
)


@pytest.fixture
def tiny_demo_caps(monkeypatch):
    monkeypatch.setattr(limits, "PUBLIC_DEMO", TINY_DEMO)
    return monkeypatch


def _workbook_bomb() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", "x" * 4096)
    return output.getvalue()


def test_local_mode_accepts_input_beyond_the_demo_caps(tiny_demo_caps, demo_events) -> None:
    tiny_demo_caps.delenv("SIGNAL_PUBLIC", raising=False)
    assert limits.active() == Limits()
    payload = demo_events.to_csv(index=False).encode("utf-8")  # > 100 rows, 8 columns, 11 touchpoints
    frame = read_table("events.csv", payload)
    assert len(frame) > TINY_DEMO.table_rows and len(frame.columns) > TINY_DEMO.table_columns
    with pytest.raises(DataProblem, match="Could not read"):  # past the size guard; just not a real workbook
        read_table("events.xlsx", _workbook_bomb())
    data = validate_event_log(frame)
    assert data.events["touchpoint"].nunique() > TINY_DEMO.touchpoints
    result = analyze_journeys(data, JourneyConfig(bootstrap_repetitions=200))
    assert int(result.markov_summary.set_index("measure").loc["Bootstrap repetitions", "value"]) == 200


def test_public_demo_enforces_its_caps_and_says_so(tiny_demo_caps, demo_events) -> None:
    tiny_demo_caps.setenv("SIGNAL_PUBLIC", "1")
    payload = demo_events.to_csv(index=False).encode("utf-8")
    narrow = demo_events[["journey_id", "timestamp", "touchpoint", "converted"]]
    cases = [
        (lambda: read_table("big.csv", b"0" * (TINY_DEMO.upload_bytes + 1)), "Uploads are limited"),
        (lambda: read_table("events.xlsx", _workbook_bomb()), "expand to at most"),
        (lambda: read_table("events.csv", payload), "100-row limit"),
        (lambda: read_table("wide.csv", b"a,b,c,d,e,f\n1,2,3,4,5,6\n"), "5-column limit"),
        (lambda: validate_event_log(narrow), "at most 100 events"),
    ]
    for call, pattern in cases:
        with pytest.raises(DataProblem, match=pattern) as caught:
            call()
        assert limits.DEMO_NOTE in str(caught.value)

    tiny_demo_caps.setattr(limits, "PUBLIC_DEMO", Limits(touchpoints=5, bootstrap_repetitions=100))
    with pytest.raises(DataProblem, match="at most 5 distinct touchpoints"):
        validate_event_log(demo_events)
    tiny_demo_caps.setattr(limits, "PUBLIC_DEMO", Limits(bootstrap_repetitions=100))
    with pytest.raises(DataProblem, match="at most 100 bootstrap repetitions") as caught:
        analyze_journeys(validate_event_log(demo_events), JourneyConfig(bootstrap_repetitions=200))
    assert limits.DEMO_NOTE in str(caught.value)


def test_real_demo_caps_follow_the_previous_release_limits() -> None:
    assert limits.PUBLIC_DEMO.upload_bytes == 50 * 1024 * 1024
    assert limits.PUBLIC_DEMO.table_rows == 250_000
    assert limits.PUBLIC_DEMO.touchpoints == 60


def test_running_out_of_memory_is_a_plain_message(monkeypatch) -> None:
    assert "not enough memory" in friendly_message(MemoryError())

    def exhausted(*args, **kwargs):
        raise MemoryError

    monkeypatch.setattr("tracesignal.io.pd.read_csv", exhausted)
    with pytest.raises(DataProblem, match="not enough memory for this file"):
        read_table("huge.csv", b"journey_id\nA\n")


def test_oversized_workbook_sheets_point_to_their_full_csv(monkeypatch, validated, result) -> None:
    monkeypatch.setattr("tracesignal.io.EXCEL_SHEET_CELLS", 1_000)
    payload = build_evidence_workbook(metadata={"app": "Trace Signal"}, audit=audit_event_log(validated), result=result)
    journeys = pd.read_excel(BytesIO(payload), sheet_name="journeys")
    assert list(journeys.columns) == ["note"]
    assert "contains every row" in journeys.iloc[0, 0]
    roles = pd.read_excel(BytesIO(payload), sheet_name="positional_roles")
    assert len(roles) == len(result.roles)


SMALL_SCREEN_APP = """
import tracesignal.ui.app as trace_app

trace_app.SCREEN_TABLE_ROWS = 3
trace_app.LAZY_EXPORT_EVENTS = 10
trace_app.render()
"""


def test_long_tables_are_truncated_on_screen_and_large_exports_are_deferred() -> None:
    app = AppTest.from_string(SMALL_SCREEN_APP, default_timeout=120)
    app.run()
    app.sidebar.radio[0].set_value("3 · Drop-off & depth").run()
    assert not app.exception, [error.value for error in app.exception]
    assert any("Showing the first 3 of" in str(caption.value) for caption in app.caption)
    app.sidebar.radio[0].set_value("6 · Evidence pack").run()
    assert not app.exception, [error.value for error in app.exception]
    assert any("prepared when you click it" in str(caption.value) for caption in app.caption)

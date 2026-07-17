from __future__ import annotations

import pandas as pd
import pytest

from tracesignal import DataProblem, JourneyConfig, validate_event_log
from tracesignal.design import audit_event_log


def test_demo_contract_is_valid(validated) -> None:
    assert validated.events["journey_id"].nunique() == 720
    assert validated.events["touchpoint"].nunique() >= 3
    assert validated.event_order_supplied


def test_events_are_sorted_by_case_time_and_order(validated) -> None:
    expected = validated.events.sort_values(
        ["journey_id", "timestamp", "event_order", "touchpoint"], kind="mergesort"
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(validated.events, expected)


def test_missing_required_column_is_rejected(demo_events) -> None:
    with pytest.raises(DataProblem, match="missing"):
        validate_event_log(demo_events.drop(columns="timestamp"))


def test_tied_timestamp_needs_event_order(demo_events) -> None:
    frame = demo_events.drop(columns="event_order").copy()
    indices = frame.index[frame["journey_id"] == frame.loc[0, "journey_id"]][:2]
    frame.loc[indices, "timestamp"] = frame.loc[indices[0], "timestamp"]
    with pytest.raises(DataProblem, match="tied timestamps"):
        validate_event_log(frame)


def test_explicit_order_resolves_tied_timestamps(demo_events) -> None:
    frame = demo_events.copy()
    indices = frame.index[frame["journey_id"] == frame.loc[0, "journey_id"]][:2]
    frame.loc[indices, "timestamp"] = frame.loc[indices[0], "timestamp"]
    assert validate_event_log(frame).event_order_supplied


def test_duplicate_event_key_is_rejected(demo_events) -> None:
    frame = pd.concat([demo_events, demo_events.iloc[[0]]], ignore_index=True)
    with pytest.raises(DataProblem, match="uniquely identify"):
        validate_event_log(frame)


@pytest.mark.parametrize("column", ["converted", "subgroup", "journey_value", "customer_id"])
def test_journey_level_fields_must_be_stable(demo_events, column: str) -> None:
    frame = demo_events.copy()
    journey = frame.loc[0, "journey_id"]
    indices = frame.index[frame["journey_id"] == journey]
    if len(indices) < 2:
        pytest.skip("Generated first journey is single-event")
    index = indices[1]
    if column == "converted":
        frame.loc[index, column] = 1 - int(frame.loc[index, column])
    elif column == "journey_value":
        frame.loc[index, column] = float(frame.loc[index, column]) + 1
    else:
        frame.loc[index, column] = f"changed-{column}"
    with pytest.raises(DataProblem, match="stable"):
        validate_event_log(frame)


def test_reserved_model_states_are_rejected(demo_events) -> None:
    frame = demo_events.copy()
    frame.loc[0, "touchpoint"] = "CONVERSION"
    with pytest.raises(DataProblem, match="reserved"):
        validate_event_log(frame)


def test_invalid_outcomes_are_rejected(demo_events) -> None:
    frame = demo_events.copy()
    frame["converted"] = 2
    with pytest.raises(DataProblem, match="only 0 and 1"):
        validate_event_log(frame)


def test_negative_value_is_rejected(demo_events) -> None:
    frame = demo_events.copy()
    journey = frame.loc[0, "journey_id"]
    frame.loc[frame["journey_id"] == journey, "journey_value"] = -1
    with pytest.raises(DataProblem, match="negative"):
        validate_event_log(frame)


def test_minimum_sample_is_enforced(demo_events) -> None:
    journeys = demo_events["journey_id"].drop_duplicates().head(19)
    with pytest.raises(DataProblem, match="At least 20"):
        validate_event_log(demo_events.loc[demo_events["journey_id"].isin(journeys)])


def test_missing_optional_fields_create_explicit_defaults(demo_events) -> None:
    frame = demo_events.drop(columns=["customer_id", "subgroup", "journey_value"])
    data = validate_event_log(frame)
    assert set(data.events["subgroup"]) == {"All journeys"}
    assert (data.events["journey_value"] == 0).all()
    assert (data.events["customer_id"] == data.events["journey_id"]).all()
    assert any("independent clusters" in warning for warning in data.warnings)


def test_config_rejects_too_few_bootstrap_repetitions() -> None:
    with pytest.raises(DataProblem, match="between 100"):
        JourneyConfig(bootstrap_repetitions=99)


def test_audit_uses_journey_level_outcomes(validated) -> None:
    audit = audit_event_log(validated)
    assert audit.outcome_counts["journeys"].sum() == 720
    assert set(audit.outcome_counts["outcome"]) == {"Conversion", "Drop-off"}

"""Event-log contracts for Trace Signal."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .errors import DataProblem


REQUIRED_COLUMNS = ("journey_id", "timestamp", "touchpoint", "converted")
RESERVED_STATES = {"START", "CONVERSION", "DROP_OFF"}


@dataclass(frozen=True)
class JourneyConfig:
    """Declared sequence-analysis choices."""

    collapse_consecutive: bool = True
    min_path_journeys: int = 5
    min_outcome_transition_support: int = 10
    bootstrap_repetitions: int = 300
    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        if not 1 <= self.min_path_journeys <= 1000:
            raise DataProblem("Minimum path support must be between 1 and 1,000 journeys.")
        if not 2 <= self.min_outcome_transition_support <= 1000:
            raise DataProblem("Minimum outcome-comparison support must be between 2 and 1,000 transitions.")
        if not 100 <= self.bootstrap_repetitions <= 5000:
            raise DataProblem("Bootstrap repetitions must be between 100 and 5,000.")
        if not 0.80 <= self.confidence_level <= 0.99:
            raise DataProblem("Confidence level must be between 0.80 and 0.99.")


@dataclass
class ValidatedJourneyData:
    events: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    event_order_supplied: bool = False


@dataclass
class JourneyAudit:
    overview: pd.DataFrame
    subgroup_counts: pd.DataFrame
    touchpoint_counts: pd.DataFrame
    outcome_counts: pd.DataFrame
    warnings: list[str]


def _stable_within_journey(events: pd.DataFrame, column: str) -> None:
    unstable = events.groupby("journey_id", observed=True)[column].nunique(dropna=False)
    if (unstable > 1).any():
        journey = unstable[unstable > 1].index[0]
        raise DataProblem(f"{column} must be stable within each journey; {journey} has several values.")


def validate_event_log(events: pd.DataFrame) -> ValidatedJourneyData:
    """Validate and standardize a case-based, timestamped touchpoint event log."""

    events = events.copy()
    missing = [column for column in REQUIRED_COLUMNS if column not in events]
    if missing:
        raise DataProblem(f"Event log is missing: {', '.join(missing)}.")
    if events.empty:
        raise DataProblem("The event log contains no rows.")
    if len(events) > 250_000:
        raise DataProblem("This local workbench supports at most 250,000 events per run.")

    for column in ("journey_id", "touchpoint"):
        if events[column].isna().any():
            raise DataProblem(f"{column} cannot contain missing values.")
        events[column] = events[column].astype(str).str.strip()
        if events[column].eq("").any():
            raise DataProblem(f"{column} cannot contain blank values.")
    reserved = events["touchpoint"].str.upper().isin(RESERVED_STATES)
    if reserved.any():
        value = events.loc[reserved, "touchpoint"].iloc[0]
        raise DataProblem(f"Touchpoint name {value} is reserved for the sequence model.")

    try:
        events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    except Exception as exc:
        raise DataProblem("Every timestamp must be a valid date or datetime.") from exc

    order_supplied = "event_order" in events
    tied_times = events.duplicated(["journey_id", "timestamp"], keep=False)
    if tied_times.any() and not order_supplied:
        journey = events.loc[tied_times, "journey_id"].iloc[0]
        raise DataProblem(
            f"Journey {journey} has tied timestamps. Add a numeric event_order column so the sequence is explicit."
        )
    if order_supplied:
        events["event_order"] = pd.to_numeric(events["event_order"], errors="coerce")
        if events["event_order"].isna().any() or (~np.isfinite(events["event_order"])).any():
            raise DataProblem("event_order must contain finite numeric values.")
    else:
        events["event_order"] = 0
    if events.duplicated(["journey_id", "timestamp", "event_order"]).any():
        raise DataProblem("journey_id, timestamp, and event_order must uniquely identify each event.")

    converted = pd.to_numeric(events["converted"], errors="coerce")
    if converted.isna().any() or not set(converted.unique()).issubset({0, 1}):
        raise DataProblem("converted must contain only 0 and 1.")
    events["converted"] = converted.astype(int)
    _stable_within_journey(events, "converted")

    warnings: list[str] = []
    if "subgroup" not in events:
        events["subgroup"] = "All journeys"
        warnings.append("No subgroup was supplied; path comparison uses one all-journey group.")
    events["subgroup"] = events["subgroup"].fillna("Unspecified").astype(str).str.strip().replace("", "Unspecified")
    _stable_within_journey(events, "subgroup")

    if "journey_value" not in events:
        events["journey_value"] = 0.0
    events["journey_value"] = pd.to_numeric(events["journey_value"], errors="coerce")
    if events["journey_value"].isna().any() or (~np.isfinite(events["journey_value"])).any():
        raise DataProblem("journey_value must contain finite numeric values.")
    if (events["journey_value"] < 0).any():
        raise DataProblem("journey_value cannot be negative.")
    _stable_within_journey(events, "journey_value")
    if ((events["converted"] == 0) & (events["journey_value"] > 0)).any():
        warnings.append("Some non-converted journeys have positive value; value is retained but not interpreted as conversion value.")

    if "customer_id" in events:
        events["customer_id"] = events["customer_id"].fillna("Unspecified").astype(str)
        _stable_within_journey(events, "customer_id")
    else:
        events["customer_id"] = events["journey_id"]
        warnings.append(
            "No customer_id was supplied; bootstrap uncertainty treats journeys as independent clusters."
        )

    journeys = events["journey_id"].nunique()
    touchpoints = events["touchpoint"].nunique()
    if journeys < 20:
        raise DataProblem("At least 20 journeys are required for sequence analysis.")
    if touchpoints < 3:
        raise DataProblem("At least three distinct touchpoints are required.")
    if touchpoints > 60:
        raise DataProblem("At most 60 distinct touchpoints are supported in the local Markov workbench.")
    if events["converted"].nunique() < 2:
        raise DataProblem("Both converted and non-converted journeys are required for drop-off and removal analysis.")

    events = events.sort_values(
        ["journey_id", "timestamp", "event_order", "touchpoint"], kind="mergesort"
    ).reset_index(drop=True)
    warnings.extend(
        [
            "The event log contains observed and successfully stitched touchpoints only; missing exposures remain invisible.",
            "Journey boundaries, identity resolution, timestamp quality, and touchpoint taxonomy determine the estimand.",
            "Every transition, role, path, drop-off rate, and removal effect is descriptive rather than causal.",
        ]
    )
    return ValidatedJourneyData(events=events, warnings=warnings, event_order_supplied=order_supplied)


def audit_event_log(data: ValidatedJourneyData) -> JourneyAudit:
    events = data.events
    journey_level = events.drop_duplicates("journey_id")
    overview = pd.DataFrame(
        [
            {"measure": "Events", "value": len(events)},
            {"measure": "Journeys", "value": events["journey_id"].nunique()},
            {"measure": "Touchpoints", "value": events["touchpoint"].nunique()},
            {"measure": "Conversion rate", "value": journey_level["converted"].mean()},
            {"measure": "First event", "value": events["timestamp"].min().isoformat()},
            {"measure": "Last event", "value": events["timestamp"].max().isoformat()},
            {"measure": "Explicit event order supplied", "value": data.event_order_supplied},
        ]
    )
    subgroup_counts = (
        journey_level.groupby("subgroup", observed=True)
        .agg(journeys=("journey_id", "size"), conversion_rate=("converted", "mean"))
        .reset_index()
        .sort_values("journeys", ascending=False)
    )
    touchpoint_counts = (
        events.groupby("touchpoint", observed=True)
        .agg(events=("journey_id", "size"), journeys=("journey_id", "nunique"))
        .reset_index()
        .sort_values("events", ascending=False)
    )
    outcome_counts = (
        journey_level.groupby("converted", observed=True)
        .size()
        .rename("journeys")
        .reset_index()
        .assign(outcome=lambda frame: frame["converted"].map({0: "Drop-off", 1: "Conversion"}))
        [["outcome", "journeys"]]
    )
    return JourneyAudit(
        overview=overview,
        subgroup_counts=subgroup_counts,
        touchpoint_counts=touchpoint_counts,
        outcome_counts=outcome_counts,
        warnings=list(data.warnings),
    )

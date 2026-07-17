"""Real event-log sequence analysis for TraceSignal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .design import JourneyConfig, ValidatedJourneyData
from .errors import DataProblem


START = "START"
CONVERSION = "CONVERSION"
DROP_OFF = "DROP_OFF"


@dataclass
class JourneyResult:
    config: JourneyConfig
    overview: pd.DataFrame
    journeys: pd.DataFrame
    event_positions: pd.DataFrame
    transitions: pd.DataFrame
    transition_entropy: pd.DataFrame
    roles: pd.DataFrame
    dropoff: pd.DataFrame
    depth: pd.DataFrame
    paths: pd.DataFrame
    subgroup_paths: pd.DataFrame
    subgroup_summary: pd.DataFrame
    outcome_transition_comparison: pd.DataFrame
    markov_removal: pd.DataFrame
    markov_summary: pd.DataFrame
    memory_diagnostic: pd.DataFrame
    warnings: list[str]


def _wilson(successes: int, total: int, confidence: float) -> tuple[float, float]:
    if total <= 0:
        return np.nan, np.nan
    z = float(stats.norm.ppf(0.5 + confidence / 2))
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    half = z * np.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    return float(max(0, centre - half)), float(min(1, centre + half))


def _role(index: int, length: int) -> str:
    if length == 1:
        return "Single"
    relative = index / (length - 1)
    if relative < 1 / 3:
        return "Early"
    if relative > 2 / 3:
        return "Late"
    return "Middle"


def _prepare(data: ValidatedJourneyData, config: JourneyConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    journey_rows: list[dict[str, object]] = []
    position_rows: list[dict[str, object]] = []
    for journey_id, raw_group in data.events.groupby("journey_id", sort=False, observed=True):
        group = raw_group.copy()
        original_events = len(group)
        # Duration uses the full pre-collapse timestamps so trailing repeated
        # events still count toward the observed journey window.
        start_time = raw_group["timestamp"].iloc[0]
        end_time = raw_group["timestamp"].iloc[-1]
        if config.collapse_consecutive:
            group = group.loc[group["touchpoint"].ne(group["touchpoint"].shift())].copy()
        sequence = tuple(group["touchpoint"].astype(str))
        if not sequence:
            continue
        duration_hours = (end_time - start_time).total_seconds() / 3600
        converted = int(group["converted"].iloc[0])
        journey_rows.append(
            {
                "journey_id": journey_id,
                "cluster_id": group["customer_id"].iloc[0],
                "subgroup": group["subgroup"].iloc[0],
                "converted": converted,
                "journey_value": float(group["journey_value"].iloc[0]),
                "start_time": start_time,
                "end_time": end_time,
                "duration_hours": duration_hours,
                "original_events": original_events,
                "analysis_events": len(sequence),
                "collapsed_events": original_events - len(sequence),
                "has_revisit": len(set(sequence)) < len(sequence),
                "path": " → ".join(sequence),
                "sequence": sequence,
            }
        )
        denominator = max(len(sequence) - 1, 1)
        for index, event in enumerate(group.itertuples(index=False)):
            position_rows.append(
                {
                    "journey_id": journey_id,
                    "subgroup": group["subgroup"].iloc[0],
                    "converted": converted,
                    "touchpoint": event.touchpoint,
                    "position": index + 1,
                    "relative_position": index / denominator if len(sequence) > 1 else 0.5,
                    "role": _role(index, len(sequence)),
                    "hours_from_start": (event.timestamp - start_time).total_seconds() / 3600,
                    "hours_to_end": (end_time - event.timestamp).total_seconds() / 3600,
                }
            )
    journeys = pd.DataFrame(journey_rows)
    positions = pd.DataFrame(position_rows)
    if journeys.empty:
        raise DataProblem("No journeys remain after sequence preparation.")
    return journeys, positions


def _transition_events(journeys: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in journeys.itertuples(index=False):
        end_state = CONVERSION if row.converted else DROP_OFF
        states = (START, *row.sequence, end_state)
        for position, (source, target) in enumerate(zip(states[:-1], states[1:], strict=True)):
            rows.append(
                {
                    "journey_id": row.journey_id,
                    "subgroup": row.subgroup,
                    "converted": row.converted,
                    "transition_position": position,
                    "from_state": source,
                    "to_state": target,
                }
            )
    return pd.DataFrame(rows)


def _transition_table(transition_events: pd.DataFrame, confidence: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = (
        transition_events.groupby(["from_state", "to_state"], observed=True)
        .size()
        .rename("transitions")
        .reset_index()
    )
    totals = counts.groupby("from_state", observed=True)["transitions"].transform("sum")
    counts["from_state_total"] = totals
    counts["probability"] = counts["transitions"] / totals
    intervals = [_wilson(int(row.transitions), int(row.from_state_total), confidence) for row in counts.itertuples()]
    counts["ci_low"] = [interval[0] for interval in intervals]
    counts["ci_high"] = [interval[1] for interval in intervals]
    counts = counts.sort_values(["from_state", "probability", "to_state"], ascending=[True, False, True])

    entropy_rows: list[dict[str, object]] = []
    for source, group in counts.groupby("from_state", observed=True):
        probabilities = group["probability"].to_numpy(dtype=float)
        entropy = float(-(probabilities * np.log2(probabilities)).sum())
        maximum = np.log2(len(probabilities)) if len(probabilities) > 1 else 0.0
        entropy_rows.append(
            {
                "from_state": source,
                "outgoing_states": len(probabilities),
                "transitions": int(group["transitions"].sum()),
                "next_state_entropy_bits": entropy,
                "normalized_entropy": entropy / maximum if maximum > 0 else 0.0,
            }
        )
    return counts.reset_index(drop=True), pd.DataFrame(entropy_rows)


def _role_table(positions: pd.DataFrame, confidence: float) -> pd.DataFrame:
    occurrence_totals = positions.groupby("touchpoint", observed=True).size()
    rows: list[dict[str, object]] = []
    for (touchpoint, role), group in positions.groupby(["touchpoint", "role"], observed=True):
        unique = group.drop_duplicates("journey_id")
        journeys = unique["journey_id"].nunique()
        conversions = int(unique["converted"].sum())
        low, high = _wilson(conversions, journeys, confidence)
        rows.append(
            {
                "touchpoint": touchpoint,
                "role": role,
                "occurrences": len(group),
                "journeys": journeys,
                "occurrence_share_within_touchpoint": len(group) / occurrence_totals[touchpoint],
                "associated_conversion_rate": conversions / journeys,
                "conversion_ci_low": low,
                "conversion_ci_high": high,
                "median_relative_position": group["relative_position"].median(),
                "median_hours_from_start": group["hours_from_start"].median(),
                "median_hours_to_end": group["hours_to_end"].median(),
            }
        )
    result = pd.DataFrame(rows)
    role_order = pd.CategoricalDtype(["Early", "Middle", "Late", "Single"], ordered=True)
    result["role"] = result["role"].astype(role_order)
    return result.sort_values(["touchpoint", "role"]).reset_index(drop=True)


def _dropoff_table(journeys: pd.DataFrame, positions: pd.DataFrame, confidence: float) -> pd.DataFrame:
    terminal_rows = []
    for row in journeys.itertuples(index=False):
        terminal_rows.append(
            {
                "journey_id": row.journey_id,
                "terminal_touchpoint": row.sequence[-1],
                "converted": row.converted,
            }
        )
    terminal = pd.DataFrame(terminal_rows)
    rows: list[dict[str, object]] = []
    for touchpoint, group in positions.groupby("touchpoint", observed=True):
        unique_visits = group.drop_duplicates("journey_id")
        visited = set(unique_visits["journey_id"])
        terminals = terminal.loc[
            terminal["journey_id"].isin(visited) & (terminal["terminal_touchpoint"] == touchpoint)
        ]
        dropoffs = int((terminals["converted"] == 0).sum())
        conversions = int(unique_visits["converted"].sum())
        visits = len(visited)
        low, high = _wilson(dropoffs, visits, confidence)
        rows.append(
            {
                "touchpoint": touchpoint,
                "journeys_visiting": visits,
                "nonconversion_endings": dropoffs,
                "dropoff_after_visit_rate": dropoffs / visits,
                "dropoff_ci_low": low,
                "dropoff_ci_high": high,
                "journey_conversion_association": conversions / visits,
                "median_relative_position": group["relative_position"].median(),
                "median_position": group["position"].median(),
            }
        )
    return pd.DataFrame(rows).sort_values("dropoff_after_visit_rate", ascending=False).reset_index(drop=True)


def _depth_table(journeys: pd.DataFrame, confidence: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total = len(journeys)
    max_depth = int(journeys["analysis_events"].max())
    for depth in range(1, max_depth + 1):
        reached = journeys.loc[journeys["analysis_events"] >= depth]
        continued = journeys.loc[journeys["analysis_events"] >= depth + 1]
        endings = journeys.loc[journeys["analysis_events"] == depth]
        continuation = len(continued) / len(reached) if len(reached) else np.nan
        low, high = _wilson(len(continued), len(reached), confidence)
        rows.append(
            {
                "depth": depth,
                "journeys_reaching": len(reached),
                "share_reaching": len(reached) / total,
                "conditional_continuation_rate": continuation,
                "continuation_ci_low": low,
                "continuation_ci_high": high,
                "journeys_ending": len(endings),
                "conversion_endings": int(endings["converted"].sum()),
                "dropoff_endings": int((1 - endings["converted"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def _aggregate_paths(journeys: pd.DataFrame, confidence: float, min_support: int, include_subgroup: bool) -> pd.DataFrame:
    group_columns = ["subgroup", "path"] if include_subgroup else ["path"]
    subgroup_sizes = journeys.groupby("subgroup", observed=True).size() if include_subgroup else None
    rows: list[dict[str, object]] = []
    for keys, group in journeys.groupby(group_columns, observed=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        record = dict(zip(group_columns, keys, strict=True))
        total = len(group)
        conversions = int(group["converted"].sum())
        low, high = _wilson(conversions, total, confidence)
        # Subgroup path shares are within-subgroup so each subgroup's shares sum to one.
        denominator = int(subgroup_sizes[record["subgroup"]]) if include_subgroup else len(journeys)
        record.update(
            {
                "journeys": total,
                "share": total / denominator,
                "conversions": conversions,
                "conversion_rate": conversions / total,
                "conversion_ci_low": low,
                "conversion_ci_high": high,
                "median_events": group["analysis_events"].median(),
                "median_duration_hours": group["duration_hours"].median(),
                "mean_converted_value": group.loc[group["converted"] == 1, "journey_value"].mean(),
                "meets_minimum_support": total >= min_support,
            }
        )
        rows.append(record)
    return pd.DataFrame(rows).sort_values(["journeys", "conversion_rate"], ascending=[False, False]).reset_index(drop=True)


def _subgroup_summary(journeys: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for subgroup, group in journeys.groupby("subgroup", observed=True):
        path_shares = group["path"].value_counts(normalize=True).to_numpy(dtype=float)
        entropy = float(-(path_shares * np.log2(path_shares)).sum())
        rows.append(
            {
                "subgroup": subgroup,
                "journeys": len(group),
                "conversion_rate": group["converted"].mean(),
                "median_events": group["analysis_events"].median(),
                "median_duration_hours": group["duration_hours"].median(),
                "revisit_rate": group["has_revisit"].mean(),
                "unique_paths": group["path"].nunique(),
                "path_entropy_bits": entropy,
            }
        )
    return pd.DataFrame(rows)


def _outcome_transition_comparison(transition_events: pd.DataFrame, min_support: int) -> pd.DataFrame:
    internal = transition_events.loc[~transition_events["to_state"].isin([CONVERSION, DROP_OFF])].copy()
    counts = (
        internal.groupby(["converted", "from_state", "to_state"], observed=True)
        .size()
        .rename("transitions")
        .reset_index()
    )
    counts["probability"] = counts["transitions"] / counts.groupby(
        ["converted", "from_state"], observed=True
    )["transitions"].transform("sum")
    probability = counts.pivot_table(
        index=["from_state", "to_state"], columns="converted", values="probability", fill_value=0
    ).rename(columns={0: "dropoff_journey_probability", 1: "converted_journey_probability"})
    support = counts.pivot_table(
        index=["from_state", "to_state"], columns="converted", values="transitions", fill_value=0
    ).rename(columns={0: "dropoff_journey_transitions", 1: "converted_journey_transitions"})
    result = probability.join(support, how="outer").fillna(0).reset_index()
    result["converted_minus_dropoff_probability"] = (
        result["converted_journey_probability"] - result["dropoff_journey_probability"]
    )
    # A difference ranked by |Δ| alone lets near-empty cells top the table, so
    # both outcome cells must reach the declared minimum transition count.
    result["meets_minimum_support"] = (
        (result["dropoff_journey_transitions"] >= min_support)
        & (result["converted_journey_transitions"] >= min_support)
    )
    result["_abs_difference"] = result["converted_minus_dropoff_probability"].abs()
    result = result.sort_values(
        ["meets_minimum_support", "_abs_difference"], ascending=[False, False]
    ).drop(columns="_abs_difference")
    return result.reset_index(drop=True)


def _markov_matrix(
    records: list[tuple[tuple[str, ...], int]], touchpoints: list[str]
) -> tuple[list[str], np.ndarray]:
    states = [START, *touchpoints, CONVERSION, DROP_OFF]
    index = {state: position for position, state in enumerate(states)}
    counts = np.zeros((len(states), len(states)), dtype=float)
    for sequence, converted in records:
        end = CONVERSION if converted else DROP_OFF
        path = (START, *sequence, end)
        for source, target in zip(path[:-1], path[1:], strict=True):
            counts[index[source], index[target]] += 1
    matrix = np.zeros_like(counts)
    for state in states:
        row = index[state]
        if state in {CONVERSION, DROP_OFF}:
            matrix[row, row] = 1.0
        elif counts[row].sum() > 0:
            matrix[row] = counts[row] / counts[row].sum()
        else:
            matrix[row, index[DROP_OFF]] = 1.0
    return states, matrix


def _conversion_probability(states: list[str], matrix: np.ndarray) -> float:
    transient = [state for state in states if state not in {CONVERSION, DROP_OFF}]
    transient_indices = [states.index(state) for state in transient]
    conversion_index = states.index(CONVERSION)
    q = matrix[np.ix_(transient_indices, transient_indices)]
    r = matrix[transient_indices, conversion_index]
    system = np.eye(len(q)) - q
    try:
        absorption = np.linalg.solve(system, r)
    except np.linalg.LinAlgError:
        absorption = np.linalg.lstsq(system, r, rcond=None)[0]
    return float(np.clip(absorption[transient.index(START)], 0, 1))


def _remove_state(states: list[str], matrix: np.ndarray, removed: str) -> tuple[list[str], np.ndarray]:
    keep = [index for index, state in enumerate(states) if state != removed]
    reduced_states = [states[index] for index in keep]
    reduced = matrix[np.ix_(keep, keep)].copy()
    drop_index = reduced_states.index(DROP_OFF)
    for row, state in enumerate(reduced_states):
        if state in {CONVERSION, DROP_OFF}:
            reduced[row] = 0
            reduced[row, row] = 1
            continue
        total = reduced[row].sum()
        if total > 0:
            reduced[row] /= total
        else:
            reduced[row, drop_index] = 1.0
    return reduced_states, reduced


def _markov_effects(records: list[tuple[tuple[str, ...], int]], touchpoints: list[str]) -> tuple[float, dict[str, float]]:
    states, matrix = _markov_matrix(records, touchpoints)
    baseline = _conversion_probability(states, matrix)
    effects: dict[str, float] = {}
    for touchpoint in touchpoints:
        reduced_states, reduced = _remove_state(states, matrix, touchpoint)
        removed_probability = _conversion_probability(reduced_states, reduced)
        effects[touchpoint] = (baseline - removed_probability) / baseline if baseline > 0 else np.nan
    return baseline, effects


def _markov_analysis(
    journeys: pd.DataFrame, config: JourneyConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    touchpoints = sorted({touchpoint for sequence in journeys["sequence"] for touchpoint in sequence})
    records = [(row.sequence, int(row.converted)) for row in journeys.itertuples(index=False)]
    baseline, effects = _markov_effects(records, touchpoints)
    states, matrix = _markov_matrix(records, touchpoints)
    rows: list[dict[str, object]] = []
    for touchpoint in touchpoints:
        reduced_states, reduced = _remove_state(states, matrix, touchpoint)
        removed_probability = _conversion_probability(reduced_states, reduced)
        rows.append(
            {
                "touchpoint": touchpoint,
                "journeys_containing": int(journeys["sequence"].map(lambda seq: touchpoint in seq).sum()),
                "baseline_markov_conversion_probability": baseline,
                "probability_after_removal": removed_probability,
                "absolute_removal_sensitivity": baseline - removed_probability,
                "relative_removal_sensitivity": effects[touchpoint],
            }
        )

    rng = np.random.default_rng(20260716)
    boot = {touchpoint: [] for touchpoint in touchpoints}
    cluster_records = [
        [(row.sequence, int(row.converted)) for row in group.itertuples(index=False)]
        for _, group in journeys.groupby("cluster_id", observed=True, sort=False)
    ]
    indices = np.arange(len(cluster_records))
    for _ in range(config.bootstrap_repetitions):
        sampled_clusters = rng.choice(indices, size=len(indices), replace=True)
        sampled = [record for index in sampled_clusters for record in cluster_records[index]]
        _, sampled_effects = _markov_effects(sampled, touchpoints)
        for touchpoint in touchpoints:
            boot[touchpoint].append(sampled_effects[touchpoint])
    alpha = (1 - config.confidence_level) / 2
    for row in rows:
        draws = np.asarray(boot[row["touchpoint"]], dtype=float)
        valid = draws[np.isfinite(draws)]
        if len(valid):
            row["relative_ci_low"] = float(np.quantile(valid, alpha))
            row["relative_ci_high"] = float(np.quantile(valid, 1 - alpha))
        else:
            row["relative_ci_low"] = np.nan
            row["relative_ci_high"] = np.nan

    # The pooled maximum-likelihood absorbing chain reproduces the observed
    # conversion rate exactly, so no "calibration gap" is reported: it is zero
    # by construction and would misleadingly suggest an informative check.
    summary = pd.DataFrame(
        [
            {"measure": "Observed conversion rate", "value": journeys["converted"].mean()},
            {"measure": "Fitted first-order Markov conversion probability", "value": baseline},
            {"measure": "Transient states", "value": len(touchpoints) + 1},
            {"measure": "Bootstrap clusters", "value": len(cluster_records)},
            {"measure": "Bootstrap repetitions", "value": config.bootstrap_repetitions},
        ]
    )
    removal = pd.DataFrame(rows).sort_values("relative_removal_sensitivity", ascending=False).reset_index(drop=True)
    return removal, summary


def _memory_diagnostic(journeys: pd.DataFrame) -> pd.DataFrame:
    triples: list[tuple[str, str, str]] = []
    for row in journeys.itertuples(index=False):
        end = CONVERSION if row.converted else DROP_OFF
        states = (START, *row.sequence, end)
        triples.extend(zip(states[:-2], states[1:-1], states[2:], strict=True))
    frame = pd.DataFrame(triples, columns=["previous_state", "current_state", "next_state"])
    rows: list[dict[str, object]] = []
    for current, group in frame.groupby("current_state", observed=True):
        joint = pd.crosstab(group["previous_state"], group["next_state"]).to_numpy(dtype=float)
        joint /= joint.sum()
        previous = joint.sum(axis=1, keepdims=True)
        following = joint.sum(axis=0, keepdims=True)
        expected = previous @ following
        mask = joint > 0
        mutual_information = float((joint[mask] * np.log2(joint[mask] / expected[mask])).sum())
        rows.append(
            {
                "touchpoint": current,
                "observed_context_transitions": len(group),
                "previous_contexts": group["previous_state"].nunique(),
                "next_states": group["next_state"].nunique(),
                "previous_next_conditional_mi_bits": mutual_information,
            }
        )
    return pd.DataFrame(rows).sort_values("previous_next_conditional_mi_bits", ascending=False).reset_index(drop=True)


def _overview(journeys: pd.DataFrame) -> pd.DataFrame:
    shares = journeys["path"].value_counts(normalize=True).to_numpy(dtype=float)
    path_entropy = float(-(shares * np.log2(shares)).sum())
    return pd.DataFrame(
        [
            {"measure": "Journeys", "value": len(journeys)},
            {"measure": "Analysis events", "value": journeys["analysis_events"].sum()},
            {"measure": "Collapsed consecutive events", "value": journeys["collapsed_events"].sum()},
            {"measure": "Conversion rate", "value": journeys["converted"].mean()},
            {"measure": "Median touchpoints", "value": journeys["analysis_events"].median()},
            {"measure": "Median duration hours", "value": journeys["duration_hours"].median()},
            {"measure": "Revisit rate", "value": journeys["has_revisit"].mean()},
            {"measure": "Unique paths", "value": journeys["path"].nunique()},
            {"measure": "Path entropy bits", "value": path_entropy},
        ]
    )


def analyze_journeys(
    data: ValidatedJourneyData, config: JourneyConfig | None = None
) -> JourneyResult:
    """Run descriptive sequence analysis on a validated event log."""

    config = config or JourneyConfig()
    journeys, positions = _prepare(data, config)
    transition_events = _transition_events(journeys)
    transitions, transition_entropy = _transition_table(transition_events, config.confidence_level)
    roles = _role_table(positions, config.confidence_level)
    dropoff = _dropoff_table(journeys, positions, config.confidence_level)
    depth = _depth_table(journeys, config.confidence_level)
    paths = _aggregate_paths(journeys, config.confidence_level, config.min_path_journeys, include_subgroup=False)
    subgroup_paths = _aggregate_paths(
        journeys, config.confidence_level, config.min_path_journeys, include_subgroup=True
    )
    subgroup_summary = _subgroup_summary(journeys)
    outcome_comparison = _outcome_transition_comparison(transition_events, config.min_outcome_transition_support)
    removal, markov_summary = _markov_analysis(journeys, config)
    memory = _memory_diagnostic(journeys)
    warnings = list(data.warnings)
    warnings.extend(
        [
            "Early, middle, late, and single roles are relative positions within observed journey length, not universal funnel stages.",
            "Path and touchpoint conversion rates condition on observed journey membership and are vulnerable to selection bias.",
            "Markov removal renormalizes the fitted transition matrix after deleting a state; it is a model sensitivity, not a real intervention.",
            "The first-order Markov model assumes the next state depends only on the current state and uses pooled stationary transitions.",
            "Bootstrap intervals resample customer clusters when customer_id is supplied, otherwise journeys; they do not repair "
            "identity stitching, missing touchpoints, interference, or causal confounding.",
        ]
    )
    return JourneyResult(
        config=config,
        overview=_overview(journeys),
        journeys=journeys,
        event_positions=positions,
        transitions=transitions,
        transition_entropy=transition_entropy,
        roles=roles,
        dropoff=dropoff,
        depth=depth,
        paths=paths,
        subgroup_paths=subgroup_paths,
        subgroup_summary=subgroup_summary,
        outcome_transition_comparison=outcome_comparison,
        markov_removal=removal,
        markov_summary=markov_summary,
        memory_diagnostic=memory,
        warnings=warnings,
    )

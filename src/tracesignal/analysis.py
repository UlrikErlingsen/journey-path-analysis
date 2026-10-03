"""Real event-log sequence analysis for Trace Signal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .design import JourneyConfig, ValidatedJourneyData
from .errors import DataProblem
from .limits import active, demo_limit


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


def _wilson_many(successes, totals, confidence: float) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized ``_wilson`` with the same arithmetic, for tables with many rows."""
    successes = np.asarray(successes, dtype=float)
    totals = np.asarray(totals, dtype=float)
    low = np.full(len(totals), np.nan)
    high = np.full(len(totals), np.nan)
    valid = totals > 0
    if valid.any():
        z = float(stats.norm.ppf(0.5 + confidence / 2))
        total = totals[valid]
        proportion = successes[valid] / total
        denominator = 1 + z**2 / total
        centre = (proportion + z**2 / (2 * total)) / denominator
        half = z * np.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
        low[valid] = np.maximum(0, centre - half)
        high[valid] = np.minimum(1, centre + half)
    return low, high


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
    """One row per journey and one row per analysed event, computed column-wise for event logs of any size.

    The validated events are sorted by journey, so each journey is one contiguous block of rows.
    """
    events = data.events
    n_events = len(events)
    if n_events == 0:
        raise DataProblem("No journeys remain after sequence preparation.")
    journey_ids = events["journey_id"].to_numpy()
    touchpoints = events["touchpoint"].to_numpy()
    new_journey = np.ones(n_events, dtype=bool)
    new_journey[1:] = journey_ids[1:] != journey_ids[:-1]
    starts = np.flatnonzero(new_journey)
    ends = np.append(starts[1:], n_events) - 1
    journey_of_event = np.cumsum(new_journey) - 1

    keep = new_journey.copy()
    if config.collapse_consecutive:
        keep[1:] |= touchpoints[1:] != touchpoints[:-1]
    else:
        keep[:] = True
    kept_rows = np.flatnonzero(keep)
    kept_journey = journey_of_event[kept_rows]
    lengths = np.bincount(kept_journey, minlength=len(starts))
    kept_starts = np.concatenate(([0], np.cumsum(lengths)[:-1]))
    kept_touchpoints = touchpoints[kept_rows]

    # Duration uses the full pre-collapse timestamps so trailing repeated events still count toward the window.
    timestamps = events["timestamp"]
    start_time = timestamps.iloc[starts].reset_index(drop=True)
    end_time = timestamps.iloc[ends].reset_index(drop=True)
    first = events.iloc[starts]
    converted = first["converted"].to_numpy().astype(int)
    subgroup = first["subgroup"].to_numpy()

    codes, _ = pd.factorize(kept_touchpoints)
    repeated = pd.DataFrame({"journey": kept_journey, "code": codes}).duplicated().to_numpy()
    has_revisit = np.bincount(kept_journey, weights=repeated, minlength=len(starts)) > 0
    sequences = [tuple(block) for block in np.split(kept_touchpoints, kept_starts[1:])]
    original_events = (ends - starts + 1).astype(int)

    journeys = pd.DataFrame(
        {
            "journey_id": journey_ids[starts],
            "cluster_id": first["customer_id"].to_numpy(),
            "subgroup": subgroup,
            "converted": converted,
            "journey_value": first["journey_value"].to_numpy(dtype=float),
            "start_time": start_time,
            "end_time": end_time,
            "duration_hours": (end_time - start_time).dt.total_seconds() / 3600,
            "original_events": original_events,
            "analysis_events": lengths.astype(int),
            "collapsed_events": original_events - lengths,
            "has_revisit": has_revisit,
            "path": [" → ".join(sequence) for sequence in sequences],
            "sequence": sequences,
        }
    )

    index_in_journey = np.arange(len(kept_rows)) - kept_starts[kept_journey]
    length_of_event = lengths[kept_journey]
    with np.errstate(divide="ignore", invalid="ignore"):
        relative = index_in_journey / (length_of_event - 1)
    relative_position = np.where(length_of_event > 1, relative, 0.5)
    role = np.where(
        length_of_event == 1,
        "Single",
        np.where(relative < 1 / 3, "Early", np.where(relative > 2 / 3, "Late", "Middle")),
    ).astype(object)
    kept_times = timestamps.iloc[kept_rows].reset_index(drop=True)
    journey_start = start_time.iloc[kept_journey].reset_index(drop=True)
    journey_end = end_time.iloc[kept_journey].reset_index(drop=True)
    positions = pd.DataFrame(
        {
            "journey_id": journey_ids[kept_rows],
            "subgroup": subgroup[kept_journey],
            "converted": converted[kept_journey],
            "touchpoint": kept_touchpoints,
            "position": (index_in_journey + 1).astype(int),
            "relative_position": relative_position,
            "role": role,
            "hours_from_start": (kept_times - journey_start).dt.total_seconds() / 3600,
            "hours_to_end": (journey_end - kept_times).dt.total_seconds() / 3600,
        }
    )
    if journeys.empty:
        raise DataProblem("No journeys remain after sequence preparation.")
    return journeys, positions


def _transition_events(journeys: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    """Every observed transition START → … → outcome, built column-wise from the analysed events."""
    lengths = journeys["analysis_events"].to_numpy()
    n_journeys = len(lengths)
    kept_starts = np.concatenate(([0], np.cumsum(lengths)[:-1]))
    journey_of_event = np.repeat(np.arange(n_journeys), lengths)
    event_touchpoints = positions["touchpoint"].to_numpy()
    previous = np.empty(len(event_touchpoints), dtype=object)
    previous[1:] = event_touchpoints[:-1]
    previous[kept_starts] = START
    converted = journeys["converted"].to_numpy()
    end_states = np.where(converted == 1, CONVERSION, DROP_OFF).astype(object)
    last_touchpoints = event_touchpoints[kept_starts + lengths - 1]

    total = len(event_touchpoints) + n_journeys
    # Each journey occupies lengths + 1 consecutive rows: its event transitions, then the terminal transition.
    event_slots = np.arange(len(event_touchpoints)) + journey_of_event
    terminal_slots = kept_starts + lengths + np.arange(n_journeys)
    from_state = np.empty(total, dtype=object)
    to_state = np.empty(total, dtype=object)
    position = np.empty(total, dtype=int)
    journey = np.empty(total, dtype=int)
    from_state[event_slots], to_state[event_slots] = previous, event_touchpoints
    from_state[terminal_slots], to_state[terminal_slots] = last_touchpoints, end_states
    position[event_slots] = positions["position"].to_numpy() - 1
    position[terminal_slots] = lengths
    journey[event_slots] = journey_of_event
    journey[terminal_slots] = np.arange(n_journeys)
    return pd.DataFrame(
        {
            "journey_id": journeys["journey_id"].to_numpy()[journey],
            "subgroup": journeys["subgroup"].to_numpy()[journey],
            "converted": converted[journey],
            "transition_position": position,
            "from_state": from_state,
            "to_state": to_state,
            "journey_index": journey,
        }
    )


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
    # A journey's terminal touchpoint is always one it visited, so terminal non-conversions per touchpoint need no
    # per-touchpoint membership test.
    terminal = pd.DataFrame(
        {
            "terminal_touchpoint": [sequence[-1] for sequence in journeys["sequence"]],
            "dropoff": journeys["converted"].to_numpy() == 0,
        }
    )
    dropoffs = terminal.loc[terminal["dropoff"]].groupby("terminal_touchpoint").size()
    visits = positions.drop_duplicates(["touchpoint", "journey_id"])
    grouped_visits = visits.groupby("touchpoint", observed=True)
    visit_counts = grouped_visits.size()
    conversions = grouped_visits["converted"].sum()
    grouped = positions.groupby("touchpoint", observed=True)
    median_relative = grouped["relative_position"].median()
    median_position = grouped["position"].median()
    touchpoints = visit_counts.index
    nonconversion = dropoffs.reindex(touchpoints, fill_value=0).to_numpy().astype(int)
    visit_values = visit_counts.to_numpy()
    low, high = _wilson_many(nonconversion, visit_values, confidence)
    table = pd.DataFrame(
        {
            "touchpoint": touchpoints.to_numpy(),
            "journeys_visiting": visit_values.astype(int),
            "nonconversion_endings": nonconversion,
            "dropoff_after_visit_rate": nonconversion / visit_values,
            "dropoff_ci_low": low,
            "dropoff_ci_high": high,
            "journey_conversion_association": conversions.to_numpy() / visit_values,
            "median_relative_position": median_relative.reindex(touchpoints).to_numpy(),
            "median_position": median_position.reindex(touchpoints).to_numpy(),
        }
    )
    return table.sort_values("dropoff_after_visit_rate", ascending=False).reset_index(drop=True)


def _depth_table(journeys: pd.DataFrame, confidence: float) -> pd.DataFrame:
    lengths = journeys["analysis_events"].to_numpy()
    total = len(journeys)
    max_depth = int(lengths.max())
    endings = np.bincount(lengths, minlength=max_depth + 2)
    conversion_endings = np.bincount(lengths, weights=journeys["converted"].to_numpy(), minlength=max_depth + 2)
    # journeys reaching depth d = journeys whose length is at least d
    reaching_at_least = endings[::-1].cumsum()[::-1]
    depths = np.arange(1, max_depth + 1)
    reached = reaching_at_least[depths]
    continued = reaching_at_least[depths + 1]
    low, high = _wilson_many(continued, reached, confidence)
    with np.errstate(divide="ignore", invalid="ignore"):
        continuation = np.where(reached > 0, continued / np.where(reached > 0, reached, 1), np.nan)
    ending_counts = endings[depths]
    converted_endings = conversion_endings[depths].astype(int)
    return pd.DataFrame(
        {
            "depth": depths,
            "journeys_reaching": reached.astype(int),
            "share_reaching": reached / total,
            "conditional_continuation_rate": continuation,
            "continuation_ci_low": low,
            "continuation_ci_high": high,
            "journeys_ending": ending_counts.astype(int),
            "conversion_endings": converted_endings,
            "dropoff_endings": (ending_counts - converted_endings).astype(int),
        }
    )


def _aggregate_paths(journeys: pd.DataFrame, confidence: float, min_support: int, include_subgroup: bool) -> pd.DataFrame:
    group_columns = ["subgroup", "path"] if include_subgroup else ["path"]
    grouped = journeys.groupby(group_columns, observed=True)
    table = grouped.agg(
        journeys=("converted", "size"),
        conversions=("converted", "sum"),
        median_events=("analysis_events", "median"),
        median_duration_hours=("duration_hours", "median"),
    )
    converted_value = (
        journeys.loc[journeys["converted"] == 1].groupby(group_columns, observed=True)["journey_value"].mean()
    )
    table["mean_converted_value"] = converted_value.reindex(table.index)
    table = table.reset_index()
    totals = table["journeys"].to_numpy()
    conversions = table["conversions"].to_numpy().astype(int)
    # Subgroup path shares are within-subgroup so each subgroup's shares sum to one.
    if include_subgroup:
        denominators = table["subgroup"].map(journeys.groupby("subgroup", observed=True).size()).to_numpy()
    else:
        denominators = np.full(len(table), len(journeys))
    low, high = _wilson_many(conversions, totals, confidence)
    result = pd.DataFrame({column: table[column].to_numpy() for column in group_columns})
    result["journeys"] = totals.astype(int)
    result["share"] = totals / denominators
    result["conversions"] = conversions
    result["conversion_rate"] = conversions / totals
    result["conversion_ci_low"] = low
    result["conversion_ci_high"] = high
    result["median_events"] = table["median_events"].to_numpy(dtype=float)
    result["median_duration_hours"] = table["median_duration_hours"].to_numpy(dtype=float)
    result["mean_converted_value"] = table["mean_converted_value"].to_numpy(dtype=float)
    result["meets_minimum_support"] = totals >= min_support
    return result.sort_values(["journeys", "conversion_rate"], ascending=[False, False]).reset_index(drop=True)


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


def _markov_matrix_from_counts(counts: np.ndarray) -> np.ndarray:
    """Row-normalized absorbing chain for states [START, touchpoints…, CONVERSION, DROP_OFF]."""
    size = len(counts)
    conversion, drop = size - 2, size - 1
    matrix = np.zeros_like(counts, dtype=float)
    totals = counts.sum(axis=1)
    transient = np.arange(size - 2)
    observed = transient[totals[transient] > 0]
    matrix[observed] = counts[observed] / totals[observed, None]
    matrix[transient[totals[transient] == 0], drop] = 1.0
    matrix[conversion, conversion] = 1.0
    matrix[drop, drop] = 1.0
    return matrix


def _absorption_probability(matrix: np.ndarray, transient: np.ndarray, conversion: int) -> float:
    q = matrix[np.ix_(transient, transient)]
    r = matrix[transient, conversion]
    system = np.eye(len(q)) - q
    try:
        absorption = np.linalg.solve(system, r)
    except np.linalg.LinAlgError:
        absorption = np.linalg.lstsq(system, r, rcond=None)[0]
    return float(np.clip(absorption[0], 0, 1))


def _removed_probability(matrix: np.ndarray, removed: int) -> float:
    """Conversion probability after deleting one touchpoint state and renormalizing the remaining rows."""
    size = len(matrix)
    keep = np.array([index for index in range(size) if index != removed])
    reduced = matrix[np.ix_(keep, keep)].copy()
    conversion, drop = len(keep) - 2, len(keep) - 1
    transient = np.arange(len(keep) - 2)
    totals = reduced[transient].sum(axis=1)
    positive = transient[totals > 0]
    reduced[positive] /= totals[totals > 0, None]
    empty = transient[totals <= 0]
    reduced[empty] = 0
    reduced[empty, drop] = 1.0
    return _absorption_probability(reduced, transient, conversion)


def _markov_effects_from_counts(counts: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Baseline conversion probability, probability after each touchpoint removal, and relative sensitivities."""
    matrix = _markov_matrix_from_counts(counts)
    size = len(matrix)
    baseline = _absorption_probability(matrix, np.arange(size - 2), size - 2)
    removed = np.array([_removed_probability(matrix, state) for state in range(1, size - 2)])
    relative = (baseline - removed) / baseline if baseline > 0 else np.full(len(removed), np.nan)
    return baseline, removed, relative


def _markov_analysis(
    journeys: pd.DataFrame, positions: pd.DataFrame, transition_events: pd.DataFrame, config: JourneyConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    touchpoints = sorted(set(positions["touchpoint"].unique()))
    states = [START, *touchpoints, CONVERSION, DROP_OFF]
    size = len(states)
    state_index = {state: index for index, state in enumerate(states)}
    from_codes = transition_events["from_state"].map(state_index).to_numpy()
    to_codes = transition_events["to_state"].map(state_index).to_numpy()
    pairs = from_codes * size + to_codes
    counts = np.bincount(pairs, minlength=size * size).reshape(size, size).astype(float)
    baseline, removed, relative = _markov_effects_from_counts(counts)

    containing = positions.drop_duplicates(["touchpoint", "journey_id"]).groupby("touchpoint").size()
    rows: list[dict[str, object]] = []
    for position, touchpoint in enumerate(touchpoints):
        rows.append(
            {
                "touchpoint": touchpoint,
                "journeys_containing": int(containing.get(touchpoint, 0)),
                "baseline_markov_conversion_probability": baseline,
                "probability_after_removal": float(removed[position]),
                "absolute_removal_sensitivity": baseline - float(removed[position]),
                "relative_removal_sensitivity": float(relative[position]),
            }
        )

    # Clustered bootstrap. Clusters are numbered in first-appearance order, exactly like a
    # groupby(cluster_id, sort=False), so the seeded draws match the record-by-record implementation; each
    # replicate's transition counts are the cluster counts weighted by how often the cluster was drawn.
    cluster_codes, cluster_values = pd.factorize(journeys["cluster_id"], sort=False)
    transition_cluster = cluster_codes[transition_events["journey_index"].to_numpy()]
    per_cluster = (
        pd.DataFrame({"cluster": transition_cluster, "pair": pairs}).value_counts().reset_index(name="count")
    )
    pair_codes = per_cluster["pair"].to_numpy()
    pair_clusters = per_cluster["cluster"].to_numpy()
    pair_counts = per_cluster["count"].to_numpy(dtype=float)
    n_clusters = len(cluster_values)
    rng = np.random.default_rng(20260716)
    indices = np.arange(n_clusters)
    draws = np.empty((config.bootstrap_repetitions, len(touchpoints)))
    for repetition in range(config.bootstrap_repetitions):
        sampled_clusters = rng.choice(indices, size=n_clusters, replace=True)
        multiplicity = np.bincount(sampled_clusters, minlength=n_clusters).astype(float)
        boot_counts = np.bincount(
            pair_codes, weights=multiplicity[pair_clusters] * pair_counts, minlength=size * size
        ).reshape(size, size)
        draws[repetition] = _markov_effects_from_counts(boot_counts)[2]
    alpha = (1 - config.confidence_level) / 2
    for position, row in enumerate(rows):
        column = draws[:, position]
        valid = column[np.isfinite(column)]
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
            {"measure": "Bootstrap clusters", "value": n_clusters},
            {"measure": "Bootstrap repetitions", "value": config.bootstrap_repetitions},
        ]
    )
    removal = pd.DataFrame(rows).sort_values("relative_removal_sensitivity", ascending=False).reset_index(drop=True)
    return removal, summary


def _memory_diagnostic(transition_events: pd.DataFrame) -> pd.DataFrame:
    # Triples (previous, current, next) are consecutive transitions within one journey.
    positions = transition_events["transition_position"].to_numpy()
    follows = np.flatnonzero(positions[1:] >= 1) + 1
    from_state = transition_events["from_state"].to_numpy()
    to_state = transition_events["to_state"].to_numpy()
    frame = pd.DataFrame(
        {
            "previous_state": from_state[follows - 1],
            "current_state": from_state[follows],
            "next_state": to_state[follows],
        }
    )
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
    cap = active().bootstrap_repetitions
    if cap is not None and config.bootstrap_repetitions > cap:
        raise DataProblem(demo_limit(f"The demo runs at most {cap} bootstrap repetitions."))
    journeys, positions = _prepare(data, config)
    transition_events = _transition_events(journeys, positions)
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
    removal, markov_summary = _markov_analysis(journeys, positions, transition_events, config)
    memory = _memory_diagnostic(transition_events)
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

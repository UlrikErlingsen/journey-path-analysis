from __future__ import annotations

import numpy as np
import pandas as pd

from tracesignal import JourneyConfig, analyze_journeys


def test_consecutive_repeats_are_audited(validated) -> None:
    collapsed = analyze_journeys(validated, JourneyConfig(collapse_consecutive=True, bootstrap_repetitions=100))
    retained = analyze_journeys(validated, JourneyConfig(collapse_consecutive=False, bootstrap_repetitions=100))
    assert collapsed.journeys["collapsed_events"].sum() > 0
    assert retained.journeys["collapsed_events"].sum() == 0
    assert collapsed.journeys["analysis_events"].sum() < retained.journeys["analysis_events"].sum()


def test_transition_rows_are_empirical_probability_distributions(result) -> None:
    totals = result.transitions.groupby("from_state", observed=True)["probability"].sum()
    assert np.allclose(totals, 1)
    assert set(result.transitions.loc[result.transitions["from_state"] == "START", "to_state"])
    assert {"CONVERSION", "DROP_OFF"}.issubset(set(result.transitions["to_state"]))


def test_transition_intervals_are_bounded(result) -> None:
    assert result.transitions["ci_low"].between(0, 1).all()
    assert result.transitions["ci_high"].between(0, 1).all()
    assert (result.transitions["ci_low"] <= result.transitions["probability"]).all()
    assert (result.transitions["probability"] <= result.transitions["ci_high"]).all()


def test_entropy_is_finite_and_normalized(result) -> None:
    assert np.isfinite(result.transition_entropy["next_state_entropy_bits"]).all()
    assert result.transition_entropy["normalized_entropy"].between(0, 1).all()


def test_positional_roles_cover_analysis_events(result) -> None:
    assert len(result.event_positions) == result.journeys["analysis_events"].sum()
    assert set(result.event_positions["role"]).issubset({"Early", "Middle", "Late", "Single"})
    assert result.event_positions["relative_position"].between(0, 1).all()


def test_each_touchpoint_role_share_sums_to_one(result) -> None:
    shares = result.roles.groupby("touchpoint", observed=True)["occurrence_share_within_touchpoint"].sum()
    assert np.allclose(shares, 1)


def test_terminal_dropoffs_do_not_exceed_visiting_journeys(result) -> None:
    assert (result.dropoff["nonconversion_endings"] <= result.dropoff["journeys_visiting"]).all()
    assert result.dropoff["dropoff_after_visit_rate"].between(0, 1).all()


def test_depth_reach_is_monotone(result) -> None:
    assert result.depth["share_reaching"].is_monotonic_decreasing
    assert result.depth.iloc[0]["share_reaching"] == 1
    assert result.depth["conditional_continuation_rate"].between(0, 1).all()


def test_paths_partition_journeys(result) -> None:
    assert result.paths["journeys"].sum() == len(result.journeys)
    assert np.isclose(result.paths["share"].sum(), 1)
    assert result.paths["conversion_rate"].between(0, 1).all()


def test_subgroup_paths_partition_each_subgroup(result) -> None:
    actual = result.subgroup_paths.groupby("subgroup", observed=True)["journeys"].sum().sort_index()
    expected = result.journeys.groupby("subgroup", observed=True).size().sort_index()
    pd.testing.assert_series_equal(actual, expected, check_names=False)


def test_subgroup_path_shares_are_within_subgroup(result) -> None:
    sums = result.subgroup_paths.groupby("subgroup", observed=True)["share"].sum()
    assert np.allclose(sums, 1)


def test_duration_uses_precollapse_timestamps(validated, result) -> None:
    spans = validated.events.groupby("journey_id", observed=True)["timestamp"].agg(["min", "max"])
    expected = (spans["max"] - spans["min"]).dt.total_seconds() / 3600
    actual = result.journeys.set_index("journey_id")["duration_hours"]
    assert np.allclose(actual.sort_index(), expected.sort_index())


def test_path_support_flag_uses_declared_threshold(result) -> None:
    expected = result.paths["journeys"] >= result.config.min_path_journeys
    pd.testing.assert_series_equal(result.paths["meets_minimum_support"], expected, check_names=False)


def test_outcome_transition_difference_is_arithmetic(result) -> None:
    expected = result.outcome_transition_comparison["converted_journey_probability"] - result.outcome_transition_comparison[
        "dropoff_journey_probability"
    ]
    assert np.allclose(result.outcome_transition_comparison["converted_minus_dropoff_probability"], expected)


def test_outcome_transition_support_flag_uses_both_outcome_cells(result) -> None:
    frame = result.outcome_transition_comparison
    threshold = result.config.min_outcome_transition_support
    expected = (frame["dropoff_journey_transitions"] >= threshold) & (
        frame["converted_journey_transitions"] >= threshold
    )
    pd.testing.assert_series_equal(frame["meets_minimum_support"], expected, check_names=False)
    supported = frame.loc[frame["meets_minimum_support"], "converted_minus_dropoff_probability"].abs()
    assert supported.is_monotonic_decreasing


def test_markov_summary_omits_zero_by_construction_calibration_gap(result) -> None:
    assert "Absolute calibration gap" not in set(result.markov_summary["measure"])


def test_markov_baseline_is_calibrated_to_observed_conversion(result) -> None:
    summary = result.markov_summary.set_index("measure")["value"]
    assert np.isclose(
        float(summary["Observed conversion rate"]),
        float(summary["Fitted first-order Markov conversion probability"]),
        atol=1e-10,
    )


def test_markov_removal_has_one_row_per_touchpoint(result) -> None:
    assert set(result.markov_removal["touchpoint"]) == set(result.event_positions["touchpoint"])
    assert np.isfinite(result.markov_removal["probability_after_removal"]).all()
    assert result.markov_removal["probability_after_removal"].between(0, 1).all()


def test_bootstrap_intervals_surround_point_estimates(result) -> None:
    assert (result.markov_removal["relative_ci_low"] <= result.markov_removal["relative_removal_sensitivity"]).all()
    assert (result.markov_removal["relative_removal_sensitivity"] <= result.markov_removal["relative_ci_high"]).all()


def test_memory_diagnostic_is_nonnegative(result) -> None:
    assert (result.memory_diagnostic["previous_next_conditional_mi_bits"] >= -1e-12).all()
    assert (result.memory_diagnostic["observed_context_transitions"] > 0).all()


def test_result_warnings_state_noncausal_boundaries(result) -> None:
    text = " ".join(result.warnings).lower()
    assert "not a real intervention" in text
    assert "descriptive rather than causal" in text
    assert "relative positions" in text

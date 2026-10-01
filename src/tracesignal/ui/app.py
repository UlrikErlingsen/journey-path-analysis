"""Trace Signal Streamlit UI.

Everything that draws the app runs inside ``render()`` (or the functions it calls), so it runs on every rerun,
both in the standalone ``app.py`` and inside Signal Hub. Module-level code here only defines constants and
functions. ``render()`` never calls ``st.set_page_config`` or ``st.navigation``.
"""

from __future__ import annotations

import os
import traceback

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from tracesignal import DataProblem, JourneyConfig, __version__, analyze_journeys, validate_event_log
from tracesignal.design import audit_event_log
from tracesignal.errors import friendly_message
from tracesignal.examples import make_demo_events, make_starter_template
from tracesignal.io import build_evidence_workbook, dataframe_csv_bytes, read_table
from tracesignal.ui import signal_theme as sig


NS = "trace"


def k(name: str) -> str:
    """Namespace a session-state or widget key with the app slug, so apps can share one Hub session."""
    return f"{NS}:{name}"


SIDEBAR_TAGLINE = "Event-log sequence evidence—not a journey-map canvas."
MASTHEAD_KICKER = "ORDER → COMPARE → STRESS-TEST"
MASTHEAD_PROMISES = ["Observed transitions", "Path evidence", "Honest sensitivity"]
FOOTER_LINE = "describes logged sequences, not incremental value"
DEMO_LABEL = "Deterministic fictional demonstration"
CAUTION = (
    "**Trace Signal describes logged sequences; it does not identify incremental channel value.** "
    "Touchpoint occurrence, order, and path membership are selected rather than randomized. Markov state deletion "
    "is model sensitivity—not the effect of switching off a real touchpoint. Test interventions in Experiment Signal."
)

# Chart colours from the Signal theme. The Sankey keeps its old meaning: one colour for every observed touchpoint,
# and distinct colours for the START state and the two terminal outcomes.
STATE_COLORS = {
    "START": sig.FAMILIES["research"]["600"],
    "CONVERSION": sig.FAMILIES["market"]["600"],
    "DROP_OFF": sig.FAMILIES["brand"]["600"],
}
ROLE_COLORS = dict(zip(["Early", "Middle", "Late"], sig.colorway(NS), strict=False))
# Removal sensitivity: the two signs sit on opposite arms of the shared diverging palette.
POSITIVE_SENSITIVITY = sig.DIVERGING[1]
NEGATIVE_SENSITIVITY = sig.DIVERGING[5]


def show_error(exc: Exception) -> None:
    """Show a calm error and keep tracebacks opt-in for trusted local debugging."""
    st.error(friendly_message(exc))
    if not isinstance(exc, (DataProblem, ValueError)) and os.getenv("TRACESIGNAL_DEBUG") == "1":
        with st.expander("Technical details"):
            st.code("".join(traceback.format_exception(exc)))


@st.cache_data(show_spinner=False)
def _demo() -> pd.DataFrame:
    return make_demo_events()


@st.cache_data(show_spinner="Analyzing observed journey sequences…")
def _analyze(events: pd.DataFrame, config: JourneyConfig):
    data = validate_event_log(events)
    return data, audit_event_log(data), analyze_journeys(data, config)


def _ensure_state() -> None:
    """Seed the active event log with the fictional demonstration on the first run of a session."""
    if k("events") not in st.session_state:
        st.session_state[k("events")] = _demo()
        st.session_state[k("source_label")] = DEMO_LABEL


def _store_events(frame: pd.DataFrame, label: str) -> None:
    st.session_state[k("events")] = frame
    st.session_state[k("source_label")] = label


def _load_data() -> None:
    """Read the selected data source into session state. A failed upload stops the run instead of using the demo."""
    source = st.sidebar.radio("Data source", ["Fictional demonstration", "Upload my event log"], key=k("data_source"))
    if source == "Fictional demonstration":
        _store_events(_demo(), DEMO_LABEL)
        return
    upload = st.sidebar.file_uploader("Journey events · CSV or XLSX", type=["csv", "xlsx", "xlsm"], key=k("upload"))
    if upload is None:
        st.sidebar.info("Upload an event log. Until then, the fictional demonstration remains active.")
        _store_events(_demo(), "Fictional demonstration while upload is incomplete")
        return
    try:
        frame = read_table(upload.name, upload.getvalue(), sheet_name="events")
    except Exception as exc:
        # A failed upload must never silently fall back to demo data: stop the
        # run loudly so demo results cannot be mistaken for the user's data.
        st.sidebar.error(friendly_message(exc))
        st.error(
            f"**The uploaded file could not be read, so no analysis was run.** {friendly_message(exc)} "
            "Fix the file and upload it again, or switch the data source back to the fictional demonstration."
        )
        st.stop()
        raise  # unreachable; keeps the control flow explicit for type checkers
    _store_events(frame, "User-supplied local event log")


def _config() -> JourneyConfig:
    st.sidebar.markdown("### Sequence contract")
    collapse = st.sidebar.checkbox("Collapse consecutive repeats", value=True, key=k("collapse_repeats"))
    min_support = st.sidebar.slider("Minimum journeys per reported path", 2, 30, 5, key=k("min_path_journeys"))
    outcome_support = st.sidebar.slider(
        "Minimum transitions per outcome cell", 2, 50, 10, key=k("min_outcome_support")
    )
    bootstrap = st.sidebar.select_slider(
        "Removal bootstrap repetitions", options=[100, 200, 300, 500], value=200, key=k("bootstrap_repetitions")
    )
    confidence = st.sidebar.select_slider(
        "Interval level", options=[0.90, 0.95, 0.99], value=0.95, key=k("confidence_level")
    )
    return JourneyConfig(
        collapse_consecutive=collapse,
        min_path_journeys=min_support,
        min_outcome_transition_support=outcome_support,
        bootstrap_repetitions=bootstrap,
        confidence_level=confidence,
    )


def _metric_value(frame: pd.DataFrame, measure: str):
    return frame.loc[frame["measure"] == measure, "value"].iloc[0]


def page_welcome() -> None:
    sig.hero(
        NS,
        eyebrow="OBSERVED JOURNEY SEQUENCE EVIDENCE",
        title="Where do journeys flow, stall, and end—",
        em="and how stable is that story?",
        body=(
            "Turn ordered case-level events into an auditable descriptive record: inspect touchpoint transitions, "
            "compare relative early/middle/late roles and complete paths, locate terminal drop-off, and stress-test "
            "a transparent first-order Markov description."
        ),
        pills=[
            "strict event ordering",
            "transition intervals",
            "relative sequence roles",
            "path + subgroup comparison",
            "depth attrition",
            "clustered removal sensitivity",
        ],
    )
    sig.note("warn", CAUTION)
    sig.note(
        "boundary",
        "**Non-negotiable boundary:** Trace Signal describes logged sequences. It does not identify incremental "
        "channel value, causes of conversion, customer intent, or the effect of removing a real touchpoint. "
        "Interventions belong in Experiment Signal.",
    )
    sig.cards(
        [
            (
                "01 · CONTRACT",
                "Event logs, not workshop maps",
                "Every result comes from ordered case-level events. Without defensible journey IDs, touchpoints, "
                "timestamps, and outcomes, analysis stops.",
            ),
            (
                "02 · COMPARE",
                "Sequence position is relative",
                "Early, middle, and late mean thirds of each observed journey—not universal funnel stages, customer "
                "psychology, or a hidden ontology.",
            ),
            (
                "03 · STRESS-TEST",
                "Removal is sensitivity",
                "State deletion and renormalization show model dependence. They do not simulate a real shutdown or "
                "allocate causal channel credit.",
            ),
        ]
    )
    st.markdown("### A deliberately bounded workflow")
    st.markdown(
        "1. Audit case identity, event order, journey boundaries, outcomes, and taxonomy.\n"
        "2. Inspect empirical transitions and positional roles.\n"
        "3. Locate terminal drop-off and depth attrition.\n"
        "4. Compare supported paths, subgroups, and outcome-conditioned transitions.\n"
        "5. Stress-test the first-order Markov description and export the evidence pack."
    )
    st.info(
        "Use the deterministic fictional demonstration to learn the workflow. It represents no real customer, "
        "organization, course case, or empirical result."
    )


def page_data(events: pd.DataFrame, source_label: str, config: JourneyConfig) -> None:
    sig.header("Step 1", "Data & sequence contract")
    st.caption(source_label)
    data = validate_event_log(events)
    audit = audit_event_log(data)
    values = dict(zip(audit.overview["measure"], audit.overview["value"], strict=True))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Journeys", f"{int(values['Journeys']):,}")
    c2.metric("Events", f"{int(values['Events']):,}")
    c3.metric("Touchpoints", f"{int(values['Touchpoints']):,}")
    c4.metric("Observed conversion", f"{float(values['Conversion rate']):.1%}")

    left, right = st.columns(2)
    with left:
        st.markdown("### Journey subgroups")
        st.dataframe(audit.subgroup_counts, width="stretch", hide_index=True)
        st.markdown("### Outcomes")
        st.dataframe(audit.outcome_counts, width="stretch", hide_index=True)
    with right:
        st.markdown("### Touchpoint coverage")
        st.dataframe(audit.touchpoint_counts, width="stretch", hide_index=True)

    st.markdown("### Event-log preview")
    st.dataframe(data.events.head(100), width="stretch", hide_index=True)
    with st.expander("Required contract and audit warnings"):
        st.write(
            "Required columns are journey_id, timestamp, touchpoint, and stable binary converted. Tied timestamps require a numeric "
            "event_order. subgroup, customer_id, and journey_value are optional but must be stable within a journey."
        )
        st.write(
            f"Consecutive repeats are {'collapsed' if config.collapse_consecutive else 'retained'} for this analysis. "
            "The evidence pack records this choice."
        )
        for warning in audit.warnings:
            st.warning(warning)
    st.download_button(
        "Download event-log template",
        dataframe_csv_bytes(make_starter_template()),
        "tracesignal-starter-template.csv",
        "text/csv",
        key=k("download_template"),
    )


def _sankey(transitions: pd.DataFrame, minimum_count: int) -> go.Figure:
    filtered = transitions.loc[
        (transitions["transitions"] >= minimum_count) & ~transitions["from_state"].isin(["CONVERSION", "DROP_OFF"])
    ].copy()
    states = list(dict.fromkeys([*filtered["from_state"], *filtered["to_state"]]))
    index = {state: position for position, state in enumerate(states)}
    touchpoint_color = sig.roles(NS)["highlight"]
    node_colors = [STATE_COLORS.get(state, touchpoint_color) for state in states]
    return go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(label=states, color=node_colors, pad=16, thickness=17),
            link=dict(
                source=filtered["from_state"].map(index),
                target=filtered["to_state"].map(index),
                value=filtered["transitions"],
                color=sig.CORE["line"],
            ),
        )
    ).update_layout(template=sig.template(NS), height=620, margin=dict(l=15, r=15, t=25, b=15))


def page_transitions(result) -> None:
    sig.header(
        "Step 2",
        "Transitions & positional roles",
        "Empirical first-order transitions include START and the observed terminal outcome state.",
    )
    minimum = st.slider("Minimum transitions shown in flow", 1, 100, 12, key=k("flow_minimum"))
    sig.chart(NS, _sankey(result.transitions, minimum), key=k("sankey_chart"))
    st.markdown("### Transition probabilities")
    st.dataframe(result.transitions, width="stretch", hide_index=True)

    st.markdown("### Next-state uncertainty")
    st.write("Entropy is high when a touchpoint leads to many similarly likely next states and low when one exit dominates.")
    st.dataframe(result.transition_entropy, width="stretch", hide_index=True)

    st.markdown("### Early, middle, late, and single roles")
    role_plot = result.roles.loc[result.roles["role"].astype(str) != "Single"].copy()
    figure = px.bar(
        role_plot,
        x="touchpoint",
        y="occurrence_share_within_touchpoint",
        color="role",
        barmode="stack",
        labels={
            "touchpoint": "Touchpoint",
            "occurrence_share_within_touchpoint": "Share of touchpoint occurrences",
            "role": "Relative role",
        },
        color_discrete_map=ROLE_COLORS,
        template=sig.template(NS),
    )
    figure.update_layout(yaxis_tickformat=".0%", legend_orientation="h", legend_y=1.12, margin=dict(t=35))
    sig.chart(NS, figure, key=k("roles_chart"))
    st.dataframe(result.roles, width="stretch", hide_index=True)
    st.warning("Associated conversion rates condition on the touchpoint and relative role; they are not touchpoint effects.")


def page_dropoff(result) -> None:
    sig.header("Step 3", "Drop-off & journey depth")
    sig.note(
        "boundary",
        "**Drop-off definition:** a journey is a drop-off when its supplied converted flag is 0. A touchpoint "
        "receives a terminal drop-off only when it is the final observed touchpoint in that journey.",
    )
    ordered = result.dropoff.sort_values("dropoff_after_visit_rate")
    figure = px.bar(
        ordered,
        x="dropoff_after_visit_rate",
        y="touchpoint",
        orientation="h",
        error_x=ordered["dropoff_ci_high"] - ordered["dropoff_after_visit_rate"],
        error_x_minus=ordered["dropoff_after_visit_rate"] - ordered["dropoff_ci_low"],
        labels={"dropoff_after_visit_rate": "Terminal nonconversion endings / journeys visiting", "touchpoint": "Touchpoint"},
        color_discrete_sequence=[sig.roles(NS)["highlight"]],
        template=sig.template(NS),
    )
    figure.update_layout(xaxis_tickformat=".0%", margin=dict(t=25))
    sig.chart(NS, figure, key=k("dropoff_chart"))
    st.dataframe(result.dropoff, width="stretch", hide_index=True)

    st.markdown("### Observed depth survival")
    depth_figure = px.line(
        result.depth,
        x="depth",
        y="share_reaching",
        markers=True,
        labels={"depth": "Touchpoint depth", "share_reaching": "Journeys reaching at least this depth"},
        color_discrete_sequence=[sig.roles(NS)["highlight"]],
        template=sig.template(NS),
    )
    depth_figure.update_layout(yaxis_tickformat=".0%", margin=dict(t=25))
    sig.chart(NS, depth_figure, key=k("depth_chart"))
    st.dataframe(result.depth, width="stretch", hide_index=True)


def page_paths(result) -> None:
    sig.header("Step 4", "Observed path comparison")
    supported = result.paths.loc[result.paths["meets_minimum_support"]].copy()
    st.caption(
        f"Paths require at least {result.config.min_path_journeys} journeys for the primary comparison. Rare paths remain in the evidence pack."
    )
    if supported.empty:
        st.info("No path reaches the selected support threshold.")
    else:
        plot = supported.head(40)
        figure = px.scatter(
            plot,
            x="journeys",
            y="conversion_rate",
            size="median_events",
            color="median_duration_hours",
            hover_name="path",
            labels={
                "journeys": "Journey count",
                "conversion_rate": "Observed conversion rate",
                "median_events": "Median touchpoints",
                "median_duration_hours": "Median duration (hours)",
            },
            color_continuous_scale=sig.sequential(NS),
            template=sig.template(NS),
        )
        figure.update_layout(yaxis_tickformat=".0%", margin=dict(t=25))
        sig.chart(NS, figure, key=k("paths_chart"))
        st.dataframe(supported, width="stretch", hide_index=True)

    st.markdown("### Subgroup sequence summary")
    st.dataframe(result.subgroup_summary, width="stretch", hide_index=True)
    selected_group = st.selectbox(
        "Inspect supported paths for subgroup", list(result.subgroup_summary["subgroup"]), key=k("path_subgroup")
    )
    group_paths = result.subgroup_paths.loc[
        (result.subgroup_paths["subgroup"] == selected_group) & result.subgroup_paths["meets_minimum_support"]
    ]
    st.dataframe(group_paths, width="stretch", hide_index=True)

    st.markdown("### Transitions in converted versus drop-off journeys")
    st.write(
        "This conditions on the final outcome and compares internal transition distributions. It is descriptive and can introduce collider or selection bias."
    )
    supported_outcome = result.outcome_transition_comparison.loc[
        result.outcome_transition_comparison["meets_minimum_support"]
    ]
    if supported_outcome.empty:
        st.info("No transition reaches the selected per-outcome support threshold.")
    else:
        st.dataframe(supported_outcome, width="stretch", hide_index=True)
    st.caption(
        f"Only transitions with at least {result.config.min_outcome_transition_support} observations in both the "
        "converted and drop-off groups are shown, so sparse cells cannot top the ranking. The differences carry no "
        "uncertainty intervals; treat the ordering as descriptive. All rows remain in the evidence pack."
    )


def page_markov(result) -> None:
    sig.header("Step 5", "Descriptive Markov removal sensitivity")
    sig.note(
        "warn",
        "**Not causal attribution:** each touchpoint is deleted from the fitted first-order transition matrix and "
        "remaining row probabilities are renormalized. The result answers how this model changes—not what would "
        "happen if the business removed that touchpoint.",
    )
    observed = float(_metric_value(result.markov_summary, "Observed conversion rate"))
    fitted = float(_metric_value(result.markov_summary, "Fitted first-order Markov conversion probability"))
    clusters = int(_metric_value(result.markov_summary, "Bootstrap clusters"))
    c1, c2, c3 = st.columns(3)
    c1.metric("Observed conversion", f"{observed:.1%}")
    c2.metric("Fitted Markov conversion", f"{fitted:.1%}")
    c3.metric("Bootstrap clusters", f"{clusters:,}")

    ordered = result.markov_removal.sort_values("relative_removal_sensitivity")
    figure = go.Figure(
        go.Bar(
            x=ordered["relative_removal_sensitivity"],
            y=ordered["touchpoint"],
            orientation="h",
            marker_color=[
                POSITIVE_SENSITIVITY if value >= 0 else NEGATIVE_SENSITIVITY
                for value in ordered["relative_removal_sensitivity"]
            ],
            error_x=dict(
                type="data",
                symmetric=False,
                array=ordered["relative_ci_high"] - ordered["relative_removal_sensitivity"],
                arrayminus=ordered["relative_removal_sensitivity"] - ordered["relative_ci_low"],
            ),
        )
    )
    figure.update_layout(
        template=sig.template(NS),
        xaxis_title="Relative change in fitted conversion probability after state deletion",
        yaxis_title="Touchpoint",
        xaxis_tickformat=".0%",
        height=520,
        margin=dict(t=25),
    )
    sig.chart(NS, figure, key=k("removal_chart"))
    st.dataframe(result.markov_removal, width="stretch", hide_index=True)
    st.caption("Negative sensitivity can occur after renormalization and is not evidence that a real touchpoint is harmful.")

    st.markdown("### First-order memory diagnostic")
    st.write(
        "Conditional mutual information tests descriptively whether the previous state still contains information about the next state after the current touchpoint is known. Larger values flag possible first-order misspecification; small samples bias this diagnostic upward."
    )
    st.dataframe(result.memory_diagnostic, width="stretch", hide_index=True)


def page_evidence(audit, result, source_label: str) -> None:
    sig.header("Step 6", "Evidence pack")
    metadata = {
        "app": "Trace Signal",
        "version": __version__,
        "name_status": "Informally screened working name; not legally cleared, and this record is not a trademark opinion.",
        "data_source": source_label,
        "analysis_type": "Observed event-log sequence analysis",
        "markov_boundary": "First-order descriptive removal sensitivity; not causal attribution",
        "role_boundary": "Early/middle/late are relative observed positions",
        "intervention_handoff": "Experiment Signal",
    }
    workbook = build_evidence_workbook(metadata=metadata, audit=audit, result=result)
    st.download_button(
        "Download Trace Signal evidence pack",
        workbook,
        "tracesignal-evidence-pack.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key=k("download_evidence_pack"),
    )
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "Transitions CSV",
        dataframe_csv_bytes(result.transitions),
        "tracesignal-transitions.csv",
        "text/csv",
        key=k("download_transitions"),
    )
    c2.download_button(
        "Paths CSV",
        dataframe_csv_bytes(result.paths),
        "tracesignal-paths.csv",
        "text/csv",
        key=k("download_paths"),
    )
    c3.download_button(
        "Removal sensitivity CSV",
        dataframe_csv_bytes(result.markov_removal),
        "tracesignal-removal-sensitivity.csv",
        "text/csv",
        key=k("download_removal_sensitivity"),
    )
    st.json(metadata)
    st.info("The export contains observed sequence evidence and model diagnostics, not a journey diagram or causal channel-credit allocation.")


def page_methods() -> None:
    sig.header("Methods and boundaries", "What Trace Signal calculates")
    st.markdown("### What is calculated")
    st.write(
        "- Empirical transition counts, row probabilities, Wilson intervals, and next-state entropy.\n"
        "- Relative early/middle/late/single roles from normalized within-journey position.\n"
        "- Terminal nonconversion drop-off after each visited touchpoint and observed depth continuation.\n"
        "- Supported path frequencies, conversion associations, duration, value, subgroup variation, and outcome-conditioned transitions.\n"
        "- First-order absorbing Markov conversion probability, state-deletion sensitivity, clustered bootstrap intervals, and a memory diagnostic."
    )
    st.markdown("### What is not calculated")
    st.write(
        "- No invented or workshop-authored journey diagram.\n"
        "- No hidden stage ontology beyond relative sequence position.\n"
        "- No claim that logged nonconversion equals dissatisfaction.\n"
        "- No causal channel contribution, incrementality, budget recommendation, or real-world removal effect.\n"
        "- No recovery of missing offline, cross-device, anonymous, or incorrectly stitched touchpoints."
    )
    st.markdown("### Independent public foundations")
    st.markdown(
        "The implementation is independently written from public work on event logs and sequential journey analysis, including "
        "[De Weerdt & Wynn (2022)](https://doi.org/10.1007/978-3-031-08848-3_6), "
        "[Shao & Li (2011)](https://doi.org/10.1145/2020408.2020453), and "
        "[Anderl et al. (2016)](https://doi.org/10.1016/j.ijresmar.2016.03.001)."
    )
    st.caption(
        "It does not reproduce lecture slides, notes, cases, exercises, diagrams, assessment material, datasets, "
        "questionnaire wording, or institution-specific frameworks; general topics encountered in education only "
        "define the problem domain."
    )


PAGES = [
    "Welcome",
    "1 · Data & sequence contract",
    "2 · Transitions & roles",
    "3 · Drop-off & depth",
    "4 · Path comparison",
    "5 · Markov removal sensitivity",
    "6 · Evidence pack",
    "Methods & boundaries",
]


def _sidebar() -> tuple[str, JourneyConfig]:
    """Draw the sidebar lockup, page selector, data source and sequence contract; return the page and config."""
    sig.sidebar_brand(NS, SIDEBAR_TAGLINE)
    st.sidebar.caption(f"Event-log sequence evidence · v{__version__}")
    page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed", key=k("page"))
    _load_data()
    config = _config()
    events = st.session_state[k("events")]
    journey_count = f"{events['journey_id'].nunique():,}" if "journey_id" in events else "unvalidated"
    st.sidebar.caption(f"Active data · {journey_count} journeys × {len(events):,} events")
    st.sidebar.divider()
    st.sidebar.caption("Local mode · no telemetry · no external AI calls · uploads stay in this Python process")
    return page, config


def _show_page(page: str, config: JourneyConfig) -> None:
    events = st.session_state[k("events")]
    source_label = st.session_state[k("source_label")]
    if page == "Welcome":
        page_welcome()
    elif page == "1 · Data & sequence contract":
        page_data(events, source_label, config)
    elif page == "Methods & boundaries":
        page_methods()
    else:
        _validated, data_audit, analysis = _analyze(events, config)
        if page == "2 · Transitions & roles":
            page_transitions(analysis)
        elif page == "3 · Drop-off & depth":
            page_dropoff(analysis)
        elif page == "4 · Path comparison":
            page_paths(analysis)
        elif page == "5 · Markov removal sensitivity":
            page_markov(analysis)
        elif page == "6 · Evidence pack":
            page_evidence(data_audit, analysis, source_label)


def render() -> None:
    """Draw the whole Trace Signal app on the current page. Never calls st.set_page_config or st.navigation."""
    sig.apply(NS)
    _ensure_state()
    page, config = _sidebar()
    sig.masthead(NS, MASTHEAD_PROMISES, MASTHEAD_KICKER)
    try:
        _show_page(page, config)
    except Exception as exc:
        show_error(exc)
    sig.footer(NS, __version__, FOOTER_LINE)

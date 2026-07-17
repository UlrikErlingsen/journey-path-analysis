from __future__ import annotations

import os

# Keep Arrow serialization stable on macOS. This must be set before Streamlit imports Arrow.
os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")

import base64
import inspect
from pathlib import Path
import sys
import traceback

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tracesignal import DataProblem, JourneyConfig, __version__, analyze_journeys, validate_event_log  # noqa: E402
from tracesignal.design import audit_event_log  # noqa: E402
from tracesignal.errors import friendly_message  # noqa: E402
from tracesignal.examples import make_demo_events, make_starter_template  # noqa: E402
from tracesignal.io import build_evidence_workbook, dataframe_csv_bytes, read_table  # noqa: E402


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
COLORS = {
    "ink": "#17322E",
    "deep": "#102C2A",
    "teal": "#173C3A",
    "coral": "#D95B40",
    "mint": "#83D2B4",
    "gold": "#F2C66D",
    "paper": "#F8F5ED",
    "muted": "#59716C",
}
CAUTION = (
    "**TraceSignal describes logged sequences; it does not identify incremental channel value.** "
    "Touchpoint occurrence, order, and path membership are selected rather than randomized. Markov state deletion "
    "is model sensitivity—not the effect of switching off a real touchpoint. Test interventions in ExperimentSignal."
)
mark_path = ROOT / "assets" / "tracesignal-mark.svg"
MARK_URI = (
    "data:image/svg+xml;base64," + base64.b64encode(mark_path.read_bytes()).decode("ascii")
    if mark_path.exists()
    else ""
)


def full_width(widget, *args, **kwargs):
    """Use Streamlit's current width API while retaining older compatibility."""
    try:
        parameters = inspect.signature(widget).parameters
    except (TypeError, ValueError):
        parameters = {}
    width_parameter = parameters.get("width")
    if width_parameter is not None and isinstance(width_parameter.default, str):
        kwargs["width"] = "stretch"
    elif "use_container_width" in parameters:
        kwargs["use_container_width"] = True
    return widget(*args, **kwargs)


st.set_page_config(page_title="TraceSignal | Event-log sequence evidence", page_icon="◇", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --js-ink:#17322e; --js-deep:#102c2a; --js-teal:#173c3a;
        --js-coral:#d95b40; --js-mint:#83d2b4; --js-gold:#f2c66d;
        --js-paper:#f8f5ed; --js-line:rgba(23,50,46,.14);
    }
    [data-testid="stAppViewContainer"] {
        background:radial-gradient(circle at 94% 2%,rgba(131,210,180,.17),transparent 28rem),
                   radial-gradient(circle at 3% 93%,rgba(242,198,109,.14),transparent 25rem),
                   linear-gradient(180deg,#fbf9f3 0%,var(--js-paper) 100%);
    }
    [data-testid="stHeader"] { background:rgba(248,245,237,.78); }
    [data-testid="stSidebar"] { background:linear-gradient(165deg,#173c3a 0%,#102c2a 65%,#0c2422 100%); }
    [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span { color:#f8f5ed; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#b9cbc5; }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background:rgba(255,255,255,.06); border-color:rgba(242,198,109,.32);
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small,
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small span { color:#b9cbc5 !important; }
    [data-testid="stSidebar"] button {
        background:rgba(255,255,255,.08); color:#f8f5ed !important; border-color:rgba(255,255,255,.23);
    }
    [data-testid="stSidebar"] button:hover { background:rgba(242,198,109,.14); border-color:rgba(242,198,109,.48); }
    [data-testid="stSidebar"] button * { color:#f8f5ed !important; }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
        background:#f8f5ed; color:#17322e !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button * { color:#17322e !important; }
    .block-container { max-width:1240px; padding-top:4.4rem; padding-bottom:4rem; }
    h1,h2,h3 { color:var(--js-ink); letter-spacing:-.025em; }
    a { color:#9b3e2b; }
    [data-testid="stMetric"] {
        background:rgba(255,255,255,.75); border:1px solid var(--js-line); border-radius:16px;
        padding:1rem 1.05rem; box-shadow:0 8px 28px rgba(23,50,46,.045);
    }
    [data-testid="stMetricValue"] { color:var(--js-ink); font-size:clamp(1.35rem,2.3vw,1.9rem); }
    [data-testid="stDataFrame"] { border:1px solid var(--js-line); border-radius:12px; overflow:hidden; }
    .stButton > button[kind="primary"] {
        background:linear-gradient(135deg,#e26748,#c94c34); color:white; border:0;
        box-shadow:0 8px 20px rgba(217,91,64,.22); font-weight:750;
    }
    .stButton > button[kind="primary"]:hover { background:linear-gradient(135deg,#c94c34,#b63f2b); color:white; }
    button:focus-visible,a:focus-visible,input:focus-visible,[role="radio"]:focus-visible {
        outline:3px solid #f2c66d !important; outline-offset:2px;
    }
    [data-testid="stExpander"],[data-testid="stAlert"],[data-testid="stVerticalBlockBorderWrapper"] { border-radius:14px; }
    .js-lockup { display:flex; align-items:center; gap:.65rem; }
    .js-mark { width:38px; height:38px; }
    .js-name { color:white; font-size:1.28rem; line-height:1; font-weight:850; letter-spacing:-.04em; }
    .js-name span { color:#f2c66d !important; }
    .js-tag { margin:.55rem 0 0 !important; color:#b9cbc5 !important; font-size:.77rem; line-height:1.4; }
    .js-masthead {
        display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.72rem 1rem .72rem .78rem;
        margin-bottom:.72rem; background:rgba(255,255,255,.65); border:1px solid var(--js-line);
        border-radius:18px; box-shadow:0 10px 36px rgba(23,50,46,.05);
    }
    .js-masthead .js-mark { width:48px; height:48px; }
    .js-wordmark { color:var(--js-ink); font-weight:850; letter-spacing:-.045em; font-size:1.55rem; line-height:1; }
    .js-wordmark span { color:var(--js-coral); }
    .js-kicker { margin-top:.32rem; color:#59716c; font-size:.67rem; font-weight:800; letter-spacing:.13em; }
    .js-promise { color:#47645e; font-size:.78rem; font-weight:700; white-space:nowrap; }
    .js-promise span { color:var(--js-coral); padding:0 .3rem; }
    .js-hero {
        position:relative; overflow:hidden; padding:clamp(1.7rem,4vw,3.4rem); margin-bottom:1.3rem;
        background:linear-gradient(135deg,#173c3a 0%,#102c2a 75%); border-radius:26px;
        box-shadow:0 18px 50px rgba(23,50,46,.17);
    }
    .js-hero:after {
        content:""; position:absolute; width:330px; height:330px; right:-105px; top:-148px;
        border-radius:50%; border:56px solid rgba(131,210,180,.12);
    }
    .js-eyebrow { color:#83d2b4; font-size:.72rem; font-weight:850; letter-spacing:.16em; }
    .js-hero h1 { color:white; font-size:clamp(2.25rem,5vw,4.7rem); line-height:.97; margin:.75rem 0 1rem; max-width:960px; }
    .js-hero h1 em { color:#f2c66d; font-style:normal; }
    .js-hero p { color:#d7e3df; font-size:1.06rem; line-height:1.6; max-width:820px; }
    .js-pills { display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1.15rem; }
    .js-pill {
        padding:.4rem .72rem; border:1px solid rgba(255,255,255,.16); border-radius:999px;
        color:#f8f5ed; font-size:.78rem; font-weight:700; background:rgba(255,255,255,.055);
    }
    .js-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; margin:1.25rem 0 1.6rem; }
    .js-card {
        height:100%; padding:1.2rem 1.2rem 1rem; background:rgba(255,255,255,.68);
        border:1px solid var(--js-line); border-radius:18px;
    }
    .js-card b { color:var(--js-coral); font-size:.72rem; letter-spacing:.12em; }
    .js-card h3 { margin:.4rem 0 .5rem; }
    .js-card p { color:#59716c; font-size:.9rem; line-height:1.55; }
    .boundary,.name-box {
        padding:1rem 1.1rem; margin:.75rem 0 1rem; border-radius:0 14px 14px 0;
        background:rgba(255,255,255,.62); color:#47645e;
    }
    .boundary { border-left:4px solid var(--js-mint); }
    .name-box { border-left:4px solid var(--js-coral); background:#fff0e9; color:#6f271b; }
    .js-decision {
        padding:1.3rem 1.4rem; margin:1rem 0; color:white; border-radius:18px;
        background:linear-gradient(135deg,#173c3a,#102c2a); box-shadow:0 12px 34px rgba(23,50,46,.14);
    }
    .js-decision b { color:#f2c66d; font-size:.78rem; letter-spacing:.14em; }
    .js-decision h2 { color:white; margin:.35rem 0 .4rem; }
    .js-decision p { color:#d7e3df; margin:.35rem 0 0; }
    .js-footer { margin-top:3.2rem; padding-top:1rem; border-top:1px solid var(--js-line); color:#617670; font-size:.76rem; text-align:center; }
    .js-footer span { color:var(--js-coral); padding:0 .38rem; }
    @media (max-width:1050px) { .js-grid{grid-template-columns:1fr} }
    @media (max-width:760px) { .js-promise{display:none}.js-hero{border-radius:20px}.block-container{padding-top:3.5rem} }
    @media (prefers-reduced-motion:reduce) { * { scroll-behavior:auto !important; transition:none !important; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def show_error(exc: Exception) -> None:
    """Show a calm error and keep tracebacks opt-in for trusted local debugging."""
    st.error(friendly_message(exc))
    if not isinstance(exc, (DataProblem, ValueError)) and os.getenv("TRACESIGNAL_DEBUG") == "1":
        with st.expander("Technical details"):
            st.code("".join(traceback.format_exception(exc)))


def masthead() -> None:
    mark = f'<img class="js-mark" src="{MARK_URI}" alt="">' if MARK_URI else ""
    st.markdown(
        f"""
        <div class="js-masthead">
          <div class="js-lockup">{mark}<div><div class="js-wordmark">Trace<span>Signal</span></div>
          <div class="js-kicker">ORDER → COMPARE → STRESS-TEST</div></div></div>
          <div class="js-promise">Observed transitions <span>◆</span> Path evidence <span>◆</span> Honest sensitivity</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        f'<div class="js-footer">TraceSignal v{__version__} <span>◆</span> describes logged '
        "sequences, not incremental value <span>◆</span> Part of the Signal suite <span>◆</span> "
        "AGPL-3.0-or-later</div>",
        unsafe_allow_html=True,
    )


def sidebar_lockup() -> None:
    mark = f'<img class="js-mark" src="{MARK_URI}" alt="">' if MARK_URI else "◇"
    st.sidebar.markdown(
        f'<div class="js-lockup">{mark}<div><div class="js-name">Trace<span>Signal</span></div>'
        '<p class="js-tag">Event-log sequence evidence—not a journey-map canvas.</p></div></div>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _demo() -> pd.DataFrame:
    return make_demo_events()


@st.cache_data(show_spinner="Analyzing observed journey sequences…")
def _analyze(events: pd.DataFrame, config: JourneyConfig):
    data = validate_event_log(events)
    return data, audit_event_log(data), analyze_journeys(data, config)


def _load_data() -> tuple[pd.DataFrame, str]:
    source = st.sidebar.radio("Data source", ["Fictional demonstration", "Upload my event log"])
    if source == "Fictional demonstration":
        return _demo(), "Deterministic fictional demonstration"
    upload = st.sidebar.file_uploader("Journey events · CSV or XLSX", type=["csv", "xlsx", "xlsm"])
    if upload is None:
        st.sidebar.info("Upload an event log. Until then, the fictional demonstration remains active.")
        return _demo(), "Fictional demonstration while upload is incomplete"
    try:
        return read_table(upload.name, upload.getvalue(), sheet_name="events"), "User-supplied local event log"
    except Exception as exc:
        # A failed upload must never silently fall back to demo data: stop the
        # run loudly so demo results cannot be mistaken for the user's data.
        st.sidebar.error(friendly_message(exc))
        st.error(
            f"**The uploaded file could not be read, so no analysis was run.** {friendly_message(exc)} "
            "Fix the file and upload it again, or switch the data source back to the fictional demonstration."
        )
        st.stop()
        raise  # unreachable; keeps the return type explicit for type checkers


def _config() -> JourneyConfig:
    st.sidebar.markdown("### Sequence contract")
    collapse = st.sidebar.checkbox("Collapse consecutive repeats", value=True)
    min_support = st.sidebar.slider("Minimum journeys per reported path", 2, 30, 5)
    outcome_support = st.sidebar.slider("Minimum transitions per outcome cell", 2, 50, 10)
    bootstrap = st.sidebar.select_slider("Removal bootstrap repetitions", options=[100, 200, 300, 500], value=200)
    confidence = st.sidebar.select_slider("Interval level", options=[0.90, 0.95, 0.99], value=0.95)
    return JourneyConfig(
        collapse_consecutive=collapse,
        min_path_journeys=min_support,
        min_outcome_transition_support=outcome_support,
        bootstrap_repetitions=bootstrap,
        confidence_level=confidence,
    )


def _metric_value(frame: pd.DataFrame, measure: str):
    return frame.loc[frame["measure"] == measure, "value"].iloc[0]


def _hero() -> None:
    st.markdown(
        """
        <section class="js-hero">
          <div class="js-eyebrow">OBSERVED JOURNEY SEQUENCE EVIDENCE</div>
          <h1>Where do journeys flow, stall, and end—<em>and how stable is that story?</em></h1>
          <p>Turn ordered case-level events into an auditable descriptive record: inspect touchpoint transitions,
          compare relative early/middle/late roles and complete paths, locate terminal drop-off, and stress-test a
          transparent first-order Markov description.</p>
          <div class="js-pills"><span class="js-pill">strict event ordering</span>
          <span class="js-pill">transition intervals</span><span class="js-pill">relative sequence roles</span>
          <span class="js-pill">path + subgroup comparison</span><span class="js-pill">depth attrition</span>
          <span class="js-pill">clustered removal sensitivity</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def page_welcome() -> None:
    _hero()
    st.warning(CAUTION)
    st.markdown(
        '<div class="boundary"><strong>Non-negotiable boundary:</strong> TraceSignal describes logged sequences. '
        "It does not identify incremental channel value, causes of conversion, customer intent, or the effect of removing "
        "a real touchpoint. Interventions belong in ExperimentSignal.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="js-grid">
          <div class="js-card"><b>01 · CONTRACT</b><h3>Event logs, not workshop maps</h3><p>Every result comes from
          ordered case-level events. Without defensible journey IDs, touchpoints, timestamps, and outcomes, analysis stops.</p></div>
          <div class="js-card"><b>02 · COMPARE</b><h3>Sequence position is relative</h3><p>Early, middle, and late
          mean thirds of each observed journey—not universal funnel stages, customer psychology, or a hidden ontology.</p></div>
          <div class="js-card"><b>03 · STRESS-TEST</b><h3>Removal is sensitivity</h3><p>State deletion and
          renormalization show model dependence. They do not simulate a real shutdown or allocate causal channel credit.</p></div>
        </div>
        """,
        unsafe_allow_html=True,
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
    st.title("Data & sequence contract")
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
    )


def _sankey(transitions: pd.DataFrame, minimum_count: int) -> go.Figure:
    filtered = transitions.loc[
        (transitions["transitions"] >= minimum_count) & ~transitions["from_state"].isin(["CONVERSION", "DROP_OFF"])
    ].copy()
    states = list(dict.fromkeys([*filtered["from_state"], *filtered["to_state"]]))
    index = {state: position for position, state in enumerate(states)}
    node_colors = [
        COLORS["mint"]
        if state == "CONVERSION"
        else COLORS["coral"]
        if state == "DROP_OFF"
        else COLORS["gold"]
        if state == "START"
        else "#4A746D"
        for state in states
    ]
    return go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(label=states, color=node_colors, pad=16, thickness=17),
            link=dict(
                source=filtered["from_state"].map(index),
                target=filtered["to_state"].map(index),
                value=filtered["transitions"],
                color="rgba(23,60,58,.20)",
            ),
        )
    ).update_layout(height=620, margin=dict(l=15, r=15, t=25, b=15))


def page_transitions(result) -> None:
    st.title("Transitions & positional roles")
    st.caption("Empirical first-order transitions include START and the observed terminal outcome state.")
    minimum = st.slider("Minimum transitions shown in flow", 1, 100, 12)
    st.plotly_chart(_sankey(result.transitions, minimum), width="stretch")
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
        color_discrete_map={"Early": COLORS["teal"], "Middle": COLORS["gold"], "Late": COLORS["coral"]},
    )
    figure.update_layout(yaxis_tickformat=".0%", legend_orientation="h", legend_y=1.12, margin=dict(t=35))
    st.plotly_chart(figure, width="stretch")
    st.dataframe(result.roles, width="stretch", hide_index=True)
    st.warning("Associated conversion rates condition on the touchpoint and relative role; they are not touchpoint effects.")


def page_dropoff(result) -> None:
    st.title("Drop-off & journey depth")
    st.markdown(
        '<div class="boundary"><strong>Drop-off definition:</strong> a journey is a drop-off when its supplied converted flag is 0. '
        "A touchpoint receives a terminal drop-off only when it is the final observed touchpoint in that journey.</div>",
        unsafe_allow_html=True,
    )
    figure = px.bar(
        result.dropoff.sort_values("dropoff_after_visit_rate"),
        x="dropoff_after_visit_rate",
        y="touchpoint",
        orientation="h",
        error_x=result.dropoff.sort_values("dropoff_after_visit_rate")["dropoff_ci_high"]
        - result.dropoff.sort_values("dropoff_after_visit_rate")["dropoff_after_visit_rate"],
        error_x_minus=result.dropoff.sort_values("dropoff_after_visit_rate")["dropoff_after_visit_rate"]
        - result.dropoff.sort_values("dropoff_after_visit_rate")["dropoff_ci_low"],
        labels={"dropoff_after_visit_rate": "Terminal nonconversion endings / journeys visiting", "touchpoint": "Touchpoint"},
        color_discrete_sequence=[COLORS["coral"]],
    )
    figure.update_layout(xaxis_tickformat=".0%", margin=dict(t=25))
    st.plotly_chart(figure, width="stretch")
    st.dataframe(result.dropoff, width="stretch", hide_index=True)

    st.markdown("### Observed depth survival")
    depth_figure = px.line(
        result.depth,
        x="depth",
        y="share_reaching",
        markers=True,
        labels={"depth": "Touchpoint depth", "share_reaching": "Journeys reaching at least this depth"},
        color_discrete_sequence=[COLORS["teal"]],
    )
    depth_figure.update_layout(yaxis_tickformat=".0%", margin=dict(t=25))
    st.plotly_chart(depth_figure, width="stretch")
    st.dataframe(result.depth, width="stretch", hide_index=True)


def page_paths(result) -> None:
    st.title("Observed path comparison")
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
            color_continuous_scale=[[0, COLORS["paper"]], [0.5, COLORS["mint"]], [1, COLORS["teal"]]],
        )
        figure.update_layout(yaxis_tickformat=".0%", margin=dict(t=25))
        st.plotly_chart(figure, width="stretch")
        st.dataframe(supported, width="stretch", hide_index=True)

    st.markdown("### Subgroup sequence summary")
    st.dataframe(result.subgroup_summary, width="stretch", hide_index=True)
    selected_group = st.selectbox("Inspect supported paths for subgroup", list(result.subgroup_summary["subgroup"]))
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
    st.title("Descriptive Markov removal sensitivity")
    st.markdown(
        '<div class="name-box"><strong>Not causal attribution:</strong> each touchpoint is deleted from the fitted first-order '
        "transition matrix and remaining row probabilities are renormalized. The result answers how this model changes—not what would "
        "happen if the business removed that touchpoint.</div>",
        unsafe_allow_html=True,
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
                COLORS["teal"] if value >= 0 else COLORS["coral"]
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
        xaxis_title="Relative change in fitted conversion probability after state deletion",
        yaxis_title="Touchpoint",
        xaxis_tickformat=".0%",
        height=520,
        margin=dict(t=25),
    )
    st.plotly_chart(figure, width="stretch")
    st.dataframe(result.markov_removal, width="stretch", hide_index=True)
    st.caption("Negative sensitivity can occur after renormalization and is not evidence that a real touchpoint is harmful.")

    st.markdown("### First-order memory diagnostic")
    st.write(
        "Conditional mutual information tests descriptively whether the previous state still contains information about the next state after the current touchpoint is known. Larger values flag possible first-order misspecification; small samples bias this diagnostic upward."
    )
    st.dataframe(result.memory_diagnostic, width="stretch", hide_index=True)


def page_evidence(audit, result, source_label: str) -> None:
    st.title("Evidence pack")
    metadata = {
        "app": "TraceSignal",
        "version": __version__,
        "name_status": "Informally screened working name; not legally cleared, and this record is not a trademark opinion.",
        "data_source": source_label,
        "analysis_type": "Observed event-log sequence analysis",
        "markov_boundary": "First-order descriptive removal sensitivity; not causal attribution",
        "role_boundary": "Early/middle/late are relative observed positions",
        "intervention_handoff": "ExperimentSignal",
    }
    workbook = build_evidence_workbook(metadata=metadata, audit=audit, result=result)
    st.download_button(
        "Download TraceSignal evidence pack",
        workbook,
        "tracesignal-evidence-pack.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    c1, c2, c3 = st.columns(3)
    c1.download_button("Transitions CSV", dataframe_csv_bytes(result.transitions), "tracesignal-transitions.csv", "text/csv")
    c2.download_button("Paths CSV", dataframe_csv_bytes(result.paths), "tracesignal-paths.csv", "text/csv")
    c3.download_button(
        "Removal sensitivity CSV",
        dataframe_csv_bytes(result.markov_removal),
        "tracesignal-removal-sensitivity.csv",
        "text/csv",
    )
    st.json(metadata)
    st.info("The export contains observed sequence evidence and model diagnostics, not a journey diagram or causal channel-credit allocation.")


def page_methods() -> None:
    st.title("Methods & boundaries")
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


sidebar_lockup()
st.sidebar.caption(f"Event-log sequence evidence · v{__version__}")
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
event_frame, source = _load_data()
config = _config()
journey_count = f"{event_frame['journey_id'].nunique():,}" if "journey_id" in event_frame else "unvalidated"
st.sidebar.caption(f"Active data · {journey_count} journeys × {len(event_frame):,} events")
st.sidebar.divider()
st.sidebar.caption("Local mode · no telemetry · no external AI calls · uploads stay in this Python process")

masthead()
try:
    if page == "Welcome":
        page_welcome()
    elif page == "1 · Data & sequence contract":
        page_data(event_frame, source, config)
    elif page == "Methods & boundaries":
        page_methods()
    else:
        validated, data_audit, analysis = _analyze(event_frame, config)
        if page == "2 · Transitions & roles":
            page_transitions(analysis)
        elif page == "3 · Drop-off & depth":
            page_dropoff(analysis)
        elif page == "4 · Path comparison":
            page_paths(analysis)
        elif page == "5 · Markov removal sensitivity":
            page_markov(analysis)
        elif page == "6 · Evidence pack":
            page_evidence(data_audit, analysis, source)
except Exception as exc:
    show_error(exc)
footer()

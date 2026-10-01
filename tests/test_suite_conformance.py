from pathlib import Path

from streamlit.testing.v1 import AppTest

from tracesignal import __version__


ROOT = Path(__file__).parents[1]
APP = str(ROOT / "app.py")
UI = ROOT / "src" / "tracesignal" / "ui"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_shared_signal_shell_renders() -> None:
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()

    assert not app.exception, [error.value for error in app.exception]
    body = "\n".join(str(item.value) for item in app.markdown)
    sidebar = "\n".join(str(item.value) for item in app.sidebar.markdown)
    assert "ORDER → COMPARE → STRESS-TEST" in body
    assert "OBSERVED JOURNEY SEQUENCE EVIDENCE" in body
    assert "Where do journeys flow, stall, and end" in body
    assert f"Trace Signal v{__version__}" in body
    assert "describes logged sequences, not incremental value" in body
    assert "Part of the Signal suite" in body
    assert "AGPL-3.0-or-later" in body
    assert "sg-mast" in body  # the shared Signal masthead
    assert "sg-foot" in body  # the shared Signal footer
    assert "Event-log sequence evidence—not a journey-map canvas." in sidebar
    assert "sg-side" in sidebar  # the shared Signal sidebar lockup


def test_app_uses_shared_signal_theme_instead_of_pasted_styles() -> None:
    standalone = _read("app.py")
    ui_source = (UI / "app.py").read_text(encoding="utf-8")
    theme = (UI / "signal_theme.py").read_text(encoding="utf-8")
    assert 'st.set_page_config(**sig.page_config("trace"))' in standalone
    assert "sig.apply(NS)" in ui_source
    assert "template=sig.template(NS)" in ui_source
    # sig.chart sets the per-app template and theme=None, so Streamlit's chart theme cannot replace the palette.
    assert "sig.chart(NS, " in ui_source
    assert "st.plotly_chart(" not in ui_source
    assert "<style>" not in standalone + ui_source
    for old_colour in ("#173c3a", "#d95b40", "#83d2b4", "#f2c66d", "#f8f5ed", "#17322e", "#102c2a", "#4a746d"):
        assert old_colour not in (standalone + ui_source).lower()
    assert (UI / "assets" / "marks" / "tracesignal-mark-64.png").exists()
    assert ":focus-visible" in theme
    assert "@media (max-width:760px)" in theme
    assert "@media (prefers-reduced-motion:reduce)" in theme
    assert "friendly_message" in ui_source
    assert "Event logs, not workshop maps" in ui_source
    assert "Journey" + "Signal" not in standalone + ui_source  # the retired working title must not resurface


def test_readme_retains_full_product_contract_in_common_structure() -> None:
    readme = _read("README.md")
    headings = (
        "## Read this first",
        "## Supported scope",
        "## Try it in three minutes",
        "## Event-log contract",
        "## Method and interpretation",
        "## Evidence pack",
        "## Run locally",
        "## Privacy",
        "## Development checks",
        "## Relationship to the Signal suite",
        "## Originality and license",
    )
    assert all(heading in readme for heading in headings)
    for boundary in (
        "not a journey-diagram maker",
        "not universal funnel stages",
        "conditional mutual information",
        "cluster-bootstrap",
        "not legally cleared",
        "not legal advice",
    ):
        assert boundary in readme


def test_readme_name_note_is_modest_not_alarmist() -> None:
    readme = _read("README.md")
    assert "Working-name status" in readme
    assert "DO NOT PUBLISH" not in readme
    assert "WORKING NAME ONLY" not in readme
    assert "trademark opinion" in readme
    assert "github.com/UlrikErlingsen/journey-path-analysis" in readme


def test_local_runtime_is_no_telemetry_and_uses_dedicated_port() -> None:
    config = _read(".streamlit/config.toml")
    dockerfile = _read("Dockerfile")
    launcher = _read("run_app.command")
    assert "gatherUsageStats = false" in config
    assert 'base = "light"' in config
    assert "headless = true" in config
    assert 'fileWatcherType = "none"' in config
    assert "maxUploadSize = 50" in config
    assert 'primaryColor = "#aa5d83"' in config  # Signal Customer family, 600 step
    assert "USER tracesignal" in dockerfile
    assert "chown" not in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "8585/_stcore/health" in dockerfile
    assert "[8585, *range(8501, 8600)]" in launcher
    assert "--browser.gatherUsageStats=false" in launcher
    assert "TRACESIGNAL_MAX_UPLOAD_MB" in launcher
    assert 'TRACESIGNAL_MAX_UPLOAD_MB:-50' in launcher


def test_ci_runs_tests_lint_and_build_without_a_publish_job() -> None:
    workflow = _read(".github/workflows/tests.yml")
    assert "python -m pytest" in workflow
    assert "python -m ruff check ." in workflow
    assert "python -m build" in workflow
    assert "publish" not in workflow.lower()

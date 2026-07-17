from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_app_uses_signal_suite_shell_with_tracesignal_branding() -> None:
    app = _read("app.py")
    for token in (
        "#173C3A",
        "#D95B40",
        "#83D2B4",
        "#F2C66D",
        "#F8F5ED",
        "js-masthead",
        "js-hero",
        "js-footer",
        "MARK_URI",
        "Trace<span>Signal</span>",
    ):
        assert token in app
    assert "Where do journeys flow, stall, and end" in app
    assert "Event logs, not workshop maps" in app
    assert "Journey" + "Signal" not in app  # the retired working title must not resurface
    normalized = app.replace("'\n        \"", "").replace('"\n        "', "")
    assert (
        'TraceSignal v{__version__} <span>◆</span> describes logged '
        'sequences, not incremental value <span>◆</span> Part of the Signal suite <span>◆</span> '
        'AGPL-3.0-or-later'
    ) in normalized


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
    assert 'primaryColor = "#D95B40"' in config
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

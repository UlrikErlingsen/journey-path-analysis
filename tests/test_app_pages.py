from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).parents[1] / "app.py")
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


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_fictional_event_log(page: str) -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    app.sidebar.radio[0].set_value(page).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.sidebar.radio[0].value == page
    captions = " ".join(str(item.value).lower() for item in app.sidebar.caption)
    assert "event-log sequence evidence" in captions


def test_welcome_rejects_diagram_and_causal_interpretation() -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    body = "\n".join(str(markdown.value) for markdown in app.markdown)
    assert "Event logs, not workshop maps" in body
    assert "does not identify incremental channel value" in body
    assert "Experiment Signal" in body
    assert "Trace Signal" in body
    assert "Journey" + "Signal" not in body  # the retired working title must not resurface
    assert "Journey" + " Signal" not in body

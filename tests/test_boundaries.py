from pathlib import Path


ROOT = Path(__file__).parents[1]


def _product_text() -> str:
    paths = [
        ROOT / "app.py",
        ROOT / "src" / "tracesignal" / "ui" / "app.py",
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_product_and_package_name_are_consistent() -> None:
    from tracesignal import __version__

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "tracesignal"' in pyproject
    assert f'version = "{__version__}"' in pyproject
    assert "TraceSignal" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_name_screen_is_honest_without_overclaiming() -> None:
    text = _product_text().lower()
    assert "not legally cleared" in text
    assert "not legal advice" in text
    assert "tracesignal" in text


def test_markov_removal_is_never_presented_as_causal_attribution() -> None:
    text = _product_text().lower()
    assert "not causal attribution" in text
    assert "does not estimate what would happen" in text or "not a real intervention" in text
    assert "experimentsignal" in text


def test_app_is_more_than_a_journey_diagram() -> None:
    text = _product_text().lower()
    assert "not a journey-diagram maker" in text
    assert "conditional mutual information" in text
    assert "cluster-bootstrap" in text or "clustered resampling" in text


def test_relative_roles_are_not_universal_stages() -> None:
    text = _product_text().lower()
    assert "relative" in text
    assert "not universal funnel stages" in text


def test_originality_boundary_excludes_course_material() -> None:
    text = (ROOT / "docs" / "sources-and-originality.md").read_text(encoding="utf-8")
    assert (
        "It does not reproduce lecture slides, notes, cases, exercises, diagrams, assessment material, "
        "datasets, questionnaire wording, or institution-specific frameworks" in text
    )
    assert "general topics encountered in education only define the problem domain" in text
    assert "fictional" in text.lower()
    assert "independently" in text.lower()

from __future__ import annotations

import pytest

from tracesignal import JourneyConfig, analyze_journeys, validate_event_log
from tracesignal.examples import make_demo_events


@pytest.fixture(scope="session")
def demo_events():
    return make_demo_events()


@pytest.fixture(scope="session")
def validated(demo_events):
    return validate_event_log(demo_events)


@pytest.fixture(scope="session")
def config():
    return JourneyConfig(bootstrap_repetitions=100, min_path_journeys=5)


@pytest.fixture(scope="session")
def result(validated, config):
    return analyze_journeys(validated, config)

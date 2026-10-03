"""Trace Signal: descriptive event-log sequence analysis."""

from .analysis import JourneyResult, analyze_journeys
from .design import JourneyConfig, ValidatedJourneyData, validate_event_log
from .errors import DataProblem

__all__ = [
    "DataProblem",
    "JourneyConfig",
    "JourneyResult",
    "ValidatedJourneyData",
    "analyze_journeys",
    "validate_event_log",
]

__version__ = "1.2.0"

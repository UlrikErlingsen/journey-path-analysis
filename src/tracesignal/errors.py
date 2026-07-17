"""User-facing TraceSignal errors."""


class DataProblem(ValueError):
    """Raised when an event log cannot support a defensible sequence analysis."""


def friendly_message(exc: Exception) -> str:
    """Return a useful user-facing message without exposing an internal traceback."""
    if isinstance(exc, DataProblem):
        return str(exc)
    if isinstance(exc, ValueError):
        return f"TraceSignal could not use that setting or value: {exc}"
    return (
        "TraceSignal could not complete that step. Check the event-log contract and try again. "
        "Set TRACESIGNAL_DEBUG=1 only in a trusted local session to inspect technical details."
    )

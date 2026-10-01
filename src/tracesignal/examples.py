"""Deterministic, wholly fictional Trace Signal event logs."""

from __future__ import annotations

import numpy as np
import pandas as pd


CONVERSION = "CONVERSION"
DROP_OFF = "DROP_OFF"

TRANSITIONS: dict[str, tuple[tuple[str, float], ...]] = {
    "Paid social": (
        ("Content article", 0.34),
        ("Product page", 0.19),
        ("Organic search", 0.08),
        ("Email", 0.06),
        (DROP_OFF, 0.33),
    ),
    "Organic search": (
        ("Product page", 0.34),
        ("Content article", 0.23),
        ("Comparison tool", 0.15),
        ("Pricing page", 0.09),
        (DROP_OFF, 0.19),
    ),
    "Referral": (
        ("Product page", 0.37),
        ("Sales chat", 0.15),
        ("Pricing page", 0.15),
        ("Content article", 0.12),
        (DROP_OFF, 0.21),
    ),
    "Email": (
        ("Product page", 0.30),
        ("Content article", 0.18),
        ("Webinar", 0.18),
        ("Pricing page", 0.12),
        (DROP_OFF, 0.22),
    ),
    "Content article": (
        ("Product page", 0.31),
        ("Comparison tool", 0.20),
        ("Email", 0.12),
        ("Webinar", 0.10),
        ("Organic search", 0.07),
        (DROP_OFF, 0.20),
    ),
    "Webinar": (
        ("Sales chat", 0.30),
        ("Pricing page", 0.24),
        ("Product page", 0.13),
        ("Email", 0.08),
        (CONVERSION, 0.10),
        (DROP_OFF, 0.15),
    ),
    "Product page": (
        ("Pricing page", 0.27),
        ("Comparison tool", 0.20),
        ("Sales chat", 0.13),
        ("Content article", 0.08),
        ("Checkout", 0.16),
        (DROP_OFF, 0.16),
    ),
    "Comparison tool": (
        ("Pricing page", 0.31),
        ("Product page", 0.18),
        ("Sales chat", 0.20),
        ("Checkout", 0.12),
        (DROP_OFF, 0.19),
    ),
    "Sales chat": (
        ("Pricing page", 0.24),
        ("Checkout", 0.34),
        ("Product page", 0.10),
        (CONVERSION, 0.16),
        (DROP_OFF, 0.16),
    ),
    "Pricing page": (
        ("Checkout", 0.44),
        ("Sales chat", 0.15),
        ("Comparison tool", 0.10),
        (CONVERSION, 0.08),
        (DROP_OFF, 0.23),
    ),
    "Checkout": (
        (CONVERSION, 0.64),
        (DROP_OFF, 0.23),
        ("Pricing page", 0.08),
        ("Sales chat", 0.05),
    ),
}

STARTS: dict[str, tuple[tuple[str, float], ...]] = {
    "New prospects": (
        ("Paid social", 0.38),
        ("Organic search", 0.27),
        ("Content article", 0.20),
        ("Referral", 0.10),
        ("Email", 0.05),
    ),
    "Returning evaluators": (
        ("Organic search", 0.27),
        ("Email", 0.24),
        ("Product page", 0.20),
        ("Comparison tool", 0.16),
        ("Referral", 0.13),
    ),
    "Existing customers": (
        ("Email", 0.34),
        ("Referral", 0.20),
        ("Product page", 0.18),
        ("Webinar", 0.16),
        ("Organic search", 0.12),
    ),
}


def _draw(rng: np.random.Generator, options: tuple[tuple[str, float], ...], subgroup: str) -> str:
    labels = [label for label, _ in options]
    probabilities = np.array([probability for _, probability in options], dtype=float)
    if subgroup == "Existing customers":
        probabilities = np.array(
            [probability * 1.25 if label == CONVERSION else probability * 0.82 if label == DROP_OFF else probability
             for label, probability in zip(labels, probabilities, strict=True)]
        )
    elif subgroup == "Returning evaluators":
        probabilities = np.array(
            [probability * 1.12 if label == CONVERSION else probability * 0.93 if label == DROP_OFF else probability
             for label, probability in zip(labels, probabilities, strict=True)]
        )
    probabilities /= probabilities.sum()
    return str(rng.choice(labels, p=probabilities))


def make_demo_events(seed: int = 6420) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-01-01", tz="UTC")
    rows: list[dict[str, object]] = []
    subgroups = ("New prospects", "Returning evaluators", "Existing customers")

    for journey_index in range(720):
        subgroup = subgroups[journey_index % len(subgroups)]
        customer_index = journey_index if journey_index < 520 else journey_index - 420
        current = _draw(rng, STARTS[subgroup], subgroup)
        sequence: list[str] = []
        outcome = DROP_OFF
        for _ in range(15):
            sequence.append(current)
            next_state = _draw(rng, TRANSITIONS[current], subgroup)
            if next_state in {CONVERSION, DROP_OFF}:
                outcome = next_state
                break
            current = next_state
        converted = int(outcome == CONVERSION)
        value = float(np.round(rng.lognormal(mean=5.45, sigma=0.38), 2)) if converted else 0.0
        journey_start = start + pd.to_timedelta(int(rng.integers(0, 330)), unit="D")
        elapsed_minutes = 0
        event_order = 0
        for touchpoint in sequence:
            elapsed_minutes += int(max(5, rng.gamma(shape=1.8, scale=420)))
            rows.append(
                {
                    "journey_id": f"JOURNEY-{journey_index + 1:04d}",
                    "customer_id": f"CUSTOMER-{customer_index + 1:04d}",
                    "timestamp": (journey_start + pd.to_timedelta(elapsed_minutes, unit="m")).isoformat(),
                    "event_order": event_order,
                    "touchpoint": touchpoint,
                    "converted": converted,
                    "journey_value": value,
                    "subgroup": subgroup,
                }
            )
            event_order += 1
            if rng.random() < 0.09:
                elapsed_minutes += int(rng.integers(2, 25))
                rows.append(
                    {
                        "journey_id": f"JOURNEY-{journey_index + 1:04d}",
                        "customer_id": f"CUSTOMER-{customer_index + 1:04d}",
                        "timestamp": (journey_start + pd.to_timedelta(elapsed_minutes, unit="m")).isoformat(),
                        "event_order": event_order,
                        "touchpoint": touchpoint,
                        "converted": converted,
                        "journey_value": value,
                        "subgroup": subgroup,
                    }
                )
                event_order += 1
    return pd.DataFrame(rows).sort_values(["journey_id", "timestamp", "event_order"], kind="mergesort").reset_index(drop=True)


def make_starter_template() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "journey_id": "JOURNEY-001",
                "customer_id": "CUSTOMER-001",
                "timestamp": "2026-01-01T09:00:00Z",
                "event_order": 1,
                "touchpoint": "Organic search",
                "converted": 1,
                "journey_value": 250.0,
                "subgroup": "Declared cohort A",
            },
            {
                "journey_id": "JOURNEY-001",
                "customer_id": "CUSTOMER-001",
                "timestamp": "2026-01-03T13:00:00Z",
                "event_order": 2,
                "touchpoint": "Product page",
                "converted": 1,
                "journey_value": 250.0,
                "subgroup": "Declared cohort A",
            },
        ]
    )

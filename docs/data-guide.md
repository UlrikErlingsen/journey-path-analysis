# Data guide

## Unit and ordering

One row is one observed touchpoint event. `journey_id` defines the case and must reflect a declared inactivity rule, transaction episode, campaign window, or other defensible boundary. Rows are ordered by UTC-normalized `timestamp`, then numeric `event_order`. Tied timestamps without an explicit event order are rejected because alphabetical or file-row ordering would invent a path.

## Required fields

| Field | Contract |
|---|---|
| `journey_id` | nonblank case identifier |
| `timestamp` | parseable date/datetime |
| `touchpoint` | nonblank observed state; `START`, `CONVERSION`, and `DROP_OFF` are reserved |
| `converted` | 0 or 1, constant within the journey |

Optional `customer_id`, `subgroup`, and `journey_value` must be stable within a journey. Value must be finite and non-negative. If `customer_id` is absent, bootstrap resampling treats journeys as independent clusters.

## Consecutive repeats

The default collapses immediately repeated touchpoints within a journey. This prevents refreshes or repeated instrumentation calls from dominating transitions while retaining later revisits after another state. The evidence pack records the setting and the number of collapsed events. Turn it off when repeats represent substantively different actions.

## Outcome and censoring

`converted=0` means no conversion was observed under the supplied journey definition and observation window. It does not prove abandonment or dissatisfaction. Journeys still active at extraction time are right-censored; exclude them, provide a mature cohort, or interpret terminal drop-off cautiously.

## Taxonomy and stitching audit

Before interpretation, document:

- how journey boundaries and conversion windows were set;
- identity stitching across devices, accounts, cookies, and offline systems;
- touchpoint naming, aggregation, and channel changes over time;
- instrumentation gaps, duplicate handling, bots, internal traffic, and consent filtering;
- exposure versus engagement semantics;
- time-zone normalization and late-arriving events;
- whether outcome and value are complete for every cohort.

The app cannot recover unlogged exposures or correct a bad identity graph.

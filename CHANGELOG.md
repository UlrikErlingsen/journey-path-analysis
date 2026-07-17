# Changelog

## 1.0.0 — 2026-07-17

First public release, under the name **TraceSignal** (the previous internal working title was retired after a name screen found active conflicting "Journey Signal™" use; TraceSignal was informally screened on 17 July 2026 — see `docs/name-screen.md`).

### Analysis

- Strict event-log validation and ordering contract with explicit tie handling and stable journey-level fields.
- Empirical transitions with Wilson intervals, next-state entropy, relative positional roles, timing, terminal drop-off, and depth attrition.
- Supported complete-path, subgroup, and outcome-conditioned sequence comparison; subgroup path shares are within-subgroup.
- Journey durations use the full pre-collapse timestamps, so trailing repeated events count toward the observed window.
- The outcome-conditioned transition table requires a declared minimum transition count in both outcome groups (default 10, floor 2) before a difference is ranked, so sparse cells cannot top the table.
- First-order absorbing Markov state-deletion sensitivity with cluster-bootstrap intervals and a conditional-mutual-information memory diagnostic. The fitted chain reproduces the observed conversion rate by construction, so no "calibration gap" metric is reported.
- Deterministic fictional examples, XLSX evidence export, and separate CSV downloads.

### Security hardening

- Every exported table (CSV and every XLSX sheet) is formula-neutralized: cell values and column headers beginning with `=`, `+`, `-`, or `@` are prefixed with `'`, and ASCII control characters are stripped.
- `defusedxml` hardens workbook XML parsing.
- Uploads gain byte, expansion, row, and column caps (50 MB file / 200 MB expanded workbook / 250,000 rows / 200 columns), and the Streamlit upload limit is 50 MB.
- A failed upload stops the run with a visible error instead of silently analyzing demonstration data.
- The Docker image keeps application code root-owned; the runtime user only gets a writable home.

### Shell

- Signal-suite local-first shell: no-telemetry defaults, resilient local launcher on preferred port 8585, health-checked non-root container, CI, and suite-conformance tests.

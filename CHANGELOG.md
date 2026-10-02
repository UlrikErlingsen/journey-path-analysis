# Changelog

## 1.1.0 — 2026-10-02

Signal brand refresh and Signal Hub entry point. The analysis, statistics, event-log contract and exports are unchanged.

### Brand

- Display name written **Trace Signal** (with a space) in the app, README, docs, launchers and metadata. Package, file and environment-variable names stay `tracesignal` / `TRACESIGNAL_*`. The name screen still covers the exact string “TraceSignal” only; no new clearance is claimed.
- The app uses the shared `signal_theme` module (Organic Signal design, Customer family colour `#aa5d83`, Figtree): sidebar lockup, masthead, hero, cards, notes, footer, Plotly template and the mark as favicon replace the pasted styles. Every chart uses the Trace Signal template through `sig.chart`, with the old palette mapped to theme tokens and the same chart meaning.
- New banner, social preview and marks in `assets/`; the old banner SVG is removed. `.streamlit/config.toml` uses the family colours.
- README follows the Signal template; bug-report, feature-request and config issue templates added.

### Signal Hub contract

- `tracesignal.ui` exposes `APP_INFO` and `render()`, so Signal Hub can embed the app; `app.py` is now a thin standalone entry point.
- All session-state and widget keys are namespaced `trace:` (including the page selector and the sidebar sequence-contract controls). A failed upload still stops the run instead of falling back to the demonstration.
- `streamlit` and `plotly` moved to a `ui` extra (also in `test`); the analysis core installs without them. `requirements.txt` still lists everything.
- New tests: no Streamlit/Plotly import outside `tracesignal.ui`, the core imports in a fresh interpreter without them, `render()` runs from a script without a page config, and every widget key is namespaced.

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

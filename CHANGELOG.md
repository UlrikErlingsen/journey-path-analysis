# Changelog

## 1.2.0 — 2026-10-03

### Larger datasets

- Larger datasets: run locally (standalone, a local Signal Hub or an internal deployment), Trace Signal no longer sets any limit on file size, rows, columns, events or touchpoints; memory is the limit. The former 50 MB upload, 200 MB expanded-workbook, 250,000-row, 200-column and 60-touchpoint limits, plus a 300-repetition bootstrap cap, now apply only in the public demo (`SIGNAL_PUBLIC=1`), where messages say they are demo limits. All caps live in the new `tracesignal.limits` module.
- Streamlit's upload cap is 10,000 MB: `.streamlit/config.toml`, `TRACESIGNAL_MAX_UPLOAD_MB` (default 10000, was 50) in both launchers, and `STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10000` in the Docker image.
- Running out of memory while loading or analyzing is reported as a plain "not enough memory on this computer" message.
- The analysis is computed column-wise instead of journey by journey: sequence preparation, transitions, drop-off, depth, paths, the memory diagnostic and the clustered Markov bootstrap (cluster transition counts weighted by how often each cluster is drawn). Results are identical to 1.1.0 on the same data and seed; the fictional demo analyzes about ten times faster. Validation strips and sorts on integer codes.
- The app reads an upload once and keeps validation and analysis in the session instead of re-reading, re-hashing and copying the log on every rerun.
- Long on-screen tables show their first 1,000 rows with a note. Every table remains complete in the downloads: new Journeys, Event positions and Subgroup paths CSVs, and a workbook sheet too large for Excel points to its CSV. Large evidence files are built when their button is clicked.
- Measured on a 24-thread desktop: a 5-million-event log (1 million journeys, 334 MB) loads in about 5 seconds, validates in about 17 seconds and is fully analyzed with 200 bootstrap repetitions in about 32 seconds, with a peak of about 3.2 GB.

### Suite

- Suite: Rival, Reach, Learn and Blueprint Signal added to the suite table.

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

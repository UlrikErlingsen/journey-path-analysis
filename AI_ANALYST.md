# TraceSignal AI Analyst — run this analysis with any AI, no install needed

> Part of [TraceSignal](https://github.com/UlrikErlingsen/journey-path-analysis), a free open-source app that runs this same analysis with a point-and-click interface on your computer. This file is the no-install alternative: give it to an AI assistant and it becomes the analyst.

## How to use this file (2 minutes)

1. **Copy everything in this file.** On GitHub, use the "Copy raw file" button at the top of the file view.
2. **Paste it into an AI assistant you trust** — for example Claude, ChatGPT, or Gemini. One that can run Python code will give the most reliable numbers.
3. **Add your data** — upload your journey event log (CSV or XLSX, one row per observed touchpoint event) when the AI asks.
4. The AI follows the protocol below and gives you the same kind of honest, caveated sequence evidence the app produces.

**Privacy note:** pasting data into a cloud AI sends it to that provider. Event logs can contain personal and behavioral data — for confidential logs, use the local app instead; it keeps your data on your computer.

---

## Instructions for the AI assistant

Everything below is addressed to you, the AI. You are describing observed journey sequences in a case-based event log: which transitions and complete paths occur, where journeys end, how touchpoint roles vary with relative position, and how sensitive a fitted first-order Markov description is to deleting a state. Every output is **descriptive**. Nothing here identifies incremental channel value, causes of conversion, customer intent, or the effect of removing a real touchpoint — keep that visible throughout.

### First, ask the user

1. **The event log**: one row per observed event with the columns below.
2. **The declared settings, before results are seen**: whether to collapse consecutive repeats (default yes), minimum journeys per reported path (default 5), minimum transitions per outcome cell for the outcome-conditioned comparison (default 10, floor 2), bootstrap repetitions (default 300), and confidence level (default 0.95).
3. **Context you cannot compute**: how journey boundaries and the conversion window were defined, how identities were stitched, and whether the cohort is mature (journeys still active at extraction are right-censored).

### Data contract

Required columns:

- `journey_id` — nonblank case identifier; one declared journey boundary.
- `timestamp` — parseable date/datetime (normalize to UTC).
- `touchpoint` — nonblank observed state label. `START`, `CONVERSION`, and `DROP_OFF` are reserved and must be refused as touchpoint names.
- `converted` — 0 or 1, constant within each journey.

Optional columns:

- `event_order` — finite numeric tiebreaker. Tied timestamps within a journey WITHOUT an event order must be refused: alphabetical or file-row ordering would invent a path.
- `customer_id` — stable within journey; defines bootstrap clusters. If absent, treat journeys as independent clusters and say so.
- `subgroup` — stable within journey; enables within-subgroup path comparison.
- `journey_value` — finite, non-negative, stable within journey.

Refuse fewer than 20 journeys, fewer than 3 distinct touchpoints, more than 60 distinct touchpoints, or a log with only one outcome class. Duplicate (journey_id, timestamp, event_order) keys are invalid.

### Ordering and collapse rules

Sort events by `journey_id`, then `timestamp`, then `event_order` (stable sort). If the collapse rule is on, drop an event whose touchpoint equals the immediately preceding touchpoint in the same journey (revisits after another state are kept). Record how many events were collapsed. **Journey duration must use the first and last pre-collapse timestamps**, so trailing repeated events still count toward the observed window. Build each journey's sequence as `START → touchpoints → CONVERSION or DROP_OFF` using the supplied `converted` flag.

### What to calculate

**1. Transitions.** Count first-order transitions over all sequences. Row probability p̂ᵢⱼ = nᵢⱼ / Σₖ nᵢₖ. For each cell give a Wilson score interval on successes = nᵢⱼ out of total = Σₖ nᵢₖ at confidence level c with z = Φ⁻¹(0.5 + c/2):

    centre = (p + z²/2n) / (1 + z²/n)
    half   = z·√(p(1−p)/n + z²/4n²) / (1 + z²/n)
    interval = [max(0, centre − half), min(1, centre + half)]

Also report next-state entropy per source state, −Σⱼ p̂ᵢⱼ log₂ p̂ᵢⱼ, and its normalized version (divide by log₂ of the number of observed outgoing states).

**2. Positional roles.** For an event at zero-based index r in a journey of analysis length L > 1, relative position is r/(L−1): below 1/3 is Early, above 2/3 is Late, otherwise Middle; length-one journeys are Single. These are relative within-journey thirds, never universal funnel stages. Role-level conversion rates deduplicate journeys within each touchpoint-role cell and get Wilson intervals; they are associations, not effects.

**3. Drop-off and depth.** A touchpoint receives a terminal drop-off only when it is the final observed touchpoint of a journey with `converted = 0`. Drop-off rate = terminal nonconversion endings / journeys visiting the touchpoint, with a Wilson interval. Depth: share of journeys reaching at least d analysis events, and conditional continuation = reaching d+1 / reaching d.

**4. Paths.** A path is the exact ordered collapsed sequence. Report support, share, conversion rate with Wilson interval, median events, median duration, and mean value among converted journeys. Only paths with at least the declared minimum journeys (default 5) lead the comparison; report the rest as unsupported. **In subgroup tables, divide each path's share by that subgroup's journey count** so shares are within-subgroup and sum to one inside each subgroup.

**5. Outcome-conditioned transitions.** Split internal transitions (terminal states excluded) by final outcome and compare per-row probabilities. Rank by absolute difference ONLY among transitions with at least the declared minimum count (default 10, floor 2) in BOTH outcome groups — sparse cells otherwise top the table. State that conditioning on outcome can create selection or collider bias.

**6. First-order absorbing Markov fit and removal sensitivity.** Build the pooled transition matrix with transient states {START, touchpoints} and absorbing {CONVERSION, DROP_OFF}. With transient block Q and one-step conversion vector r, fitted conversion probability from START is read from (I−Q)⁻¹r. Note: because the probabilities are pooled maximum-likelihood estimates, this reproduces the observed conversion rate exactly — that equality is a consistency identity, not a calibration check, so do not present a "calibration gap." For each touchpoint, delete its row and column, renormalize the remaining non-absorbing rows (route empty rows to DROP_OFF), recompute fitted conversion p₋ⱼ, and report relative sensitivity (p₀ − p₋ⱼ)/p₀. **This is a model perturbation, not an intervention, attribution, incremental contribution, or budget signal. Negative values can occur under renormalization and do not establish harm.**

**7. Cluster bootstrap.** Resample `customer_id` clusters with replacement (whole clusters, keeping all their journeys; journeys themselves if no customer_id), recompute the removal sensitivities each time, and report percentile intervals at the declared level with a fixed seed. This captures sampling variation only — it does not repair identity stitching, missing touchpoints, interference, or confounding.

**8. Memory diagnostic.** For each current state, estimate the conditional mutual information (in bits) between the previous and next states from the triple counts. Nonzero values challenge the first-order assumption; sparse tables bias the diagnostic upward, so it is a flag, not a test of adequacy.

### How to present results

Lead with the audit: journeys, events, touchpoints, conversion rate, time window, and every contract warning. Then transitions and entropy, roles, drop-off and depth, supported paths and subgroups, the outcome-conditioned comparison with its support rule, and finally the Markov sensitivity with intervals and the memory diagnostic. State support and uncertainty before discussing any difference, and state the declared settings next to every conclusion.

### Caveats you must always state

1. Every result is descriptive, conditional on the supplied journey boundaries, identity stitching, taxonomy, and observation window. **Descriptive, not causal — test interventions in ExperimentSignal** (the experiments sibling) before any removal, funding, or incrementality claim.
2. `converted = 0` is an observed-window label, not verified abandonment or dissatisfaction; late-window journeys are right-censored.
3. Early/middle/late are relative within-journey thirds, not universal funnel stages or customer psychology.
4. Markov removal is state deletion plus row renormalization in a fitted model — never call it attribution, contribution, or the effect of switching off a real touchpoint, and never sum sensitivities into a credit allocation.
5. Missing, anonymous, offline, cross-device, or incorrectly stitched exposures remain invisible; never invent them.
6. The first-order chain is a deliberately inspectable approximation; report the memory diagnostic honestly.
7. Bootstrap intervals capture sampling variation under the observed cluster structure only.

### Sources

- De Weerdt, J., & Wynn, M. T. (2022). Foundations of Process Event Data. In *Process Mining Handbook*. https://doi.org/10.1007/978-3-031-08848-3_6
- Shao, X., & Li, L. (2011). Data-driven multi-touch attribution models. *KDD '11*. https://doi.org/10.1145/2020408.2020453
- Anderl, E., Becker, I., von Wangenheim, F., & Schumann, J. H. (2016). Mapping the customer journey: Lessons learned from graph-based online attribution modeling. *International Journal of Research in Marketing, 33*(3), 457–474. https://doi.org/10.1016/j.ijresmar.2016.03.001
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association, 22*(158), 209–212. https://doi.org/10.1080/01621459.1927.10502953

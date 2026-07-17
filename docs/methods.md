# Methods

## Empirical transition evidence

For each journey, the app creates `START → observed touchpoints → outcome`, where outcome is `CONVERSION` or `DROP_OFF`. For source state \(i\) and next state \(j\),

\[
\hat p_{ij}=n_{ij}/\sum_k n_{ik}.
\]

Wilson score intervals describe binomial uncertainty for each row probability. Because probabilities in one row sum to one, those marginal intervals are not a simultaneous multinomial region. Next-state entropy is \(-\sum_j \hat p_{ij}\log_2\hat p_{ij}\), with a normalized version divided by the maximum entropy for the observed outgoing support.

## Relative roles

For an event at zero-based index \(r\) in a journey of length \(L>1\), normalized position is \(r/(L-1)\). Values below one third are early, above two thirds are late, and the remainder are middle. Length-one journeys are `Single`. These are relative positional summaries—not a psychological funnel or a claim about a touchpoint's intrinsic role.

Role-level conversion rates deduplicate journeys inside each touchpoint-role cell and use Wilson intervals. They are associations conditional on observed occurrence and role.

## Drop-off and depth

A touchpoint receives a terminal nonconversion ending only when it is the final observed touchpoint of a journey whose supplied outcome is zero. `dropoff_after_visit_rate` divides those endings by all journeys visiting the touchpoint. This differs from the probability of dropping immediately after a transition and remains sensitive to the observation window.

At depth \(d\), `share_reaching` is the share of journeys with at least \(d\) analysis events. Conditional continuation divides journeys reaching \(d+1\) by journeys reaching \(d\).

## Path comparison

Complete paths are exact ordered sequences after the declared repeat rule. Journey duration is measured on the full pre-collapse timestamps, so trailing repeated events still count toward the observed window. The app reports support, cohort share, conversion association with Wilson intervals, median event count, median duration, and mean value among converted journeys. In the subgroup path table, `share` divides by that subgroup's journey count, so shares are within-subgroup and sum to one inside each subgroup. A declared minimum-support flag prevents rare paths from leading the visual comparison; all paths remain in the evidence pack.

Subgroup summaries report path diversity and observed outcomes. Outcome-conditioned transition differences compare transition distributions after splitting on the final outcome. Because the differences carry no uncertainty intervals, ranking by absolute difference alone would let near-empty cells dominate; a transition is therefore flagged as supported only when both the converted and the drop-off group contain at least the declared minimum number of observations of that transition (default 10, floor 2), and the app's primary table shows supported rows only. Conditioning on outcome can create selection or collider bias, so these are pattern descriptions only.

## First-order absorbing Markov sensitivity

The transition matrix has transient states `START` and observed touchpoints, plus absorbing `CONVERSION` and `DROP_OFF`. With transient block \(Q\) and one-step conversion vector \(r\), the fitted probability of eventual conversion is read from

\[
(I-Q)^{-1}r.
\]

Because the transition probabilities are pooled maximum-likelihood estimates from the same journeys, the fitted absorbing chain reproduces the observed conversion rate exactly. That equality is a model-consistency identity, not an informative calibration check, so no "calibration gap" is reported.

For each touchpoint, the app deletes its row and column, renormalizes each remaining nonabsorbing row, routes an empty row to `DROP_OFF`, and recomputes fitted conversion. Relative sensitivity is

\[
(p_0-p_{-j})/p_0.
\]

This is a perturbation of an estimated first-order transition system. It is **not** an intervention, channel attribution, incremental contribution, mediation estimate, or budget recommendation. It does not estimate what would happen after a real touchpoint removal. Real removal can reroute people, change exposure opportunities, alter demand, and violate stationarity. Negative values are possible under renormalization and do not establish harm.

## Uncertainty and model diagnostic

Bootstrap intervals resample `customer_id` clusters with replacement, retaining all journeys for each sampled customer. Without that field they resample journeys. This captures sampling variation under the observed cluster structure; it does not fix confounding, missing states, taxonomy error, interference, censoring, or identity error.

The memory diagnostic estimates conditional mutual information between previous and next states within each current state. Nonzero values indicate that the previous state still helps describe the next state after conditioning on the current state, which challenges the first-order assumption. Sparse contingency tables bias the diagnostic upward, so it is a flag rather than a test of adequacy.

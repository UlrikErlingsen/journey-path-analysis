# Decision guide

Use Trace Signal to audit and describe observed sequence structure—not to award channel credit.

## Defensible questions

- Which next states are common after each logged state, and how uncertain are those proportions?
- Does a touchpoint appear mostly early, middle, late, or alone within observed journeys?
- Which states are commonly terminal in mature nonconversion journeys?
- How quickly does the observed cohort thin out with sequence depth?
- Which complete paths have enough support to compare descriptively?
- Do path mixes, durations, revisits, or transitions differ across declared subgroups?
- Is a first-order Markov summary heavily dependent on a particular state, and is that result stable under clustered resampling?
- Does the memory diagnostic warn that one-state history is inadequate?

## Escalate before acting when

- customer or journey stitching changed between periods;
- timestamps tie without an ordering field;
- cohorts have unequal conversion-observation windows;
- a small number of customers contributes many journeys;
- path support is thin or taxonomy has too many states;
- channel availability or targeting determines who can enter a path;
- the proposed decision is to remove, fund, or claim incrementality for a touchpoint.

For the last case, form a clear intervention, preregister primary metrics and guardrails, and test it in Experiment Signal. Alloc Signal may use planning assumptions, but should not treat Trace Signal removal sensitivity as causal return.

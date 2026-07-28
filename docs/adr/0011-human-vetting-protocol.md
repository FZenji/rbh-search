# ADR-0011 — Human vetting is a measured pipeline stage, not an afterthought

**Status:** Accepted

## Context

The last stage of every candidate search is a person looking at pictures. It is usually
treated as outside the pipeline, and its efficiency is usually assumed to be 100%. It is
not.

A vetter who has just rejected 400 diffraction spikes in a row has a measurably different
threshold from one on their first stamp. Fatigue, ordering effects and prior expectation
all bias the outcome, and none of it is captured unless it is deliberately measured. An
unmeasured human stage silently corrupts the selection function that
[ADR-0009](0009-injection-recovery.md) works so hard to establish.

There is also a scaling question. The score threshold has to be set somewhere, and setting
it against an abstract purity target is arbitrary. The real constraint is how many stamps a
human will actually look at carefully.

## Decision

Human vetting is treated as a pipeline stage with its own measured completeness and purity.

- **The threshold is set by the inspection budget**, not by a purity target. Target ~10³
  stamps across the whole archive — a few evenings of careful work. The resulting purity
  and the completeness it costs are both reported.
- **Injected positives are mixed blind into the vetting queue**, drawn from the same
  synthetic generator used for injection–recovery. Human completeness is then measured on
  exactly the same footing as algorithmic completeness, and the total selection function is
  the product of the two.
- Vetters record a **category**, not a binary: `wake` / `edge-on disk` / `tidal feature` /
  `lens arc` / `jet` / `artifact` / `unclear`. Categories feed back into the discriminator
  training set.
- Stamps are presented **multi-band with a consistent, pre-registered stretch**, in
  randomised order, with the score hidden. Showing the score would make the measurement
  circular.
- Every decision is logged with vetter, timestamp, duration and score, so the human stage
  is as auditable as the algorithmic ones — and so fatigue effects are visible after the
  fact.

## Consequences

- The published selection function includes the human stage, which is unusual and is the
  correct thing to do.
- Vetting takes longer, because a fraction of the queue is synthetic. That fraction is the
  price of knowing what the stage is worth.
- Score thresholds become a function of available human effort, which must be stated
  explicitly in the catalogue.
- With a single vetter, "human completeness" measures one person on one day. Worth stating
  plainly; multiple independent vetters would be better and should be sought before
  publication.
- The randomised, score-hidden presentation makes vetting slower and less satisfying than
  a ranked list would be. That is the point.

## Alternatives considered

- **Unstructured visual inspection.** What most searches do. Rejected: unmeasurable and
  unreproducible, and it invalidates the effort spent measuring everything upstream.
- **Fully automated classification, no human stage.** Rejected: with N = 1 real positive,
  no classifier deserves that trust, and the categories humans assign are the only source
  of real labels we will ever get.
- **Crowdsourced vetting (Zooniverse-style).** Better statistics and multiple independent
  vetters. Genuinely attractive, and the logging format should be designed so it stays
  possible — but it is disproportionate for a ~10³-stamp queue.

# ADR-0011 — Human vetting is a measured pipeline stage, not an afterthought

**Status:** Accepted

**In plain terms:** The last step is a person looking at pictures — probably you. People get
tired and start missing things after a few hundred boring images, so we measure that too:
fake wakes get mixed secretly into your review queue, and we track how many you catch. We
also set how many images you have to review based on how many you'll realistically look at
carefully, rather than picking a number out of the air.

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

## Amendment, 2026-08-02 (vetters learn the injections, and this protocol must plan for it)

Found in Phase 2, in a place that looks unrelated: ADR-0017's blind discrimination test uses
transplanted pixels from RBH-1 as its "real" class, and after two rounds the participant
reported *"now I know what the actual trail of RBH-1 looks like, I will probably always be
able to distinguish it"* — scoring 20/20 twice while every measured statistic said the two
classes were identical.

**This protocol has the same structure and will hit the same wall.** Injected positives are
mixed into the queue to measure vetter sensitivity, which works only while the vetter cannot
tell an injection from a candidate. They are drawn from one generator, calibrated to one
object. A vetter working a ~10³-stamp queue will see hundreds, and the recall figure will
then measure *recognition of our injections* rather than sensitivity to wakes — drifting
upward, looking like an improving vetter.

It has to be designed for rather than discovered late:

- **Vary what is injected.** Sample across the completeness grid's full parameter range, not
  at the calibrated point, so there is no single look to learn. This also samples the
  selection function where it is actually uncertain, so it costs nothing.
- **Include transplants as well as parametric injections**, in proportion, so the injected
  class is not homogeneous.
- **Log recall against vetting order.** If sensitivity to injections climbs through the
  queue while it stays flat for real candidates, that is the effect appearing, and it is
  only detectable if the order is recorded. Cheap to add now, impossible to reconstruct
  later.
- **Treat a vetter's later sessions as weaker evidence** about sensitivity, in the same way
  ADR-0017 now treats a repeat participant's accuracy.

No change to the categories or the logging schema, which already record what is needed —
except that **vetting order must be part of the record**.

## Alternatives considered

- **Unstructured visual inspection.** What most searches do. Rejected: unmeasurable and
  unreproducible, and it invalidates the effort spent measuring everything upstream.
- **Fully automated classification, no human stage.** Rejected: with N = 1 real positive,
  no classifier deserves that trust, and the categories humans assign are the only source
  of real labels we will ever get.
- **Crowdsourced vetting (Zooniverse-style).** Better statistics and multiple independent
  vetters. Genuinely attractive, and the logging format should be designed so it stays
  possible — but it is disproportionate for a ~10³-stamp queue.

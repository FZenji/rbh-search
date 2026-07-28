# ADR-0015 — Publish candidates, never discoveries

**Status:** Accepted

**In plain terms:** We produce a list of *candidates worth a closer look*, never a claim
that we've found a runaway black hole. Confirming one requires a spectrograph — an
instrument that splits light apart to reveal how fast things are moving — and we don't have
one. Pictures alone weren't enough for the experts arguing over RBH-1 for three years, and
they won't be enough for us either.

## Context

The history of RBH-1 is unambiguous on this point.

The original 2023 paper — using imaging *and* Keck spectroscopy — was careful enough to
title itself "A **candidate** runaway supermassive black hole". Even so, three separate
groups published competing interpretations within months: a bulgeless edge-on disk galaxy,
a partially shredded galaxy, and an order-of-magnitude objection to the formation timescale.
Deep HST imaging in 2024 came down **against** the wake interpretation. Only JWST/NIRSpec
IFU kinematics in 2026 — a 600 km s⁻¹ velocity discontinuity across 1 kpc at the tip, with
fast-radiative-shock line ratios — settled it.

Three years, and the thing that settled it was spectroscopy. Deep broadband imaging not
only failed to settle it, it briefly pointed the wrong way.

Separately, Bellovary et al. 2023 showed that flyby encounters involving multiple black
holes produce morphologically similar star-forming linear features **without** any
gravitational-wave recoil. So even a morphologically perfect candidate does not uniquely
imply a runaway black hole.

This pipeline has strictly less information than the 2023 discovery paper: broadband
imaging, no spectroscopy.

## Decision

**The pipeline produces candidates for spectroscopic follow-up. It never produces
discoveries.**

Concretely:

- Catalogue objects are typed as **"linear star-forming feature"**, not "runaway black
  hole". The physical interpretation is downstream of follow-up and belongs to whoever does
  it.
- No public announcement of a candidate as a runaway SMBH without, at minimum, a measured
  velocity discontinuity at the tip and shock-consistent line ratios.
- The candidate catalogue is published **with its selection function, survey MOC, ROC
  curve and false-positive rate**, so a reader can judge each candidate for themselves.
- Every candidate record carries the alternative hypotheses explicitly — edge-on disk
  score, tidal score, lens score, jet score — rather than a single "wake likelihood".
- Communication follows the science: "N candidate linear features, of which the M
  highest-ranked merit spectroscopy", never "we found a runaway black hole".

## Consequences

- Success looks modest: a ranked list and a density limit, not a headline. That is the
  honest shape of this result.
- Follow-up requires telescope time we do not have. Realistically, a strong candidate
  becomes a proposal, or a note to a group who can observe it — worth deciding *before*
  there is a candidate, not after.
- The catalogue stays useful even if every candidate turns out to be an edge-on disk,
  because the selection function and area still constrain the space density.
- Some perfectly reasonable excitement gets deferred. Given a three-year controversy over
  the prototype, this seems a small price.

## Alternatives considered

- **Announce strong candidates as probable detections.** Faster, higher impact. Rejected on
  the RBH-1 history — the field spent three years on one object with far better data than
  we will have.
- **Do not publish at all without follow-up.** Rejected: the selection function and density
  limit are useful independently, and sitting on a candidate list helps no one.
- **Publish only the density limit, not the candidates.** Rejected: the candidates are the
  part someone else can act on, and withholding them wastes the search.

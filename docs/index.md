# rbh-search

A reproducible search for **runaway supermassive black hole (RBH) wakes** in the public
HST and JWST imaging archives.

!!! tip "New to this?"
    Read **[Start here](start-here.md)** instead of this page. It covers the same ground in
    plain English with no astronomy background assumed, and explains every decision we've
    made. The **[Glossary](glossary.md)** defines all the jargon.

## The premise

A supermassive black hole ejected from its host galaxy — most plausibly by gravitational
recoil following a black hole merger — ploughs through the circumgalactic medium at
~1000 km s⁻¹. The bow shock ahead of it compresses gas past the threshold for star
formation, and it leaves behind a narrow ribbon of newborn stars marking the path it took.

Projected on the sky that is a **thin, nearly straight, blue, one-sided filament**, a few
arcseconds long and roughly PSF-wide, anchored to a galaxy at one end and terminating in a
compact knot at the other, with stellar ages increasing away from the tip.

Exactly one such object is known: **RBH-1**, found serendipitously in a single-orbit
HST/ACS image in 2022 and confirmed by JWST in 2026. This project asks whether more are
sitting unrecognised in thirty years of archival pixels.

## What makes this tractable

RBH-1 was a **high-significance detection in a one-orbit exposure**. The search is
therefore limited by sky area, not by depth — which means the whole HST and JWST archive
is in play, not just the deep fields, and it means a laptop-scale algorithm run over a
cloud-scale corpus is the right shape of solution.

## What makes this hard

Thin straight lines are the single most common artifact class in astronomical imaging,
and the most common *astrophysical* thin straight thing is a bulgeless edge-on disk
galaxy. RBH-1 itself was contested in the literature for three years on exactly this
point. **Rejecting contaminants is the project, not detecting streaks.**

## What we will actually deliver

A ranked candidate catalogue **with a measured selection function**. The second half of
that sentence is what makes the work worth doing: because completeness is measured by
injection–recovery over a MOC-accounted unique sky area, a result of zero candidates is
still a quantitative upper limit on the space density of SMBH wakes — and that limit
directly predicts how many Euclid DR1 should find.

## Where to start

- **New to any of this? → [Start here](start-here.md)**
- Need a term defined? → [Glossary](glossary.md)
- Want the published measurements? → [RBH-1 dossier](science/rbh-1-dossier.md)
- Want to know what the detector looks for? → [Target signature](science/target-signature.md)
- Want to know why it is built this way? → [ADR index](adr/README.md)
- Want to build it? → [Architecture](design/architecture.md), then
  [Roadmap](design/roadmap.md)

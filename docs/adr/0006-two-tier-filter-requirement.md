# ADR-0006 — Two tiers by filter coverage, prioritising cross-filter vetting

**Status:** Accepted

**In plain terms:** Images taken in two or more colours are far more useful, because colour
is both our best glitch test (a glitch rarely shows up in both colours) and our best galaxy
test. So we search those first and call them Tier A. Single-colour images still get
searched, but they go in a separate, lower-confidence list rather than being quietly mixed
in.

## Context

The very first thing that saved RBH-1 from the bin was that it appeared in **both** F606W
and F814W. van Dokkum's team thought it was a badly-removed cosmic ray until that check;
cross-filter presence ruled that out immediately.

Cross-filter coincidence is therefore not an optional refinement — it is the test that
made the discovery possible. It is also the cheapest strong artifact test we have, and it
doubles as the entry point to the best *astrophysical* discriminant (the rest-UV to
rest-NIR ratio, which distinguishes a young wake from an old stellar disk).

But archival coverage is heterogeneous. A substantial fraction of the corpus has only one
filter. Requiring two filters everywhere would discard real area; ignoring the distinction
would silently mix two very different purity regimes into one catalogue and make the
selection function meaningless.

## Decision

Every tile is assigned a **tier** from its filter coverage, and the two tiers are processed
and reported **separately**, each with its own selection function.

| Tier | Coverage | Vetting available | Priority |
|---|---|---|---|
| **A** | ≥ 2 filters | Cross-filter coincidence, colour gradient, rest-NIR ratio | Swept first |
| **B** | 1 filter | Morphology and geometry only; no colour information | Swept second, reported separately |

A further internal flag records **multi-visit coverage with differing roll angles**, which
enables the cross-visit test — detector-frame artifacts rotate on the sky, real objects do
not. This is the strongest artifact discriminant available and is a bonus wherever present,
in either tier.

Tier B candidates are **never promoted to the main catalogue on morphology alone**. They
are published as a separate, explicitly lower-purity list, and any Tier B candidate worth
pursuing is escalated by requesting or locating second-filter data rather than by relaxing
the standard.

## Consequences

- Two selection functions must be measured, not one. Injection–recovery runs per tier.
- Purity will differ substantially between tiers, and saying so openly is more useful than
  a single blended number that describes neither.
- Tier A gets swept first, so the highest-quality result arrives earliest — good for both
  science and morale.
- Some real wakes will sit in Tier B and be under-ranked. That is a known, *measured* cost
  recorded in the Tier B completeness, not a hidden one.
- Tiering is a property of the tile, so it must be computed in the manifest/tiling stage
  and carried through every downstream record.

## Alternatives considered

- **Require ≥ 2 filters everywhere.** Highest purity, cleanest story. Rejected: it throws
  away real area for a corpus where area is the binding constraint
  ([ADR-0001](0001-search-the-full-archive.md)).
- **Ignore filter coverage entirely.** Maximum area, one pipeline. Rejected: it mixes
  incompatible purity regimes and makes the selection function uninterpretable.
- **Require ≥ 3 filters.** Would enable SED fitting per candidate, but shrinks the area
  too far for v1. Recorded as an attractive option for Euclid/Roman, which deliver uniform
  multi-band coverage by construction.

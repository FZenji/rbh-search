# Start here

No astronomy background assumed. This page explains what we're looking for, how the
search works, why we made each choice, and where to find everything. Anything in
**bold-italic** like ***this*** is defined in the [glossary](glossary.md).

---

## 1. What are we actually looking for?

Think of a speedboat crossing a lake. The boat itself is small and hard to see from far
away — but the wake it leaves behind is long, bright, and obvious.

We're looking for the wake, not the boat.

The "boat" is a **supermassive black hole** — an object millions of times heavier than the
Sun — that has been thrown out of the galaxy it used to live in. It's now flying through
space at around 1,000 kilometres *per second*.

The "lake" is the thin gas that surrounds every galaxy. It's incredibly sparse, but it's
there.

The "wake" is the interesting bit. As the black hole ploughs through that gas, it squeezes
the gas in front of it. Squeezed gas collapses. Collapsed gas forms **stars**. So the black
hole leaves behind a long trail of brand-new stars marking exactly where it has been.

New stars are blue and bright. So on a telescope image, the thing we're hunting looks like:

> **a thin, straight, blue streak** — with a galaxy at one end (where the black hole was
> thrown out from) and a bright compact blob at the other end (where the black hole is
> right now).

The stars nearest the black hole are the youngest and bluest. The ones nearest the galaxy
were formed first and have had time to age and redden. So there's a colour gradient along
the streak, like a fuse burning.

## 2. How many have been found?

**One.** It's called RBH-1.

It was found completely by accident in 2022. An astronomer was using Hubble to photograph
something else entirely, and there was a weird streak sitting in the corner of the image.
His first thought was that it was a glitch.

Here's the thing that makes this whole project possible: **it was an easy detection**. It
wasn't dredged out of a super-deep, hundred-hour exposure. It was sitting in a routine
one-hour snapshot, plainly visible. He nearly deleted it as a glitch precisely *because*
it was so obvious.

That fact drives almost every decision below.

## 3. Why hasn't anyone found more?

Because nobody has systematically looked. Finding RBH-1 required a human to notice an odd
streak in a picture they were taking for another reason.

Meanwhile, Hubble has taken about thirty years of pictures, and JWST is adding more. Nobody
has scanned all of them for this specific shape.

That's the gap. That's what we're building.

## 4. How does the search work?

Seven steps. In everyday terms:

| Step | What happens |
|---|---|
| **1. Make a list** | Ask NASA's archive for every usable picture Hubble and JWST have taken of deep space. Record where each one points and what colours it was taken in. |
| **2. Cut the sky into squares** | Instead of working picture-by-picture (they're wildly different sizes and they overlap), we chop the sky into equal ***tiles***. Each tile is one unit of work. |
| **3. Find the streaks** | For each tile, run a filter that highlights thin line-shaped things. This is genuinely similar to the tools that find blood vessels in medical scans — same shape problem. |
| **4. Throw out the glitches** | Most streaks are camera artefacts. Reject anything that looks like a known glitch (details in step 6). |
| **5. Double-check** | Run a completely different, independently-written streak-finder over the survivors. If two different methods agree, that's much stronger than one. |
| **6. Score what's left** | For each survivor, measure everything we can — colour, shape, symmetry, what's at each end — and give it a score for how much it looks like a real wake versus a lookalike. |
| **7. Look at them** | A human looks at the top-scoring ones. That human is you. |

Running quietly alongside all of this is the step that makes it science rather than a
treasure hunt — see section 7.

## 5. What's actually hard about this?

Not finding streaks. **Streaks are everywhere.** The hard part is telling the real thing
from the fakes, and there are two very different kinds of fake.

### Fake type 1: camera glitches (the easy problem)

Cosmic rays hitting the detector, satellites flying through the shot, spikes of light
around bright stars, the edges of the sensor. All of these make straight lines.

These sound scary but they're mostly *already solved*, and for a slightly beautiful reason.

Telescopes never take one photo — they take several and combine them, nudging the
telescope slightly between shots. Real things in space stay put between shots. Cosmic rays
and satellites don't. So the standard combining software already throws them out
automatically.

**By choosing to search the already-combined images rather than the raw ones, we get most
of our glitch-rejection for free.** That's one of the best decisions in the project and it
cost us nothing.

### Fake type 2: galaxies seen edge-on (the hard problem)

Our own Milky Way is a flat disc. Seen face-on, a disc galaxy looks like a spiral. Seen
edge-on, it looks like... a thin straight line.

This is a genuine problem, not a theoretical one. When RBH-1 was announced, other
astronomers published papers arguing it was just an edge-on galaxy. **The argument ran for
three years.** In 2024 a very deep Hubble image seemed to prove the sceptics right. Only in
2026 did JWST settle it in favour of the black hole.

So: the world's experts, with better data than we'll have, couldn't tell these apart for
three years.

Our best trick is this. An edge-on galaxy is a normal galaxy — it's full of old stars. Old
stars glow in **infrared**. A black hole wake is made *only* of newborn stars — there are
no old stars in it, because it didn't exist until a few million years ago. So:

> Look at the streak in blue light, then look again in infrared. If it's bright in blue but
> **vanishes** in infrared, it has no old stars, so it isn't a galaxy.

That's the single most useful test we have. It isn't foolproof, which is why we score
candidates rather than accepting or rejecting them outright.

## 6. Why can't we just download the images?

Because there are tens of terabytes of them, and every single pixel has to be looked at
once.

NASA keeps a copy of the whole archive on Amazon's cloud servers. If your program runs on a
computer *inside* that same data centre, reading the data is free and fast. If it runs on
your laptop, you're pulling tens of terabytes across the internet — slow, and expensive.

So we send the program to the data rather than the data to the program. NASA runs a free
service called the **Fornax Science Console** for exactly this: it gives you a computer
sitting right next to the archive, at no cost.

**But not for everything.** Development and testing happen on your actual machine, using a
handful of small saved images. You need to be able to change a line of code and see the
result in two seconds, and that's impossible if every test round-trips to a cloud server.
So it's both: laptop for building, cloud for the big run.

## 7. The bit that makes this science instead of a lottery ticket

Be honest about the likely outcome: **we probably find nothing.**

So here's the question that matters. If we search everything and come up empty, have we
learned anything?

With a naive search: no. "We looked and didn't see any" is worthless, because you can't
tell the difference between *there are none* and *our program isn't good enough to see
them*.

The fix is to **cheat on ourselves, deliberately**.

We generate fake wakes on the computer — realistic ones, with all the right properties —
and secretly paste them into the real telescope images. Then we run the pipeline and see
how many it finds.

If we hide 1,000 fakes and the pipeline finds 700, we now know it catches about 70% of the
wakes that are actually there. That number is called the ***completeness***.

Now "we found nothing" becomes a real scientific statement:

> "We searched 18 square degrees of sky. In that area we would have found 70% of any wakes
> present. We found none. Therefore there are fewer than X of these things per patch of
> sky."

That's a publishable result. It's a real constraint that other astronomers can use — and it
predicts how many the big upcoming surveys should find.

This is the single most important design decision in the project, and it's the one that's
least obvious from the outside.

## 8. Where the real payoff is

Hubble and JWST have, between them, photographed roughly **0.1% of the sky**. Our whole
searchable area is around 15–20 square degrees. For scale, the full Moon covers about 0.2
square degrees — so we're searching an area equal to about 90 full Moons. Out of an entire
sky.

Two things change that, both within the next few months:

| Survey | When | Area |
|---|---|---|
| **Euclid DR1** | 21 October 2026 | ~1,900 square degrees — about **100× our whole archive** |
| **Roman** | launched 30 August 2026 | eventually thousands of square degrees |

The astronomer who found RBH-1 says outright that these are the obvious places to hunt.

So why aren't we starting there? **Because RBH-1 isn't in them.** We only have one known
example to test against, and it's in the Hubble archive. You have to prove your method
finds the thing you know is there before you point it at fresh sky. Otherwise you have no
idea whether an empty result means "nothing there" or "program broken".

Hubble and JWST are where we prove the method works. Euclid is where we expect to actually
find something. The code is built so switching over is a small job, not a rewrite.

---

## Every decision, in one line each

Full reasoning for each is one click away.

| # | Decision | Why, plainly |
|---|---|---|
| [0001](adr/0001-search-the-full-archive.md) | Search everything, not just the famous deep images | RBH-1 was easy to see in a short exposure. We don't need deep pictures, we need *lots* of pictures. Deep-only would throw away 90% of our sky. |
| [0002](adr/0002-compute-next-to-the-data.md) | Run the big job on NASA's free cloud; build on your laptop | Tens of terabytes can't come to us. But we still need fast local testing, so it's both. |
| [0003](adr/0003-search-plane-drizzled-mosaics.md) | Use the already-combined images, not raw ones | Free removal of cosmic rays and satellite trails. Best value decision in the project. |
| [0004](adr/0004-work-unit-is-a-sky-tile.md) | Work in sky tiles, not per-file | Files overlap and vary hugely in size. Tiles are even, don't double-count sky, and let us know exactly how much sky we searched. |
| [0005](adr/0005-detector-cascade.md) | Two different streak-finders, cheap one first | Agreement between two independent methods is much stronger evidence than one. The second only runs on survivors, so it's nearly free. |
| [0006](adr/0006-two-tier-filter-requirement.md) | Prefer images taken in 2+ colours | Colour is both our best glitch test *and* our best galaxy test. Single-colour images still get searched, but reported separately so we don't mix confidence levels. |
| [0007](adr/0007-target-selection-window.md) | Write down exactly what sizes we look for | If the limits are hidden inside the code, nobody can tell what we'd have missed. Written down once, in one file. |
| [0008](adr/0008-scored-discriminants-not-cuts.md) | Score candidates, don't reject them | The experts argued for three years over RBH-1. We're not going to settle it with a threshold. So we rank, keep everything, and let people re-rank later. |
| [0009](adr/0009-injection-recovery.md) | Hide fake wakes in the real data | Section 7 above. This is what turns "found nothing" into a real result. |
| [0010](adr/0010-rbh1-regression-test.md) | Automatically re-check we can still find RBH-1 | Tuning naturally drifts toward stricter settings and a tidier list. Without a fixed anchor you can quietly tune until the pipeline can't find the one real example. |
| [0011](adr/0011-human-vetting-protocol.md) | Measure the human, too | After 400 boring images in a row, people miss things. So we secretly mix fakes into your review queue and measure your hit rate as well as the computer's. |
| [0012](adr/0012-reproducibility-contract.md) | Same input, same output, every time | Every result records which exact file, settings and code version produced it. If a candidate ever matters, every choice behind it will be picked over. |
| [0013](adr/0013-survey-agnostic-io.md) | Keep telescope-specific bits in one place | So pointing at Euclid in October is a small job, not a rewrite. |
| [0014](adr/0014-output-data-model.md) | Fixed output formats and what we keep | Including keeping the *rejects*, because "why was this thrown out?" is the question people actually ask. |
| [0015](adr/0015-no-discovery-claims.md) | We produce candidates, never discoveries | Confirming one needs a spectrograph, which we don't have. Pictures alone were not enough for the experts and won't be enough for us. |
| [0016](adr/0016-rejoin-collinear-fragments.md) | Stitch broken-up streaks back together | A wake is a chain of clumps, so any cutoff strict enough to reject noise snips the faint bits between them. Better to rejoin the pieces than to tune the cutoff to a knife edge. |

---

## Where is everything?

### Reading the docs as a website

The nicest way to read all of this — searchable, with working links and a sidebar:

```bash
uv run mkdocs serve
```

Then open **<http://127.0.0.1:8000>** in your browser. It updates live as files change.
Press `Ctrl+C` in the terminal to stop it.

### The files

```
RBH/
├── README.md              ← one-page overview
├── CLAUDE.md              ← notes for AI assistants working on this
├── docs/
│   ├── start-here.md      ← you are here
│   ├── glossary.md        ← every bit of jargon, defined
│   ├── science/           ← what we're looking for and what fools us
│   ├── design/            ← how the program is built
│   └── adr/               ← the 15 decisions, one file each
├── src/rbh/               ← the program (currently just a skeleton)
└── tests/                 ← automatic checks
```

### Checking the project is healthy

```bash
uv run pytest -m "not network"   # run the automatic checks
uv run ruff check .              # check code style
uv run rbh config                # show current search settings
uv run rbh reference             # show the RBH-1 facts we test against
```

---

## Where are we right now?

**Phases 0 and 1 of 6: complete.** ✅

**The detector works.** Given the original 2022 Hubble image, it finds RBH-1 by itself —
no hints about where to look. It measures the streak as 5.5 arcseconds long and 20 times
longer than it is wide, and if you measure from the host galaxy to the far end you get
8.1 arcseconds against the 7.8 that was published. Out of everything else in that patch of
sky, exactly one thing passes our filters, and it's the right one.

Two things went wrong along the way, which is the useful part:

- **The published coordinate isn't where the streak is.** It's about 5.5 arcseconds away.
  That looked like a bug for a while. It turned out the published coordinate marks the
  *host galaxy* at one end of the wake, not its middle — and it sits within 0.11
  arcseconds of the streak's own centre line, so it's exactly on it.
- **The streak kept breaking into three pieces.** A wake is a chain of bright clumps with
  faint bridges between them, and any cutoff strict enough to reject noise also snips
  those bridges. Rather than fiddling with the cutoff until it happened to work, we now
  detect the pieces and stitch back together the ones that line up
  ([ADR-0016](adr/0016-rejoin-collinear-fragments.md)).

**Phase 2 is next: the measurement.** This is section 7 above — hiding fake wakes in real
images to find out what fraction we'd catch. Until that exists, we can find things but we
can't say what we'd have missed.

The full phase list, with what each one has to achieve before the next begins, is in the
[roadmap](design/roadmap.md).

One thing worth doing soon: the free NASA cloud service needs an application, and we don't
control how long approval takes. Better to apply now than to find it blocking Phase 3.

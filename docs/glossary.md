# Glossary

Every term used in this project, in plain English. If something in the other docs doesn't
make sense, it should be here — if it isn't, that's a documentation bug worth reporting.

## Measuring the sky

**Arcsecond (″)**
: A tiny angle. One degree = 60 arcminutes = 3,600 arcseconds. The full Moon is about 1,800
  arcseconds across, so **one arcsecond is roughly 1/1800th of the Moon's width**. RBH-1 is
  about 8 arcseconds long — around 1/225th of the Moon.

**Square degree (deg²)**
: Area on the sky. The full Moon covers about **0.2 square degrees**. Our whole search area
  of ~18 deg² is therefore about 90 full Moons' worth of sky. The entire sky is 41,253
  deg².

**Magnitude**
: How bright something is. The scale is backwards and compressed: **smaller numbers are
  brighter**, and every 5 steps is a factor of 100. The Sun is −27, the faintest star you
  can see by eye is about +6, and RBH-1 is +22.9 — roughly a million times fainter than
  naked-eye visibility.

**Surface brightness**
: Brightness *spread over area*, in "magnitudes per square arcsecond". Matters because a
  faint smear and a bright thin line can contain the same total light but be wildly
  different to detect. This is the number that decides whether our target is visible.

**Redshift (z)**
: How much the universe's expansion has stretched an object's light on its way to us. It's
  a stand-in for distance and for look-back time. RBH-1 sits at z = 0.964, meaning its
  light took about **7.5 billion years** to reach us — we're seeing it as it was when the
  universe was about half its current age.

**Position angle (PA)**
: Which way something points on the sky, as an angle. Useful because many camera glitches
  point in fixed directions and real objects don't.

## The objects

**Supermassive black hole**
: A black hole millions to billions of times the mass of the Sun. Essentially every large
  galaxy has one at its centre.

**Runaway / recoiling black hole**
: One that has been kicked out of its galaxy. The leading explanation: when two black holes
  spiral together and merge, the merger can fire off gravitational waves unevenly, and the
  resulting recoil punts the merged black hole away — the same principle as a rifle kicking
  back. If the kick is hard enough, it escapes the galaxy entirely.

**Wake**
: The trail of newborn stars left behind as the escaping black hole compresses gas in its
  path. **This is what we actually search for.** The black hole itself is invisible.

**Bow shock**
: The compressed pile-up of gas directly in front of the moving black hole, like the wave
  in front of a ship's bow. Detecting this is what finally confirmed RBH-1 in 2026.

**CGM (circumgalactic medium)**
: The thin halo of gas surrounding a galaxy. The "water" the black hole is ploughing
  through.

**RBH-1**
: The one and only confirmed example. Found by accident in 2022, argued over until 2026.
  Everything we build is tested against it.

**Edge-on galaxy**
: A flat disc galaxy seen from the side, so it looks like a thin straight line rather than
  a spiral. **Our single worst source of false alarms** — this is exactly what other
  astronomers claimed RBH-1 really was.

**Bulge / bulgeless**
: The fat central bump in many disc galaxies. A galaxy without one looks like a clean
  straight line edge-on, with no obvious middle — which is precisely what makes bulgeless
  edge-on galaxies such convincing wake impostors.

**Tidal tail**
: A streamer of stars pulled out of a galaxy by a close encounter with another galaxy.
  Another lookalike, though usually curved and attached to an obviously interacting pair.

**Jet**
: A narrow beam of material fired from the centre of an active galaxy. Also a lookalike,
  but it emerges from a bright nucleus and usually shows up on radio telescopes.

**Gravitational lens arc**
: A background galaxy smeared into a curved arc by the gravity of something massive in
  front of it. Curved rather than straight, which usually gives it away.

## Telescopes and cameras

**HST (Hubble Space Telescope)**
: Launched 1990. Where RBH-1 was found. Its cameras: **ACS/WFC** (the workhorse visible
  camera, and the one that found RBH-1), **WFC3/UVIS** (bluer), **WFC3/IR** (infrared —
  valuable to us because it reveals old stars).

**JWST (James Webb Space Telescope)**
: Launched 2021. Infrared. Its main imaging camera is **NIRCam**. It confirmed RBH-1 in
  2026.

**Euclid**
: European telescope surveying huge areas of sky. Its first big data release, **1,900
  square degrees**, lands on 21 October 2026 — about 100× our entire Hubble+JWST search
  area.

**Roman (Nancy Grace Roman Space Telescope)**
: NASA's wide-field telescope, launched 30 August 2026. Eventually the best possible hunting
  ground for this, though its data won't be usable for a while yet.

**Filter / band**
: A piece of coloured glass that lets only certain wavelengths through, so each image
  captures one "colour". `F606W` is roughly visible green-yellow; `F814W` is deep red.
  Comparing images taken through different filters is how we measure colour — and colour is
  our best discriminator.

**Deep field**
: A patch of sky the telescope stared at for a very long time to capture extremely faint
  things. Famous, beautiful, and — for us — **not especially useful**, since our target is
  bright enough to appear in ordinary short exposures. See
  [ADR-0001](adr/0001-search-the-full-archive.md).

**PSF (point spread function)**
: How a single point of light gets smeared out by the telescope. Nothing can appear sharper
  than this. RBH-1's width is right at Hubble's PSF limit — it's about as thin as Hubble
  can possibly render anything.

## Data and processing

**FITS**
: The standard astronomy file format. An image plus a header of metadata.

**Mosaic**
: Multiple exposures stitched into one larger image.

**Drizzling**
: The standard method for combining several exposures into one, correcting distortion
  along the way. Crucially for us, **it automatically discards things that appear in only
  one exposure** — which is exactly what cosmic rays and satellite trails do. See
  [ADR-0003](adr/0003-search-plane-drizzled-mosaics.md).

**Cosmic ray**
: A high-energy particle striking the detector, leaving a bright streak or dot. Looks
  alarmingly like our target in a single frame. Removed by drizzling.

**Weight map / exposure map**
: A companion image recording how much exposure time went into each pixel. Essential for
  us, because archive images have wildly uneven depth — a fixed brightness threshold would
  produce all its "detections" in the thin, noisy edges.

**DQ (data quality) array**
: A companion image flagging known-bad pixels.

**Diffraction spike**
: The cross or star-shaped rays around bright stars in telescope images — an artefact of
  the telescope's internal supports. Straight lines, so a false-alarm source; but they
  point in fixed directions relative to a bright star, which gives them away.

**MAST**
: NASA's archive holding all Hubble and JWST data. Free and public.

**S3 / `s3://stpubdata`**
: Amazon's cloud storage, and specifically the bucket where NASA keeps its public copy of
  the archive. Free to read, no account needed.

**MOC (Multi-Order Coverage map)**
: A compact, exact way of recording "which bits of sky does this cover". We use it to
  combine thousands of overlapping image footprints and get the **true** total area
  searched without double-counting. That number is the denominator of everything we
  publish.

**Tile**
: Our unit of work — one square of sky, processed independently. See
  [ADR-0004](adr/0004-work-unit-is-a-sky-tile.md).

**Parquet**
: A file format for tables that's fast to query and compresses well. Where our results go.

## Search and statistics

**False positive**
: Something the pipeline flags that isn't real. The central problem of this project.

**Completeness**
: The fraction of real objects the pipeline would actually find. Measured by hiding fakes
  in the data and counting how many come back. **Without this number, finding nothing tells
  you nothing.**

**Purity**
: The fraction of flagged candidates that are real. The opposite trade-off from
  completeness — tighten one and you loosen the other.

**Selection function**
: The full description of what the pipeline can and can't find, as a function of size,
  brightness, colour and so on. Our single most important output, arguably more valuable
  than the candidate list itself.

**Injection–recovery**
: The technique behind all of the above: paste realistic fakes into real images, run the
  pipeline, count how many it recovers. See
  [ADR-0009](adr/0009-injection-recovery.md).

**Transplant**
: Our primary "fake": the **real** RBH-1 pixels, cut out and pasted into other real sky. No
  model, so no modelling errors. Its limitation is that it gives us exactly one shape. See
  [ADR-0017](adr/0017-synthetic-realism.md).

**Clumpiness**
: How much a wake's light is concentrated into discrete knots rather than spread smoothly.
  It matters because a clumpy feature breaks apart at the detection threshold. Measuring
  RBH-1 showed its clumpiness is low, and that most of its fragmentation is the threshold
  cutting a fairly smooth feature wherever the noise dips.

**Degeneracy**
: When two different explanations fit the data equally well, so the measurement can't tell
  them apart. Ours: a wake could look this wide either because it *is* that wide or because
  the telescope's blurring is worse than assumed. Separating them needs a star in the field
  to measure the blurring, and our cutout hasn't got one.

**Ridge filter / vesselness filter**
: Our main detection tool. An image filter designed to highlight thin line-like structures.
  Borrowed from medical imaging, where the same maths finds blood vessels in scans.

**Hysteresis thresholding**
: A two-cutoff trick. Anything above the *high* cutoff is definitely real; anything
  connected to it and above the *low* cutoff gets included too. It lets us follow a faint
  streak outward from its bright knots without accepting every faint blob in the image.
  Same idea as the edge detection in a photo editor.

**Fragment linking**
: Stitching detected pieces back into one object when they line up. A wake is a chain of
  bright clumps with faint bridges, so a threshold strict enough to reject noise snips the
  bridges. See [ADR-0016](adr/0016-rejoin-collinear-fragments.md).

**Radon / Hough transform**
: A different mathematical approach to finding straight lines — it effectively tests every
  possible line through the image and asks how much light sits along it. We use a version
  of it (the **Median Radon Transform**, from a tool NASA built to spot satellite trails) as
  an independent second opinion.

**Spectroscopy**
: Splitting light into its component wavelengths, which reveals what something is made of
  and how fast it's moving. Far more informative than a picture — and it's what finally
  settled the RBH-1 argument. We don't have it, which is why we produce candidates rather
  than discoveries. See [ADR-0015](adr/0015-no-discovery-claims.md).

**Tully–Fisher relation**
: A known relationship between how fast a disc galaxy spins and how bright it is. The
  sceptics' strongest argument against RBH-1 was that it fitted this relation — i.e. it
  behaved exactly like a spinning disc galaxy should.

## Software and project terms

**ADR (Architecture Decision Record)**
: A short document recording one decision, why it was made, and what it costs. We have 15.
  They exist so that a year from now, nobody has to guess why something works the way it
  does — and so that a published result can be audited. See
  [the index](adr/README.md).

**uv**
: The tool that manages Python versions and packages here. `uv run <something>` runs a
  command with the right environment automatically. You never need to activate anything.

**ruff**
: Checks code style and formatting, fast.

**mypy**
: Checks that the code's data types are consistent — catches a whole class of bug before
  the code ever runs.

**pytest**
: Runs the automatic tests.

**pre-commit**
: Runs all the above automatically every time you make a git commit, so broken code can't
  get in by accident.

**CI (continuous integration)**
: The same checks running automatically on GitHub every time code is pushed.

**Regression test**
: A test that guards against breaking something that already worked. Our most important one
  checks we can still find RBH-1. See
  [ADR-0010](adr/0010-rbh1-regression-test.md).

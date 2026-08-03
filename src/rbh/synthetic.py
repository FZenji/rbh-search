"""Parametric synthetic wakes.

The point of this generator is not to be beautiful, it is to be *tunable along the axes
that change whether a wake is found*. Phase 1 showed that clumpiness is one of those axes:
a wake arrives as a chain of knots joined by faint bridges, the threshold cuts the bridges,
and a fragmented feature fails the length and axis-ratio cuts entirely. A smooth ribbon
never experiences that, which is why ADR-0017 refuses to let this module stand on its own.

``clumpiness`` therefore redistributes flux along the feature **without changing its total
magnitude**, so the completeness grid can vary lumpiness at fixed brightness and isolate
its effect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy import ndimage

if TYPE_CHECKING:
    from numpy.typing import NDArray

#: Gaussian sigma to FWHM.
_FWHM_PER_SIGMA = 2.3548200450309493


@dataclass(frozen=True)
class WakeParameters:
    """The shape of one synthetic wake.

    Defaults are **fitted** to reproduce the transplanted real RBH-1's recovery statistics,
    not taken from the published measurements. See ADR-0017: the fit minimises the combined
    mismatch in recovered length, measured width and fragmentation rate over a joint grid,
    because the parameters interact (widening a feature at fixed flux lowers its peak
    surface brightness, so less of it clears the threshold and the recovered length drops).

    Two of the fitted values deserve flagging:

    * ``width_arcsec`` comes out at 0.22, against a published intrinsic 0.06-0.15. This
      parameter is **degenerate with the effective PSF**, which cannot be measured from the
      discovery cutout because it contains no stars. An effective drizzled PSF nearer 0.2
      arcsec would reconcile the two exactly. The generator is therefore calibrated for
      *detectability*, and its width must not be read as a physical claim about wake widths.
    * ``clumpiness`` is weakly determined and its fitted value has moved twice, for reasons
      that were each time a defect elsewhere rather than new information about wakes. See
      the attribute for the history; nothing downstream is allowed to depend on it, because
      the completeness grid scans it explicitly.

    The longitudinal shape - ``bright_fraction``, ``edge_power``, ``tail_brightness`` - is
    **not** fitted through injection-recovery. It is read directly off the real object's
    measured flux profile, which is a second's arithmetic on sixteen numbers rather than an
    hour of trials, and which is how a monotonic ramp was finally caught masquerading as the
    shape of a feature that actually falls to zero at both ends.
    """

    length_arcsec: float = 8.10
    #: Fitted, and degenerate with the effective PSF - see the class docstring. It went to
    #: 0.28 on the first post-blind-test fit and back to 0.22 once ``width_jitter`` was
    #: fitted alongside it rather than guessed: the two trade directly, since a feature
    #: that swings wider and narrower along its length has a different collapsed width
    #: from a uniform one of the same base. Neither is meaningful without the other, which
    #: is why the grid is joint.
    width_arcsec: float = 0.22
    position_angle_deg: float = 148.3
    #: Maximum deviation of the spine from a straight line. The sign and the position of the
    #: bend are randomised per render: an earlier version bowed every wake the same way, and
    #: a human spotted "a slight curve in the same direction" as a tell in the blind test.
    curvature_arcsec: float = 0.10
    #: Random deviation of the spine from a straight line, drawn over several nodes along
    #: the length so the path can **change direction mid-trail** rather than bowing once.
    #: ``curvature_arcsec`` is a single parabola: smooth, one sign, one vertex, and a
    #: participant who had already seen the real object described the synthetics as having
    #: "no jumps or lumps, or changes in direction mid trail, like the RBH-1 has". A single
    #: bow cannot produce that however its sign and vertex are randomised. The node profile
    #: is piecewise linear, so the direction genuinely changes at each node.
    #: Constrained by the straightness residual in the calibration objective, not guessed.
    path_wander_arcsec: float = 0.14
    #: Fractional variation of the transverse width along the feature. Real wakes are lumpy
    #: in width as well as brightness; a constant-width Gaussian ribbon reads as "extremely
    #: clean and linear", which is how the blind test was won.
    #: Interpreted as a log-width scatter: 0.6 swings the width by a factor of about 1.8
    #: either way along the feature. Fitted, not guessed - it was set by eye once and was
    #: immediately the strongest remaining discriminator in the blind-test pre-flight.
    width_jitter: float = 0.3
    #: 0 = a smooth ribbon, 1 = flux entirely concentrated into discrete knots.
    #:
    #: This sat at 0.0 for as long as brightness was modelled as a monotonic ramp, and that
    #: was recorded here as a finding - "most of RBH-1's fragmentation is the threshold
    #: cutting a smooth feature, not intrinsic lumpiness". **It was an artefact.** A ramp
    #: fading to nothing at one end already fragments constantly, so the fit had no budget
    #: left for real knots and drove this to zero. With the measured flat-topped window in
    #: place the same fit prefers 0.4, and the residual scatter of the real profile within
    #: its bright segment is 0.242 - genuinely lumpy, as a participant said twice.
    #:
    #: Treat the value as weakly determined: the cost surface along this axis is flat
    #: within noise (1.38, 1.54, 1.23 at 0.0, 0.2, 0.4). The completeness grid varies it
    #: explicitly regardless, which is the reason nothing downstream depends on the fit.
    clumpiness: float = 0.4
    n_clumps: int = 6
    #: Width of an individual knot along the axis, as a fraction of total length.
    clump_length_fraction: float = 0.07
    #: Fraction of the total length that carries the flux. The profile is flat-topped over
    #: this fraction and falls to zero on both sides of it.
    #:
    #: This exists because the real object was finally measured. RBH-1's flux per unit
    #: length, in bins of 0.54 arcsec, runs
    #: ``0.00 0.00 0.09 0.74 0.51 0.39 0.54 0.69 0.88 1.00 0.41 0.91 0.93 0.08 0.00 0.00``
    #: - **zero at both ends**, lumpy in between, and with no systematic trend across the
    #: bright part. The generator had modelled brightness as a monotonic ramp across the
    #: whole length, a shape that cannot produce that however its parameters are set. The
    #: calibration compensated by driving the ramp as steep as it would go, which fades one
    #: end and is precisely the "shooting star" reported in round 1 of the blind test.
    #:
    #: Constrained by the recovered length, which is already in the objective: the
    #: transplant is injected at 8.10 arcsec and recovered at 5.61, and this fraction is
    #: what sets that ratio honestly rather than by a ramp dipping below the threshold.
    #:
    #: 0.65 comes from a least-squares fit of this window to the measured profile. **How
    #: much of that fit to believe is itself a measurement**: the residual scatter inside
    #: the bright segment is 0.242 against a mean residual of 0.118, so the bins are
    #: dominated by lumpiness rather than by the smooth shape. What the sixteen bins do
    #: support is "falls to zero at both ends, over roughly two thirds of the length". They
    #: do not support the third decimal place, and the calibration grid scans around this.
    bright_fraction: float = 0.72
    #: How sharply the profile falls at the ends of the bright segment. 2 is a Gaussian
    #: taper, large values approach a hard-edged box. The measured profile drops from 0.74
    #: to 0.09 to 0.00 over about one bin, so it is much closer to a box - but the direct
    #: fit simply runs to whatever upper bound it is given, which means the data say "sharp"
    #: and nothing more precise. 8 is sharp without pretending to a precision that is not
    #: there, and it is deliberately not a fitted axis for the same reason.
    edge_power: float = 8.0
    #: Brightness of one end of the bright segment relative to the other, *within* the
    #: window above rather than across the whole length.
    #:
    #: The direct fit returns 0.20, a strong trend, but that is it fitting the lumps: the
    #: bright bins run 0.74, 0.51, 0.39, 0.54, 0.69, 0.88, 1.00, 0.41, 0.91, 0.93, which is
    #: a weak rise buried in scatter twice its size. Set to 0.80 - a gentle asymmetry, the
    #: most the data actually support - and left as a fitted axis so detectability can
    #: refine what the profile alone cannot.
    tail_brightness: float = 0.60
    #: Extra flux in a compact knot at the leading tip, as a fraction of the total.
    #:
    #: Default **0**, changed from 0.12 after the blind test. None of the four calibration
    #: statistics is sensitive to this parameter, so the fit never constrained it and it sat
    #: at a guessed value - which produced a bright compact head that made every synthetic
    #: read as a "shooting star". The transplant template is the *detected* part of RBH-1 and
    #: has no such head at either end, so zero is also the value that matches the reference.
    #: A real wake may well have a terminal knot; ours is not detected as one.
    terminal_knot_fraction: float = 0.0
    #: Integrated magnitude in the bluer band.
    total_mag_ab: float = 23.6
    #: Colour (blue minus red) at the feature centre.
    colour_ab: float = 0.63
    #: Colour gradient along the axis, magnitudes per arcsec, measured from tail to tip.
    colour_gradient: float = -0.047

    def __post_init__(self) -> None:
        if not 0.0 <= self.clumpiness <= 1.0:
            msg = f"clumpiness must be in [0, 1], got {self.clumpiness}"
            raise ValueError(msg)
        if self.length_arcsec <= 0 or self.width_arcsec <= 0:
            msg = "length and width must be positive"
            raise ValueError(msg)
        if self.n_clumps < 1:
            msg = "n_clumps must be at least 1"
            raise ValueError(msg)


def _spine_coordinates(
    shape: tuple[int, int],
    centre: tuple[float, float],
    position_angle_deg: float,
    pixel_scale_arcsec: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return along-axis and across-axis coordinates in arcsec for every pixel."""
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]].astype(np.float64)
    # Position angle is measured north through east; with north up and east left, that is
    # a rotation from the +y axis toward -x.
    theta = math.radians(position_angle_deg)
    along_dir = np.array([-math.sin(theta), math.cos(theta)])
    across_dir = np.array([along_dir[1], -along_dir[0]])
    dx = (xs - centre[1]) * pixel_scale_arcsec
    dy = (ys - centre[0]) * pixel_scale_arcsec
    along = dx * along_dir[0] + dy * along_dir[1]
    across = dx * across_dir[0] + dy * across_dir[1]
    return along, across


def _longitudinal_profile(
    along: NDArray[np.float64], params: WakeParameters, rng: np.random.Generator
) -> NDArray[np.float64]:
    """Brightness along the feature: a flat-topped window, modulated by knots.

    The window is the shape RBH-1 actually has - see ``bright_fraction``. It replaced a
    monotonic ramp across the full length, which could not put low flux at *both* ends and
    so forced the calibration into an extreme asymmetry to fake a compact bright region.
    """
    half = params.length_arcsec / 2.0
    inside = np.abs(along) <= half

    # Flat-topped window: roughly constant over bright_fraction of the length, falling to
    # zero on both sides. edge_power controls how boxy the fall is.
    half_bright = max(0.5 * params.bright_fraction * params.length_arcsec, 1e-6)
    window = np.exp(-(np.abs(along / half_bright) ** params.edge_power))

    # Gentle asymmetry within the bright segment. The measured profile is close to
    # symmetric, so this is a small correction rather than the main shape.
    t = np.clip((along + half) / params.length_arcsec, 0.0, 1.0)
    ramp = window * (params.tail_brightness + (1.0 - params.tail_brightness) * t)

    # Knots at jittered positions along the axis. Flux is redistributed, not added: the
    # modulation has mean 1 by construction, so total magnitude stays fixed and only the
    # lumpiness changes.
    sigma = max(params.clump_length_fraction * params.length_arcsec, 1e-6) / _FWHM_PER_SIGMA
    edges = np.linspace(-half, half, params.n_clumps + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    spacing = params.length_arcsec / params.n_clumps
    jitter = rng.uniform(-0.35, 0.35, size=params.n_clumps) * spacing
    strengths = rng.uniform(0.6, 1.4, size=params.n_clumps)

    knots = np.zeros_like(along)
    for centre, offset, strength in zip(centres, jitter, strengths, strict=True):
        knots += strength * np.exp(-0.5 * ((along - (centre + offset)) / sigma) ** 2)
    if knots.max() > 0:
        knots /= knots[inside].mean() if inside.any() and knots[inside].mean() > 0 else 1.0
    modulation = (1.0 - params.clumpiness) + params.clumpiness * knots

    profile = ramp * modulation
    return np.where(inside, profile, 0.0)


def _smooth_random_profile(
    along: NDArray[np.float64],
    half_length: float,
    rng: np.random.Generator,
    n_nodes: int = 7,
) -> NDArray[np.float64]:
    """Return a smooth random function of position along the feature, in roughly [-1, 1].

    Built by interpolating random node values rather than summing sinusoids, so it has no
    periodicity for an eye to latch onto.
    """
    nodes = np.linspace(-half_length, half_length, n_nodes)
    values = rng.uniform(-1.0, 1.0, size=n_nodes)
    return np.interp(along, nodes, values)


def render_wake(
    params: WakeParameters,
    shape: tuple[int, int],
    pixel_scale_arcsec: float,
    *,
    psf_fwhm_arcsec: float,
    centre: tuple[float, float] | None = None,
    rng: np.random.Generator | None = None,
) -> NDArray[np.float64]:
    """Render the wake's spatial shape, normalised to unit total flux.

    The intrinsic feature is built first and the PSF applied afterwards, so that knots are
    blurred exactly as real ones are. Returning a unit-flux shape keeps photometry and
    morphology independent: callers scale by whatever total flux each band needs.
    """
    rng = rng if rng is not None else np.random.default_rng(0)
    if centre is None:
        centre = (shape[0] / 2.0, shape[1] / 2.0)

    along, across = _spine_coordinates(shape, centre, params.position_angle_deg, pixel_scale_arcsec)

    # Bend the spine. The sign and the vertex position are drawn per render: with both fixed,
    # every synthetic bowed the same way and that was one of the tells in the blind test.
    half = params.length_arcsec / 2.0
    if params.curvature_arcsec != 0.0 and half > 0:
        sign = 1.0 if rng.random() < 0.5 else -1.0
        vertex = float(rng.uniform(-0.4, 0.4)) * half
        span = max(half + abs(vertex), 1e-9)
        bend = sign * params.curvature_arcsec * (1.0 - ((along - vertex) / span) ** 2)
        across = across - np.where(np.abs(along) <= half, bend, 0.0)

    # Wander the spine over several nodes, on top of the single bend. The bend is one
    # smooth bow; this is what lets the path change direction partway along, which is what
    # a participant reported the synthetics could not do.
    if params.path_wander_arcsec > 0.0 and half > 0:
        wander = params.path_wander_arcsec * _smooth_random_profile(along, half, rng)
        across = across - np.where(np.abs(along) <= half, wander, 0.0)

    # Width varies along the feature. A constant-width Gaussian ribbon is what reads as
    # "extremely clean and linear"; real wakes thicken and thin along their length.
    width_sigma = params.width_arcsec / _FWHM_PER_SIGMA
    if params.width_jitter > 0:
        # Exponential, not (1 + jitter * wobble). A width is a positive quantity, so the
        # natural symmetry is multiplicative: exp(+j) widens by exactly the factor exp(-j)
        # narrows. The linear form had to be clipped from below to stop it reaching zero,
        # and above jitter ~0.65 that clip bit on every negative excursion - the narrowing
        # saturated while the widening kept growing, so raising the parameter quietly made
        # the feature wider on average instead of more variable. The calibration then fitted
        # jitter into exactly that regime, which is how the bias was found.
        wobble = _smooth_random_profile(along, half, rng)
        local_sigma = width_sigma * np.exp(params.width_jitter * wobble)
    else:
        local_sigma = np.full_like(along, width_sigma)

    transverse = np.exp(-0.5 * (across / local_sigma) ** 2)
    image = _longitudinal_profile(along, params, rng) * transverse

    if params.terminal_knot_fraction > 0:
        knot_sigma = max(params.width_arcsec, 1.5 * pixel_scale_arcsec) / _FWHM_PER_SIGMA
        knot = np.exp(-0.5 * (((along - half) ** 2 + across**2) / knot_sigma**2))
        total = image.sum()
        if total > 0 and knot.sum() > 0:
            image = image / total + params.terminal_knot_fraction * knot / knot.sum()

    if psf_fwhm_arcsec > 0:
        psf_sigma_px = psf_fwhm_arcsec / _FWHM_PER_SIGMA / pixel_scale_arcsec
        image = ndimage.gaussian_filter(image, psf_sigma_px, mode="constant")

    total = image.sum()
    return image / total if total > 0 else image


def render_bands(
    params: WakeParameters,
    shape: tuple[int, int],
    pixel_scale_arcsec: float,
    zeropoints: dict[str, float],
    *,
    psf_fwhm_arcsec: float,
    centre: tuple[float, float] | None = None,
    rng: np.random.Generator | None = None,
) -> dict[str, NDArray[np.float32]]:
    """Render the wake in each band, in the same flux units as the tile's science arrays.

    ``zeropoints`` must be ordered blue-first: the first entry is treated as the band
    ``total_mag_ab`` refers to, and the second is offset by ``colour_ab``. The colour
    gradient is imposed as a multiplicative along-axis weighting on the redder band,
    normalised to leave the integrated colour unchanged.
    """
    names = list(zeropoints)
    if not names:
        msg = "at least one band is required"
        raise ValueError(msg)
    if centre is None:
        centre = (shape[0] / 2.0, shape[1] / 2.0)

    shape_image = render_wake(
        params,
        shape,
        pixel_scale_arcsec,
        psf_fwhm_arcsec=psf_fwhm_arcsec,
        centre=centre,
        rng=rng,
    )
    along, _ = _spine_coordinates(shape, centre, params.position_angle_deg, pixel_scale_arcsec)

    out: dict[str, NDArray[np.float32]] = {}
    for index, name in enumerate(names):
        magnitude = params.total_mag_ab if index == 0 else params.total_mag_ab - params.colour_ab
        weighting = np.ones_like(shape_image)
        if index > 0 and params.colour_gradient != 0.0:
            weighting = np.power(10.0, 0.4 * params.colour_gradient * along)
            mean = float((shape_image * weighting).sum())
            if mean > 0:
                weighting = weighting / mean
        flux = 10.0 ** (-0.4 * (magnitude - zeropoints[name]))
        out[name] = (shape_image * weighting * flux).astype(np.float32)
    return out

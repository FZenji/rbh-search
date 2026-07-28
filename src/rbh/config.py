"""Run configuration.

Every field here is part of the selection function. A run's resolved settings are
hashed and stamped onto every output row so that a candidate can always be traced back
to the exact thresholds that produced it (ADR-0012).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SelectionWindow(BaseModel):
    """The region of observable parameter space the pipeline is sensitive to.

    Defaults bracket RBH-1 with margin, and correspond to a wake of 20-150 kpc seen
    over roughly 0.4 < z < 2. See ADR-0007 for the derivation.
    """

    model_config = ConfigDict(frozen=True)

    min_length_arcsec: float = Field(default=2.0, gt=0.0)
    max_length_arcsec: float = Field(default=25.0, gt=0.0)
    max_width_arcsec: float = Field(default=0.60, gt=0.0)
    min_axis_ratio: float = Field(default=8.0, gt=1.0)
    max_straightness_residual_arcsec: float = Field(
        default=0.35,
        gt=0.0,
        description="RMS deviation of the ridge from its best-fit straight line.",
    )
    min_ridge_snr: float = Field(
        default=5.0,
        gt=0.0,
        description="Noise-normalised ridge-filter response required for a detection.",
    )


class Settings(BaseSettings):
    """Top-level run settings, populated from environment variables prefixed ``RBH_``."""

    model_config = SettingsConfigDict(
        env_prefix="RBH_",
        env_nested_delimiter="__",
        frozen=True,
        extra="forbid",
    )

    offline: bool = Field(
        default=False,
        description="Refuse all network access. Set in CI so tests cannot silently "
        "depend on MAST or AWS availability.",
    )
    tier: Literal["A", "B", "AB"] = Field(
        default="A",
        description="Filter-coverage tier to process. A requires >=2 filters for "
        "cross-filter vetting; B is single-filter. See ADR-0006.",
    )
    selection: SelectionWindow = Field(default_factory=SelectionWindow)
    random_seed: int = Field(
        default=20230208,
        description="Seed for every stochastic step, including synthetic injection. "
        "Fixed by default so runs are bit-reproducible (ADR-0012).",
    )

    def fingerprint(self) -> str:
        """Return a stable hash of the resolved settings.

        Stamped onto every output row. Two runs sharing a fingerprint used identical
        thresholds and therefore share a selection function.
        """
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

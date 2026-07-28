"""A reproducible search for runaway supermassive black hole wakes in HST and JWST imaging.

The package is in its design phase: see ``docs/`` for the architecture and the
architectural decision records that fix its behaviour. No detector is implemented yet.
"""

from rbh.config import Settings
from rbh.reference import RBH1, ReferenceObject

__all__ = ["RBH1", "ReferenceObject", "Settings", "__version__"]

__version__ = "0.1.0"

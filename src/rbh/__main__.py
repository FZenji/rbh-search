"""Entry point for ``python -m rbh``.

The console script installed by the package is the usual way in, but a module entry point is
what lets a subprocess invoke the CLI without depending on a ``PATH`` lookup - which is how
the Phase 3 gate exercise drives a real sweep and kills it.
"""

from rbh.cli import app

if __name__ == "__main__":
    app()

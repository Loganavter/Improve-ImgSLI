"""Qt-free analysis engine core: contracts, producer registry, context, catalog.

Package docstring only — no imports, so ``import engine.analysis`` never pulls
a discovery scan or a heavier module. Callers import the submodule they need.

Layout mirrors the plan's target (``src/engine/analysis/``):

- ``contracts`` — the immutable records (``AxisValue``, ``ProducerSpec``, …)
- ``registry`` — auto-discovered producer packages (``manifest.py`` metadata)
- ``context`` — the item context a producer reads instead of decoding
- ``catalog`` — the only place a provider/model identity is resolved

The engine layer is imported by tab producers and never names its callers.
"""

__all__: list[str] = []

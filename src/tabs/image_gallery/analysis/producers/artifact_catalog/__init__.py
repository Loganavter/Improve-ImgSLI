"""``artifact_catalog`` producer package: manifest + ``run(ctx)``.

One package for the whole seven-axis artifact catalog, because the production
path is one aggregate call (``artifacts.analyze_images``), not seven detectors:
the aggregate layers the source-anchoring policy over four absolute detectors,
so a per-detector producer would report a different severity than the catalog
the report already shows.
"""

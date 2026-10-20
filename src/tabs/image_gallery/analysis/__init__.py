"""Gallery analysis adapters — the tab side of ``engine.analysis`` (W3 read path).

Holds the per-axis read path (``read.py``): the ONE place that turns an item's
stored analysis (the VLM scorecard) or metrics (the local detectors) into
``AxisValue`` records that carry their own producer, status and gap reason.
Producer packages (``producers/*``) arrive in W4/W5 and are discovered by
``engine.analysis.registry``; nothing here wires a producer by hand.

``read.py`` imports no Qt at runtime (only the Qt-free ``models`` dataclasses and
the two ``quality_read`` primitives), so headless tests can exercise it as-is.
"""

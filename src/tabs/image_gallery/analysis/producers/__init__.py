"""Auto-discovered local analysis producers for the gallery (W5).

One package per analyzer family, found by ``engine.analysis.registry``'s
directory scan — nothing here is hand-wired into a central file (plan
§"Analyzers are auto-discovered producer packages"):

- ``camera_scalars``     — measured, reference-free scalars;
- ``fidelity_reference`` — measured source-relative deltas;
- ``artifact_catalog``   — the seven artifact candidate flags, in one package
  because the production path is one aggregate call
  (``artifacts.analyze_images``) whose source-anchoring delta sits above the
  detectors; per-detector packages could disagree with the report.

Each package is ``manifest.py`` (metadata only: id, ``provides``, ``requires``,
cost — no imaging or learned-backend import) plus ``producer.py``
(``run(ctx) -> tuple[AxisValue, ...]``). Discovery imports manifests only, so a
manifest that pulled in ``torch`` would load it for every start; the producers
are imported by the resolver's run path instead.

Producers wrap the existing detector math (``services/camera_metrics.py``,
``services/fidelity_metrics.py``, ``services/artifacts.py``) and never re-decode:
they read the already-decoded images of an ``AnalysisContext``. A producer that
opened a file or built a store would multiply the per-item decode work that
``services/proxy.py`` exists to prevent (plan trap 1 / gate G11).
"""

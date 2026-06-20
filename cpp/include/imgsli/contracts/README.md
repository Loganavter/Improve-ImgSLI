# Frozen Contract Headers

This directory holds canonical C++ headers that mirror the Python contracts
defined under `src/ui/canvas_infra/scene/`.

Current contents:
- `canvas_widget_feature.h` — Phase 3 C++ interface with semantic commands,
  defaults, `Q_DECLARE_INTERFACE`, and static registration support.

Remaining contract headers:
- `canvas_feature_property.h` — mirror of `feature_contract.py::CanvasFeatureProperty`.
- `gl_pass_contract.h` — mirror of `gl_pass_contract.py`.
- `canvas_render_plan.h` — POD shape produced by Rust PlanBuilder, consumed by C++ PlanApplicator.

Each header will reference the Python source by file:line for traceability while the
port is in progress.

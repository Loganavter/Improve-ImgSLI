//! Cross-feature helpers that don't belong to a single tab or plugin.
//!
//! Mirrors Python `src/shared/`. The `image_processing` sub-tree stays in C++
//! (Qt is the natural home for QImage manipulation); only the pure-logic
//! pieces — like the canvas `PlanBuilder` — live here.

pub mod rendering;

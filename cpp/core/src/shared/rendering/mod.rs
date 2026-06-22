//! Shared canvas-render helpers. Mirrors Python `src/shared/rendering/`.
//!
//! `layout_contract.py` already lives in [`crate::ui::canvas::virtual_layout`];
//! the remaining pure-logic pieces — currently just the canvas plan builder —
//! land here.

pub mod plan_builder;

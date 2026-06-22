//! imgsli-core
//!
//! Pure-logic core for the ImgSLI C++/Rust port.
//!
//! Layout mirrors the Python tree under `src/`:
//!
//! - [`core`]       — state, store, reducer, actions (mirrors `src/core/`).
//! - [`plugins`]    — plugin-owned models (settings, analysis, video editor).
//! - [`ui`]         — canvas plan/layout/hit-test/image cache.
//! - [`tabs`]       — tab-specific logic (multi-compare playlist).
//! - [`shared`]     — cross-cutting helpers (canvas plan builder).
//! - [`workspace`]  — session blueprint hydration.
//! - [`domain`]     — value primitives (Point, Color, Rect).
//! - [`i18n`]       — translation catalog (cross-cutting).
//!
//! The FFI surface exposed to C++ lives in [`bridge`] — keep that file
//! narrow and never let Qt or QRHI types cross.

pub mod bridge;
pub mod core;
pub mod domain;
pub mod i18n;
pub mod plugins;
pub mod shared;
pub mod tabs;
pub mod ui;
pub mod workspace;

pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

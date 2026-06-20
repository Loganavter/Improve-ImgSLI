//! imgsli-core
//!
//! Pure-logic core for the ImgSLI C++/Rust port.
//!
//! Modules:
//! - [`domain`]       — value primitives (Point, Color, Rect).
//! - [`settings`]     — `SettingsState` mirroring `core/store_settings.py`.
//! - [`state`]        — viewport / document / workspace state shape.
//! - [`action`]       — discrete state-mutating intents.
//! - [`reducer`]      — pure `(state, action) -> state` + scope.
//! - [`store`]        — store + subscriber notification.
//! - [`plan`]         — canvas render plan POD types.
//! - [`plan_keys`]    — cache discriminators and letterbox math.
//! - [`hit_test`]     — pure geometry helpers backing the scene hit-test pipeline.
//! - [`image_cache`]  — LRU image-pair cache.
//!
//! The FFI surface exposed to C++ lives in [`bridge`] — keep that file
//! narrow and never let Qt or QRHI types cross.

pub mod action;
pub mod bridge;
pub mod domain;
pub mod hit_test;
pub mod image_cache;
pub mod plan;
pub mod plan_keys;
pub mod reducer;
pub mod settings;
pub mod settings_dialog;
pub mod stacking;
pub mod state;
pub mod store;

pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

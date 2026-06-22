//! Actions — discrete state-mutating intents.
//!
//! In the Python codebase actions are scattered across mixin methods on
//! `Store` (and direct attribute writes). The Rust port consolidates them
//! into one enum so the reducer is exhaustive and total.
//!
//! Phase 1 surface: settings, view-state, geometry, interaction, document
//! navigation, workspace session lifecycle. Feature-coupled actions (e.g.
//! per-feature canvas state) round-trip through the opaque
//! `ViewState::feature_state` JSON value until C++ feature contracts land.

use serde::{Deserialize, Serialize};

use crate::core::state::{ImageItem, Slot};
use crate::domain::{Point, Rect};
use crate::ui::canvas::plan::TextureId;

/// All state-mutating intents. Keep it flat — pattern matching in the reducer
/// scales much better than nesting once the enum grows past a handful of
/// variants.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
// SettingsState intentionally remains inline so the JSON action contract is
// identical across Rust, C++, and the temporary PyO3 validation shim.
#[allow(clippy::large_enum_variant)]
pub enum Action {
    // ---- Settings ----
    SetLanguage(String),
    SetTheme(String),
    SetUiMode(String),
    SetDebugMode(bool),
    SetSystemNotifications(bool),
    SetAutoCropBlackBorders(bool),
    SetRhiBackend(String),
    SetWindowGeometry {
        x: i32,
        y: i32,
        w: i32,
        h: i32,
        maximized: bool,
    },
    /// Replace the entire settings struct (used when loading from disk).
    LoadSettings(crate::plugins::settings::model::SettingsState),

    // ---- View ----
    SetSplitPosition(f32),
    SetSplitVisualPosition(f32),
    SetSplitOrientation {
        is_horizontal: bool,
    },
    SetDiffMode(String),
    SetChannelViewMode(String),
    SetOverlayEnabled(bool),
    SetShowingSingleImageMode(i32),

    // ---- Geometry ----
    SetPixmapSize {
        w: i32,
        h: i32,
    },
    SetDisplayRect(Rect),
    SetFixedLabelSize {
        w: Option<i32>,
        h: Option<i32>,
    },
    SetOverlayScreenCenter(Point),

    // ---- Interaction ----
    BeginInteractiveSession,
    EndInteractiveSession,
    SetDraggingSplitLine(bool),
    SetSpaceBarPressed(bool),
    KeyPressed(i32),
    KeyReleased(i32),

    // ---- Document ----
    SetCurrentIndex {
        slot: Slot,
        index: i32,
    },
    AddImageItem {
        slot: Slot,
        item: ImageItem,
    },
    RemoveImageItem {
        slot: Slot,
        index: i32,
    },
    SetActiveImagePath {
        slot: Slot,
        path: Option<String>,
    },
    BindTextureToSlot {
        slot: Slot,
        texture: TextureId,
    },

    // ---- Workspace ----
    CreateSession {
        title: String,
        session_type: String,
        activate: bool,
    },
    CreateSessionFromBlueprint {
        title: Option<String>,
        blueprint: crate::workspace::session_blueprint::SessionBlueprint,
        activate: bool,
    },
    SwitchSession(String),
    CloseSession(String),
    RenameSession {
        id: String,
        title: String,
    },

    // ---- Opaque ----
    /// Phase 1B placeholder: replace the per-feature blob inside the active
    /// session's `view_state.feature_state`. Kept for back-compat with
    /// JSON-mutating callers; new code dispatches `SetCanvasFeature` with a
    /// typed sub-action below.
    SetFeatureState(serde_json::Value),

    /// Typed alternative to `SetFeatureState`. The reducer merges the typed
    /// payload into the same `feature_state` JSON so existing consumers see
    /// no contract change, but new callers get compile-time variant
    /// coverage and zero ad-hoc JSON construction.
    SetCanvasFeature(FeatureAction),
}

/// Typed per-feature sub-actions. Each variant maps 1:1 to a single
/// field write under `feature_state.<feature>.<key>`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum FeatureAction {
    // Divider
    SetDividerVisible(bool),
    SetDividerThickness(f32),

    // Magnifier
    SetMagnifierVisible(bool),
    SetMagnifierX(f32),
    SetMagnifierY(f32),
    SetMagnifierRadius(f32),
    SetMagnifierZoom(f32),

    // Capture (paired with magnifier)
    SetCaptureVisible(bool),
    SetCaptureX(f32),
    SetCaptureY(f32),

    // Guides
    SetGuidesVisible(bool),

    // Filename overlay
    SetFilenameOverlayVisible(bool),
    SetFilenameLeft(String),
    SetFilenameRight(String),

    // Paste overlay
    SetPasteOverlayVisible(bool),
}

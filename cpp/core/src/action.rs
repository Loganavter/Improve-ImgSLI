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

use crate::domain::{Point, Rect};
use crate::plan::TextureId;
use crate::state::{ImageItem, Slot};

/// All state-mutating intents. Keep it flat — pattern matching in the reducer
/// scales much better than nesting once the enum grows past a handful of
/// variants.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
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
    LoadSettings(crate::settings::SettingsState),

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
    SwitchSession(String),
    CloseSession(String),
    RenameSession {
        id: String,
        title: String,
    },

    // ---- Opaque ----
    /// Phase 1B placeholder: replace the per-feature blob inside the active
    /// session's `view_state.feature_state`. C++ feature commands will be
    /// dispatched via this action until they get their own typed variants.
    SetFeatureState(serde_json::Value),
}

//! Application state — POD shape of the Python `ViewportState` family.
//!
//! Mirrors `src/core/store_viewport.py`, `src/core/store_document.py`,
//! `src/domain/workspace.py`. Two simplifications vs. Python:
//!
//! * Image handles (`Optional[Any]` PIL/QImage in Python) are represented by
//!   [`crate::ui::canvas::plan::TextureId`]. Anything Rust needs to know about an image is
//!   its identity and size; pixel ownership stays on the C++ side after the
//!   final cutover.
//! * Per-feature plugin state (`canvas_widget_state` dict, `viewport_plugin_state`,
//!   `analysis_plugin_state`) is **not** ported here — that lives behind the
//!   C++ feature contracts (Phase 3). We carry it as an opaque `serde_json::Value`
//!   so the reducer can pass it through unchanged.

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

use crate::domain::{Color, Point, Rect};
use crate::ui::canvas::plan::TextureId;

/// Pure-data render configuration. Mirrors `RenderConfig` in
/// `core/store_viewport.py`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RenderConfig {
    pub interpolation_method: String,
    pub zoom_interpolation_method: String,
    pub movement_interpolation_method: String,
    pub interactive_movement_interpolation_method: String,
    pub display_resolution_limit: i32,
    pub jpeg_quality: i32,
    pub include_file_names_in_saved: bool,
    pub font_size_percent: i32,
    pub font_weight: i32,
    pub text_alpha_percent: i32,
    pub file_name_color: Color,
    pub file_name_bg_color: Color,
    pub draw_text_background: bool,
    pub text_placement_mode: String,
    pub max_name_length: i32,
}

impl Default for RenderConfig {
    fn default() -> Self {
        Self {
            interpolation_method: "BILINEAR".into(),
            zoom_interpolation_method: "BILINEAR".into(),
            movement_interpolation_method: "BILINEAR".into(),
            interactive_movement_interpolation_method: "BILINEAR".into(),
            display_resolution_limit: 0,
            jpeg_quality: 95,
            include_file_names_in_saved: false,
            font_size_percent: 120,
            font_weight: 0,
            text_alpha_percent: 100,
            file_name_color: Color::new(255, 0, 0, 255),
            file_name_bg_color: Color::new(0, 0, 0, 80),
            draw_text_background: true,
            text_placement_mode: "edges".into(),
            max_name_length: 50,
        }
    }
}

/// Mirrors `ViewState` (POD subset, no Qt feature dicts).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ViewState {
    pub split_position: f32,
    pub split_position_visual: f32,
    pub is_horizontal: bool,
    pub diff_mode: String,
    pub channel_view_mode: String,
    pub optimize_interactive_movement: bool,
    pub overlay_enabled: bool,
    pub highlighted_overlay_element: Option<String>,
    pub showing_single_image_mode: i32,
    pub movement_speed_per_sec: f32,
    pub text_bg_visual_height: f32,
    pub text_bg_visual_width: f32,
    /// Opaque feature state (`canvas_widget_state` in Python). Pass-through.
    pub feature_state: serde_json::Value,
}

impl Default for ViewState {
    fn default() -> Self {
        Self {
            split_position: 0.5,
            split_position_visual: 0.5,
            is_horizontal: false,
            diff_mode: "off".into(),
            channel_view_mode: "RGB".into(),
            optimize_interactive_movement: true,
            overlay_enabled: false,
            highlighted_overlay_element: None,
            showing_single_image_mode: 0,
            movement_speed_per_sec: 2.0,
            text_bg_visual_height: 0.0,
            text_bg_visual_width: 0.0,
            feature_state: serde_json::Value::Null,
        }
    }
}

/// Mirrors `GeometryState`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct GeometryState {
    pub pixmap_width: i32,
    pub pixmap_height: i32,
    pub image_display_rect_on_label: Rect,
    pub fixed_label_width: Option<i32>,
    pub fixed_label_height: Option<i32>,
    pub active_overlay_screen_center: Point,
    pub active_overlay_screen_size: i32,
    /// `loaded_geometry` in Python is `bytes` (Qt window geometry blob); kept
    /// as opaque bytes so settings round-trips work.
    #[serde(with = "serde_bytes")]
    pub loaded_geometry: Vec<u8>,
    pub loaded_was_maximized: bool,
    #[serde(with = "serde_bytes")]
    pub loaded_previous_geometry: Vec<u8>,
    pub loaded_debug_mode_enabled: bool,
}

/// Mirrors `InteractionState`. `pressed_keys` is a set of Qt key codes — we
/// keep it as `HashSet<i32>` so the reducer can carry it across actions
/// without committing to Qt's enum (which lives on the C++ side).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct InteractionState {
    pub resize_in_progress: bool,
    pub is_interactive_mode: bool,
    pub is_dragging_split_line: bool,
    pub is_dragging_overlay_handle: bool,
    pub is_dragging_overlay_split: bool,
    pub is_dragging_any_slider: bool,
    pub interaction_session_id: u64,
    pub is_user_interacting: bool,
    pub pressed_keys: HashSet<i32>,
    pub last_horizontal_movement_key: Option<i32>,
    pub last_vertical_movement_key: Option<i32>,
    pub last_spacing_movement_key: Option<i32>,
    pub space_bar_pressed: bool,
    pub interactive_offset_relative_visual: Point,
    pub interactive_spacing_relative_visual: f32,
    pub interactive_internal_split_visual: f32,
}

impl Default for InteractionState {
    fn default() -> Self {
        Self {
            resize_in_progress: false,
            is_interactive_mode: false,
            is_dragging_split_line: false,
            is_dragging_overlay_handle: false,
            is_dragging_overlay_split: false,
            is_dragging_any_slider: false,
            interaction_session_id: 0,
            is_user_interacting: false,
            pressed_keys: HashSet::new(),
            last_horizontal_movement_key: None,
            last_vertical_movement_key: None,
            last_spacing_movement_key: None,
            space_bar_pressed: false,
            interactive_offset_relative_visual: Point::default(),
            interactive_spacing_relative_visual: 0.1,
            interactive_internal_split_visual: 0.5,
        }
    }
}

/// Image-side session state. Mirrors `ImageSessionState` minus PIL handles
/// (`image1`/`image2` become `TextureId`s).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct ImageSessionState {
    pub image1: TextureId,
    pub image2: TextureId,
    pub loaded_image1_paths: Vec<String>,
    pub loaded_image2_paths: Vec<String>,
    pub loaded_current_index1: i32,
    pub loaded_current_index2: i32,
    pub auto_calculate_psnr: bool,
    pub auto_calculate_ssim: bool,
    pub psnr_value: Option<f64>,
    pub ssim_value: Option<f64>,
}

/// Mirrors `ViewportState` (composition of the above pieces).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct ViewportState {
    pub render_config: RenderConfig,
    pub view_state: ViewState,
    pub geometry_state: GeometryState,
    pub interaction_state: InteractionState,
    pub image_session: ImageSessionState,
}

impl ViewportState {
    /// Mirrors `ViewportState.freeze_for_export`: reset transient interaction
    /// flags so a snapshot used for export is a clean visual frame.
    pub fn frozen_for_export(&self) -> Self {
        let mut out = self.clone();
        out.interaction_state.space_bar_pressed = false;
        out.interaction_state.pressed_keys.clear();
        out.interaction_state.is_dragging_split_line = false;
        out.interaction_state.is_dragging_overlay_handle = false;
        out.interaction_state.is_dragging_overlay_split = false;
        out.interaction_state.is_dragging_any_slider = false;
        out.interaction_state.is_interactive_mode = false;
        out.interaction_state.is_user_interacting = false;
        out
    }
}

/// One image-list entry. Mirrors `ImageItem`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct ImageItem {
    pub texture: TextureId,
    pub path: String,
    pub display_name: String,
    pub rating: i32,
}

/// Mirrors `DocumentModel` minus PIL handles (replaced with [`TextureId`]).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct DocumentModel {
    pub image_list1: Vec<ImageItem>,
    pub image_list2: Vec<ImageItem>,
    pub current_index1: i32,
    pub current_index2: i32,
    pub original_image1: TextureId,
    pub original_image2: TextureId,
    pub full_res_image1: TextureId,
    pub full_res_image2: TextureId,
    pub image1_path: Option<String>,
    pub image2_path: Option<String>,
    pub preview_image1: TextureId,
    pub preview_image2: TextureId,
    pub full_res_ready1: bool,
    pub full_res_ready2: bool,
    pub preview_ready1: bool,
    pub preview_ready2: bool,
    pub progressive_load_in_progress1: bool,
    pub progressive_load_in_progress2: bool,
    pub last_display_name1: String,
    pub last_display_name2: String,
}

impl DocumentModel {
    pub fn new() -> Self {
        Self {
            current_index1: -1,
            current_index2: -1,
            ..Default::default()
        }
    }

    pub fn has_current_item(&self, slot: Slot) -> bool {
        let (idx, items) = self.slot_view(slot);
        idx >= 0 && (idx as usize) < items.len()
    }

    pub fn active_display_name(&self, slot: Slot) -> &str {
        if !self.has_current_item(slot) {
            return "";
        }
        let (idx, items) = self.slot_view(slot);
        items[idx as usize].display_name.as_str()
    }

    fn slot_view(&self, slot: Slot) -> (i32, &Vec<ImageItem>) {
        match slot {
            Slot::Left => (self.current_index1, &self.image_list1),
            Slot::Right => (self.current_index2, &self.image_list2),
        }
    }
}

/// Which image slot a per-side action operates on. Replaces the
/// `slot: int` (1 or 2) convention in the Python codebase.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Slot {
    Left,
    Right,
}

/// Mirrors `WorkspaceSession`. Plugin-owned values remain JSON so Python-built
/// blueprints can be consumed without importing Python at runtime.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct WorkspaceSession {
    pub id: String,
    pub title: String,
    pub session_type: String,
    pub document: DocumentModel,
    pub viewport: ViewportState,
    pub state_slots: HashMap<String, serde_json::Value>,
    pub resources: HashMap<String, serde_json::Map<String, serde_json::Value>>,
    pub metadata: serde_json::Map<String, serde_json::Value>,
}

/// Mirrors `WorkspaceState`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct WorkspaceState {
    pub sessions: Vec<WorkspaceSession>,
    pub active_session_id: Option<String>,
    pub next_session_counter: u64,
}

impl WorkspaceState {
    pub fn active(&self) -> Option<&WorkspaceSession> {
        let id = self.active_session_id.as_ref()?;
        self.sessions.iter().find(|s| s.id == *id)
    }

    pub fn active_mut(&mut self) -> Option<&mut WorkspaceSession> {
        let id = self.active_session_id.clone()?;
        self.sessions.iter_mut().find(|s| s.id == id)
    }
}

/// Top-level application state. The Python `Store` keeps `workspace`,
/// `document`, `viewport`, `settings` side-by-side at the root — we do
/// the same so the reducer matches the call sites.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct AppState {
    pub settings: crate::plugins::settings::model::SettingsState,
    pub workspace: WorkspaceState,
    pub document: DocumentModel,
    pub viewport: ViewportState,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_match_python() {
        let s = AppState::default();
        assert_eq!(s.viewport.view_state.split_position, 0.5);
        assert_eq!(s.viewport.render_config.font_size_percent, 120);
        assert_eq!(
            s.viewport.render_config.file_name_color,
            Color::new(255, 0, 0, 255)
        );
        assert_eq!(s.document.current_index1, 0); // serde default i32 = 0
        let blank_doc = DocumentModel::new();
        assert_eq!(blank_doc.current_index1, -1);
        assert_eq!(blank_doc.current_index2, -1);
    }

    #[test]
    fn appstate_json_roundtrip() {
        let s = AppState::default();
        let j = serde_json::to_string(&s).unwrap();
        let back: AppState = serde_json::from_str(&j).unwrap();
        assert_eq!(s, back);
    }

    #[test]
    fn freeze_for_export_clears_transient_flags() {
        let mut v = ViewportState::default();
        v.interaction_state.is_interactive_mode = true;
        v.interaction_state.is_dragging_split_line = true;
        v.interaction_state.is_user_interacting = true;
        v.interaction_state.pressed_keys.insert(42);
        v.interaction_state.space_bar_pressed = true;
        let f = v.frozen_for_export();
        assert!(!f.interaction_state.is_interactive_mode);
        assert!(!f.interaction_state.is_dragging_split_line);
        assert!(!f.interaction_state.is_user_interacting);
        assert!(!f.interaction_state.space_bar_pressed);
        assert!(f.interaction_state.pressed_keys.is_empty());
    }

    #[test]
    fn document_active_display_name() {
        let mut d = DocumentModel::new();
        assert_eq!(d.active_display_name(Slot::Left), "");
        d.image_list1.push(ImageItem {
            path: "a.png".into(),
            display_name: "Alpha".into(),
            ..Default::default()
        });
        d.current_index1 = 0;
        assert!(d.has_current_item(Slot::Left));
        assert_eq!(d.active_display_name(Slot::Left), "Alpha");
        assert!(!d.has_current_item(Slot::Right));
    }

    #[test]
    fn workspace_active_lookup() {
        let mut w = WorkspaceState::default();
        w.sessions.push(WorkspaceSession {
            id: "s1".into(),
            title: "Tab 1".into(),
            session_type: "image_compare".into(),
            ..Default::default()
        });
        w.active_session_id = Some("s1".into());
        assert_eq!(w.active().map(|s| s.title.as_str()), Some("Tab 1"));
        w.active_mut().unwrap().title = "Renamed".into();
        assert_eq!(w.active().map(|s| s.title.as_str()), Some("Renamed"));
    }
}

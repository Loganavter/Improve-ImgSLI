//! View-model for the Settings dialog.
//!
//! Mirrors `src/plugins/settings/models.py::SettingsDialogData`. This is the
//! plain value object the C++ Qt dialog binds widgets to and the diff source
//! the application service consumes to dispatch actions and persist values.
//!
//! Unlike [`crate::plugins::settings::model::SettingsState`] (which only owns the subset of
//! fields that survive to disk under the `SettingsState` dataclass), this
//! struct also covers fields backed by `RenderConfig`, `ViewState`, and
//! canvas-feature state. It is therefore not constructible from a single
//! state object — the caller assembles it from the live store.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::plugins::settings::model::SettingsState;

/// Hard-coded limits from `src/core/constants.py::AppConstants`.
pub mod limits {
    pub const MIN_NAME_LENGTH: i32 = 10;
    pub const MAX_NAME_LENGTH: i32 = 150;
    pub const DEFAULT_DISPLAY_RESOLUTION_LIMIT: i32 = 2160;
    pub const MIN_VIDEO_FPS: i32 = 1;
    pub const MAX_VIDEO_FPS: i32 = 240;
}

/// Allowed `display_resolution_limit` values, in render-order.
/// Mirrors `AppConstants.DISPLAY_RESOLUTION_OPTIONS`.
pub const DISPLAY_RESOLUTION_OPTIONS: &[(&str, i32)] = &[
    ("Original", 0),
    ("8K (4320p)", 4320),
    ("4K (2160p)", 2160),
    ("2K (1440p)", 1440),
    ("Full HD (1080p)", 1080),
];

/// Allowed interpolation method keys.
/// Mirrors `AppConstants.INTERPOLATION_METHODS_MAP` keys.
pub const INTERPOLATION_METHODS: &[&str] =
    &["NEAREST", "BILINEAR", "BICUBIC", "LANCZOS", "EWA_LANCZOS"];

/// Speed order — lower means faster.
fn interpolation_speed(method: &str) -> i32 {
    match method {
        "NEAREST" => 0,
        "BILINEAR" => 1,
        "BICUBIC" => 2,
        "LANCZOS" => 3,
        "EWA_LANCZOS" => 4,
        _ => 999,
    }
}

/// Mirrors `AppConstants.is_interpolation_conflict`. True when the
/// "optimization" interpolation is not strictly faster than the main one,
/// so the optimization would be a regression.
pub fn is_interpolation_conflict(main_method: &str, optimization_method: &str) -> bool {
    interpolation_speed(main_method) <= interpolation_speed(optimization_method)
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SettingsDialogData {
    pub language: String,
    pub theme: String,
    pub max_name_length: i32,
    pub debug_enabled: bool,
    pub system_notifications_enabled: bool,
    pub resolution_limit: i32,
    pub ui_font_mode: String,
    pub ui_font_family: String,
    pub optimize_magnifier_movement: bool,
    pub magnifier_interpolation_method: String,
    pub optimize_laser_smoothing: bool,
    pub laser_interpolation_method: String,
    pub zoom_interpolation_method: String,
    pub magnifier_intersection_highlight_enabled: bool,
    pub magnifier_auto_color_new_instances: bool,
    pub auto_calculate_psnr: bool,
    pub auto_calculate_ssim: bool,
    pub auto_crop_black_borders: bool,
    pub ui_mode: String,
    pub video_recording_fps: i32,
    pub show_workspace_tabs: bool,
    pub rhi_backend: String,
}

impl Default for SettingsDialogData {
    fn default() -> Self {
        let s = SettingsState::default();
        Self {
            language: s.current_language,
            theme: s.theme,
            max_name_length: 50,
            debug_enabled: s.debug_mode_enabled,
            system_notifications_enabled: s.system_notifications_enabled,
            resolution_limit: limits::DEFAULT_DISPLAY_RESOLUTION_LIMIT,
            ui_font_mode: s.ui_font_mode,
            ui_font_family: s.ui_font_family,
            optimize_magnifier_movement: true,
            magnifier_interpolation_method: "BILINEAR".into(),
            optimize_laser_smoothing: true,
            laser_interpolation_method: "BILINEAR".into(),
            zoom_interpolation_method: "BILINEAR".into(),
            magnifier_intersection_highlight_enabled: false,
            magnifier_auto_color_new_instances: false,
            auto_calculate_psnr: false,
            auto_calculate_ssim: false,
            auto_crop_black_borders: s.auto_crop_black_borders,
            ui_mode: s.ui_mode,
            video_recording_fps: s.video_recording_fps,
            show_workspace_tabs: s.show_workspace_tabs,
            rhi_backend: s.rhi_backend,
        }
    }
}

impl SettingsDialogData {
    pub fn from_json(s: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(s)
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("dialog data serialize")
    }

    pub fn to_json_pretty(&self) -> String {
        serde_json::to_string_pretty(self).expect("dialog data serialize")
    }

    /// Clamp numeric fields and coerce unknown enum-like strings to safe
    /// defaults. Returns the count of fields that were corrected — useful for
    /// debug logging and tests.
    pub fn normalize(&mut self) -> usize {
        let mut changes = 0;

        if self.max_name_length < limits::MIN_NAME_LENGTH {
            self.max_name_length = limits::MIN_NAME_LENGTH;
            changes += 1;
        } else if self.max_name_length > limits::MAX_NAME_LENGTH {
            self.max_name_length = limits::MAX_NAME_LENGTH;
            changes += 1;
        }

        if self.video_recording_fps < limits::MIN_VIDEO_FPS {
            self.video_recording_fps = limits::MIN_VIDEO_FPS;
            changes += 1;
        } else if self.video_recording_fps > limits::MAX_VIDEO_FPS {
            self.video_recording_fps = limits::MAX_VIDEO_FPS;
            changes += 1;
        }

        let resolution_allowed = DISPLAY_RESOLUTION_OPTIONS
            .iter()
            .any(|(_, v)| *v == self.resolution_limit);
        if !resolution_allowed {
            self.resolution_limit = limits::DEFAULT_DISPLAY_RESOLUTION_LIMIT;
            changes += 1;
        }

        for (field, fallback) in [
            (&mut self.magnifier_interpolation_method, "BILINEAR"),
            (&mut self.laser_interpolation_method, "BILINEAR"),
            (&mut self.zoom_interpolation_method, "BILINEAR"),
        ] {
            if !INTERPOLATION_METHODS.contains(&field.as_str()) {
                *field = fallback.into();
                changes += 1;
            }
        }

        if !matches!(self.ui_mode.as_str(), "beginner" | "advanced" | "expert") {
            self.ui_mode = "beginner".into();
            changes += 1;
        }

        if !matches!(
            self.ui_font_mode.as_str(),
            "builtin" | "system_default" | "system_custom"
        ) {
            self.ui_font_mode = "builtin".into();
            changes += 1;
        }

        if !matches!(self.theme.as_str(), "auto" | "light" | "dark") {
            self.theme = "auto".into();
            changes += 1;
        }

        changes
    }

    /// Convenience: clone the subset of `SettingsState` fields this view-model
    /// shadows. Used by the application service to detect whether a save is
    /// needed for any settings-state-backed field.
    pub fn apply_to_settings(&self, s: &mut SettingsState) {
        s.current_language = self.language.clone();
        s.theme = self.theme.clone();
        s.ui_font_mode = self.ui_font_mode.clone();
        s.ui_font_family = self.ui_font_family.clone();
        s.ui_mode = self.ui_mode.clone();
        s.debug_mode_enabled = self.debug_enabled;
        s.system_notifications_enabled = self.system_notifications_enabled;
        s.auto_crop_black_borders = self.auto_crop_black_borders;
        s.video_recording_fps = self.video_recording_fps;
        s.show_workspace_tabs = self.show_workspace_tabs;
        s.rhi_backend = self.rhi_backend.clone();
    }
}

/// One changed field, produced by [`diff`]. `value_json` is the *new*
/// value for the field, encoded as JSON so the C++ side can pass it to
/// QSettings (after type-erasing through Qt's QVariant) or to a Store
/// action without re-marshalling structs across the bridge.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FieldChange {
    pub field: String,
    pub value_json: String,
}

/// Compute the field-level diff between two view-models. Both inputs are
/// normalized first so cosmetic differences (e.g. unknown enum strings)
/// don't leak through as spurious changes.
pub fn diff(prev: &SettingsDialogData, next: &SettingsDialogData) -> Vec<FieldChange> {
    let mut prev_norm = prev.clone();
    let mut next_norm = next.clone();
    prev_norm.normalize();
    next_norm.normalize();

    let prev_v = serde_json::to_value(&prev_norm).expect("dialog data serialize");
    let next_v = serde_json::to_value(&next_norm).expect("dialog data serialize");
    let (Value::Object(prev_obj), Value::Object(next_obj)) = (prev_v, next_v) else {
        return Vec::new();
    };

    let mut out = Vec::new();
    for (key, next_val) in &next_obj {
        let prev_val = prev_obj.get(key);
        if Some(next_val) != prev_val {
            out.push(FieldChange {
                field: key.clone(),
                value_json: next_val.to_string(),
            });
        }
    }
    out.sort_by(|a, b| a.field.cmp(&b.field));
    out
}

/// JSON-encoded `Vec<FieldChange>`, convenient for the cxx surface.
pub fn diff_json(prev_json: &str, next_json: &str) -> Result<String, serde_json::Error> {
    let prev = SettingsDialogData::from_json(prev_json)?;
    let next = SettingsDialogData::from_json(next_json)?;
    let changes = diff(&prev, &next);
    Ok(serde_json::to_string(&changes).expect("changes serialize"))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::field_reassign_with_default)]

    use super::*;

    #[test]
    fn defaults_match_python_dataclass_subset() {
        let d = SettingsDialogData::default();
        assert_eq!(d.language, "en");
        assert_eq!(d.theme, "auto");
        assert_eq!(d.max_name_length, 50);
        assert_eq!(d.resolution_limit, 2160);
        assert_eq!(d.ui_mode, "beginner");
        assert_eq!(d.ui_font_mode, "builtin");
        assert_eq!(d.video_recording_fps, 60);
        assert_eq!(d.magnifier_interpolation_method, "BILINEAR");
        assert_eq!(d.rhi_backend, "default");
        assert!(!d.debug_enabled);
        assert!(d.system_notifications_enabled);
    }

    #[test]
    fn json_roundtrip_is_lossless() {
        let mut d = SettingsDialogData::default();
        d.theme = "dark".into();
        d.max_name_length = 99;
        d.ui_mode = "expert".into();
        d.auto_calculate_psnr = true;
        let j = d.to_json();
        let back = SettingsDialogData::from_json(&j).unwrap();
        assert_eq!(d, back);
    }

    #[test]
    fn empty_json_yields_defaults() {
        let d = SettingsDialogData::from_json("{}").unwrap();
        assert_eq!(d, SettingsDialogData::default());
    }

    #[test]
    fn normalize_clamps_max_name_length() {
        let mut d = SettingsDialogData::default();
        d.max_name_length = 5;
        assert_eq!(d.normalize(), 1);
        assert_eq!(d.max_name_length, limits::MIN_NAME_LENGTH);

        d.max_name_length = 500;
        assert_eq!(d.normalize(), 1);
        assert_eq!(d.max_name_length, limits::MAX_NAME_LENGTH);
    }

    #[test]
    fn normalize_clamps_video_fps() {
        let mut d = SettingsDialogData::default();
        d.video_recording_fps = 0;
        d.normalize();
        assert_eq!(d.video_recording_fps, limits::MIN_VIDEO_FPS);

        d.video_recording_fps = 9999;
        d.normalize();
        assert_eq!(d.video_recording_fps, limits::MAX_VIDEO_FPS);
    }

    #[test]
    fn normalize_rejects_unknown_resolution() {
        let mut d = SettingsDialogData::default();
        d.resolution_limit = 999;
        assert_eq!(d.normalize(), 1);
        assert_eq!(d.resolution_limit, 2160);
    }

    #[test]
    fn normalize_accepts_all_known_resolutions() {
        for (_, v) in DISPLAY_RESOLUTION_OPTIONS {
            let mut d = SettingsDialogData::default();
            d.resolution_limit = *v;
            assert_eq!(d.normalize(), 0, "resolution {v} should be accepted");
            assert_eq!(d.resolution_limit, *v);
        }
    }

    #[test]
    fn normalize_falls_back_on_unknown_interpolation() {
        let mut d = SettingsDialogData::default();
        d.magnifier_interpolation_method = "WAT".into();
        d.zoom_interpolation_method = "SINC".into();
        let changes = d.normalize();
        assert_eq!(changes, 2);
        assert_eq!(d.magnifier_interpolation_method, "BILINEAR");
        assert_eq!(d.zoom_interpolation_method, "BILINEAR");
    }

    #[test]
    fn normalize_falls_back_on_unknown_enum_strings() {
        let mut d = SettingsDialogData::default();
        d.ui_mode = "wizard".into();
        d.ui_font_mode = "fancy".into();
        d.theme = "neon".into();
        let changes = d.normalize();
        assert_eq!(changes, 3);
        assert_eq!(d.ui_mode, "beginner");
        assert_eq!(d.ui_font_mode, "builtin");
        assert_eq!(d.theme, "auto");
    }

    #[test]
    fn normalize_noop_on_default() {
        let mut d = SettingsDialogData::default();
        assert_eq!(d.normalize(), 0);
        assert_eq!(d, SettingsDialogData::default());
    }

    #[test]
    fn apply_to_settings_propagates_shadowed_fields() {
        let mut d = SettingsDialogData::default();
        d.theme = "dark".into();
        d.language = "ru".into();
        d.video_recording_fps = 30;
        d.show_workspace_tabs = true;
        d.rhi_backend = "vulkan".into();

        let mut s = SettingsState::default();
        d.apply_to_settings(&mut s);

        assert_eq!(s.theme, "dark");
        assert_eq!(s.current_language, "ru");
        assert_eq!(s.video_recording_fps, 30);
        assert!(s.show_workspace_tabs);
        assert_eq!(s.rhi_backend, "vulkan");
    }

    #[test]
    fn diff_empty_when_equal() {
        let d = SettingsDialogData::default();
        assert!(diff(&d, &d).is_empty());
    }

    #[test]
    fn diff_lists_changed_fields_only() {
        let prev = SettingsDialogData::default();
        let mut next = prev.clone();
        next.theme = "dark".into();
        next.video_recording_fps = 120;
        next.max_name_length = 99;

        let changes = diff(&prev, &next);
        let fields: Vec<&str> = changes.iter().map(|c| c.field.as_str()).collect();
        assert_eq!(
            fields,
            vec!["max_name_length", "theme", "video_recording_fps"]
        );
        let by_field = |name: &str| {
            changes
                .iter()
                .find(|c| c.field == name)
                .unwrap()
                .value_json
                .clone()
        };
        assert_eq!(by_field("theme"), "\"dark\"");
        assert_eq!(by_field("video_recording_fps"), "120");
        assert_eq!(by_field("max_name_length"), "99");
    }

    #[test]
    fn diff_normalizes_before_comparing() {
        // garbage enum value in prev should normalize to defaults; if next
        // already matches the normalized default, no change is reported.
        let mut prev = SettingsDialogData::default();
        prev.theme = "neon".into();
        let next = SettingsDialogData::default();
        let changes = diff(&prev, &next);
        // After normalize, prev.theme becomes "auto", same as next.
        assert!(changes.iter().all(|c| c.field != "theme"));
    }

    #[test]
    fn diff_json_roundtrip() {
        let prev = SettingsDialogData::default();
        let mut next = prev.clone();
        next.language = "ru".into();
        let raw = diff_json(&prev.to_json(), &next.to_json()).unwrap();
        let parsed: Vec<FieldChange> = serde_json::from_str(&raw).unwrap();
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].field, "language");
        assert_eq!(parsed[0].value_json, "\"ru\"");
    }

    #[test]
    fn interpolation_conflict_matches_python() {
        // optimization same speed as main -> conflict
        assert!(is_interpolation_conflict("BILINEAR", "BILINEAR"));
        // optimization slower than main -> conflict
        assert!(is_interpolation_conflict("BILINEAR", "LANCZOS"));
        // optimization strictly faster -> no conflict
        assert!(!is_interpolation_conflict("LANCZOS", "BILINEAR"));
        assert!(!is_interpolation_conflict("BICUBIC", "NEAREST"));
        // unknown methods -> 999 vs 999 -> conflict
        assert!(is_interpolation_conflict("???", "???"));
    }
}

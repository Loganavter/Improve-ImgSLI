//! Application settings state.
//!
//! Mirrors `src/core/store_settings.py::SettingsState`. JSON is the canonical
//! on-disk format. All fields default to the same values as the Python dataclass
//! so an empty `{}` round-trips into a usable state.

use serde::{Deserialize, Serialize};

use crate::domain::Color;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SettingsState {
    pub current_language: String,
    pub theme: String,
    pub ui_font_mode: String,
    pub ui_font_family: String,
    pub ui_mode: String,
    pub debug_mode_enabled: bool,
    pub system_notifications_enabled: bool,
    pub auto_crop_black_borders: bool,
    pub video_recording_fps: i32,
    pub video_editor_preview_render_scale: f32,
    pub show_workspace_tabs: bool,
    pub rhi_backend: String,

    pub export_use_default_dir: bool,
    pub export_default_dir: Option<String>,
    pub export_favorite_dir: Option<String>,
    pub export_video_favorite_dir: Option<String>,
    pub export_video_container: String,
    pub export_video_codec: String,
    pub export_video_quality_mode: String,
    pub export_video_crf: i32,
    pub export_video_bitrate: String,
    pub export_video_preset: String,
    pub export_video_pix_fmt: String,
    pub export_video_manual_args: String,
    pub export_last_format: String,
    pub export_quality: i32,
    pub export_fill_background: bool,
    pub export_background_color: Color,
    pub export_last_filename: String,
    pub export_png_compress_level: i32,
    pub export_comment_text: String,
    pub export_comment_keep_default: bool,
    pub export_resolution_scale: f32,

    pub window_width: i32,
    pub window_height: i32,
    pub window_x: i32,
    pub window_y: i32,
    pub window_was_maximized: bool,
}

impl Default for SettingsState {
    fn default() -> Self {
        Self {
            current_language: "en".into(),
            theme: "auto".into(),
            ui_font_mode: "builtin".into(),
            ui_font_family: String::new(),
            ui_mode: "beginner".into(),
            debug_mode_enabled: false,
            system_notifications_enabled: true,
            auto_crop_black_borders: true,
            video_recording_fps: 60,
            video_editor_preview_render_scale: 1.0,
            show_workspace_tabs: false,
            rhi_backend: "default".into(),

            export_use_default_dir: true,
            export_default_dir: None,
            export_favorite_dir: None,
            export_video_favorite_dir: None,
            export_video_container: "mp4".into(),
            export_video_codec: "h264 (AVC)".into(),
            export_video_quality_mode: "crf".into(),
            export_video_crf: 23,
            export_video_bitrate: "8000k".into(),
            export_video_preset: "medium".into(),
            export_video_pix_fmt: "yuv420p".into(),
            export_video_manual_args: "-c:v libx264 -crf 23 -pix_fmt yuv420p".into(),
            export_last_format: "PNG".into(),
            export_quality: 95,
            export_fill_background: false,
            export_background_color: Color::WHITE,
            export_last_filename: String::new(),
            export_png_compress_level: 9,
            export_comment_text: String::new(),
            export_comment_keep_default: false,
            export_resolution_scale: 1.0,

            window_width: 1024,
            window_height: 768,
            window_x: 100,
            window_y: 100,
            window_was_maximized: false,
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum SettingsError {
    #[error("settings JSON parse error: {0}")]
    Parse(#[from] serde_json::Error),
}

impl SettingsState {
    /// Load from JSON; tolerates missing fields by filling defaults.
    pub fn from_json(s: &str) -> Result<Self, SettingsError> {
        Ok(serde_json::from_str(s)?)
    }

    pub fn to_json_pretty(&self) -> String {
        // serde_json::to_string_pretty cannot fail for our types
        serde_json::to_string_pretty(self).expect("settings serialize")
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("settings serialize")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_match_python_dataclass() {
        let s = SettingsState::default();
        // spot-check the fields that are easy to typo
        assert_eq!(s.current_language, "en");
        assert_eq!(s.theme, "auto");
        assert_eq!(s.ui_mode, "beginner");
        assert_eq!(s.video_recording_fps, 60);
        assert_eq!(s.export_video_crf, 23);
        assert_eq!(
            s.export_video_manual_args,
            "-c:v libx264 -crf 23 -pix_fmt yuv420p"
        );
        assert_eq!(s.export_background_color, Color::WHITE);
        assert_eq!(s.window_width, 1024);
        assert_eq!(s.window_y, 100);
        assert!(s.system_notifications_enabled);
        assert!(s.auto_crop_black_borders);
        assert!(!s.show_workspace_tabs);
    }

    #[test]
    fn empty_json_yields_defaults() {
        let s = SettingsState::from_json("{}").unwrap();
        assert_eq!(s, SettingsState::default());
    }

    #[test]
    fn json_roundtrip_is_lossless() {
        let mut s = SettingsState::default();
        s.theme = "dark".into();
        s.window_was_maximized = true;
        s.export_background_color = Color::new(12, 34, 56, 78);
        s.export_default_dir = Some("/tmp/out".into());
        let j = s.to_json();
        let back = SettingsState::from_json(&j).unwrap();
        assert_eq!(s, back);
    }

    #[test]
    fn unknown_fields_are_rejected_or_ignored() {
        // serde default is to ignore unknown fields; we rely on that for
        // forward-compat (older imgsli loading newer files).
        let j = r#"{"theme": "dark", "future_field": 42}"#;
        let s = SettingsState::from_json(j).unwrap();
        assert_eq!(s.theme, "dark");
    }

    #[test]
    fn partial_json_uses_defaults_for_missing() {
        let j = r#"{"current_language": "ru", "window_width": 1600}"#;
        let s = SettingsState::from_json(j).unwrap();
        assert_eq!(s.current_language, "ru");
        assert_eq!(s.window_width, 1600);
        assert_eq!(s.window_height, 768); // default preserved
        assert_eq!(s.theme, "auto");
    }

    #[test]
    fn malformed_json_errors() {
        let r = SettingsState::from_json("{not json");
        assert!(r.is_err());
    }
}

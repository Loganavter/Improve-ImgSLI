//! Video editor pure-logic model.
//!
//! Ports `src/plugins/video_editor/model.py`:
//!
//! - `VideoTimelineState` / `VideoSelectionState` — frozen value objects
//!   for the timeline cursor and the selection range.
//! - `VideoProjectModel` — resolution / fps / codec settings with
//!   aspect-ratio adjustment math.
//!
//! Anything that touched the Python `Store` directly (session slot
//! readers, source/decoder attach) belongs in the C++ host because it
//! threads through Qt signals. Those wrappers live in
//! `cpp/app/plugin_video_editor.cpp`.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct TimelineState {
    pub position: i64,
}

impl Default for TimelineState {
    fn default() -> Self {
        Self { position: 0 }
    }
}

impl TimelineState {
    pub fn new(position: i64) -> Self {
        Self {
            position: position.max(0),
        }
    }

    pub fn advance(self, step: i64) -> Self {
        Self::new(self.position + step)
    }

    pub fn seek(self, position: i64) -> Self {
        Self::new(position)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct SelectionState {
    pub start: Option<i64>,
    pub end: Option<i64>,
}

impl SelectionState {
    pub fn is_empty(&self) -> bool {
        self.start.is_none() && self.end.is_none()
    }

    /// Normalize a (start, end) pair into a sorted selection. If both
    /// are `None` the selection is cleared; if only one is provided the
    /// other is filled with the same value, mirroring the Python
    /// `set_selection` semantics.
    pub fn set(start: Option<i64>, end: Option<i64>) -> Self {
        match (start, end) {
            (None, None) => Self::default(),
            (Some(s), Some(e)) => {
                let s = s.max(0);
                let e = e.max(0);
                Self {
                    start: Some(s.min(e)),
                    end: Some(s.max(e)),
                }
            }
            (Some(s), None) => {
                let s = s.max(0);
                Self {
                    start: Some(s),
                    end: Some(s),
                }
            }
            (None, Some(e)) => {
                let e = e.max(0);
                Self {
                    start: Some(e),
                    end: Some(e),
                }
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ProjectModel {
    pub width: i32,
    pub height: i32,
    pub fps: i32,
    pub preview_render_scale: f32,

    pub aspect_ratio_locked: bool,
    /// Cached ratio; recomputed on `set_resolution` when not locked.
    pub original_ratio: f32,

    pub container: String,
    pub codec: String,
    pub quality_mode: String,
    pub crf: i32,
    pub bitrate: String,
    pub preset: String,
    pub pix_fmt: String,

    pub manual_mode: bool,
    pub manual_args: String,
}

impl Default for ProjectModel {
    fn default() -> Self {
        Self {
            width: 1920,
            height: 1080,
            fps: 60,
            preview_render_scale: 1.0,
            aspect_ratio_locked: true,
            original_ratio: 16.0 / 9.0,
            container: "mp4".into(),
            codec: "h264".into(),
            quality_mode: "crf".into(),
            crf: 23,
            bitrate: "8000k".into(),
            preset: "medium".into(),
            pix_fmt: "yuv420p".into(),
            manual_mode: false,
            manual_args: "-c:v libx264 -crf 23 -pix_fmt yuv420p".into(),
        }
    }
}

impl ProjectModel {
    pub fn from_json(s: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(s)
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("video project serialize")
    }

    pub fn aspect_ratio(&self) -> f32 {
        if self.height > 0 {
            self.width as f32 / self.height as f32
        } else {
            16.0 / 9.0
        }
    }

    pub fn set_resolution(&mut self, width: i32, height: i32) {
        self.width = width;
        self.height = height;
        if !self.aspect_ratio_locked && height > 0 {
            self.original_ratio = width as f32 / height as f32;
        }
    }

    /// Returns the height that matches `width` under the locked aspect
    /// ratio; even-rounded so ffmpeg yuv420p is happy.
    pub fn adjust_height_to_aspect_ratio(&self, width: i32) -> i32 {
        if !self.aspect_ratio_locked || self.original_ratio <= 0.0 {
            return self.height;
        }
        let mut new_h = (width as f32 / self.original_ratio) as i32;
        if new_h % 2 != 0 {
            new_h += 1;
        }
        new_h
    }

    pub fn adjust_width_to_aspect_ratio(&self, height: i32) -> i32 {
        if !self.aspect_ratio_locked || self.original_ratio <= 0.0 {
            return self.width;
        }
        let mut new_w = (height as f32 * self.original_ratio) as i32;
        if new_w % 2 != 0 {
            new_w += 1;
        }
        new_w
    }

    /// Build ffmpeg arguments from the project settings. Mirrors
    /// `dialog_export.py::build_ffmpeg_args` semantics but lives here so
    /// both the C++ host and parallel-validation Python can reuse it.
    pub fn ffmpeg_args(&self) -> Vec<String> {
        if self.manual_mode {
            return self
                .manual_args
                .split_whitespace()
                .map(|s| s.to_string())
                .collect();
        }
        let mut out: Vec<String> = vec!["-c:v".into(), self.codec.clone()];
        match self.quality_mode.as_str() {
            "crf" => {
                out.push("-crf".into());
                out.push(self.crf.to_string());
            }
            "bitrate" => {
                out.push("-b:v".into());
                out.push(self.bitrate.clone());
            }
            _ => {
                out.push("-crf".into());
                out.push(self.crf.to_string());
            }
        }
        out.push("-preset".into());
        out.push(self.preset.clone());
        out.push("-pix_fmt".into());
        out.push(self.pix_fmt.clone());
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timeline_advance_clamps_to_zero() {
        let t = TimelineState::new(5);
        assert_eq!(t.advance(2).position, 7);
        assert_eq!(t.advance(-100).position, 0);
    }

    #[test]
    fn timeline_seek_clamps_negative() {
        assert_eq!(TimelineState::default().seek(-5).position, 0);
        assert_eq!(TimelineState::default().seek(42).position, 42);
    }

    #[test]
    fn selection_set_sorts_endpoints() {
        let s = SelectionState::set(Some(10), Some(3));
        assert_eq!(s.start, Some(3));
        assert_eq!(s.end, Some(10));
    }

    #[test]
    fn selection_set_clears_on_none() {
        let s = SelectionState::set(None, None);
        assert!(s.is_empty());
    }

    #[test]
    fn selection_set_mirrors_single_endpoint() {
        let s = SelectionState::set(Some(7), None);
        assert_eq!(s.start, Some(7));
        assert_eq!(s.end, Some(7));
        let s = SelectionState::set(None, Some(7));
        assert_eq!(s.start, Some(7));
        assert_eq!(s.end, Some(7));
    }

    #[test]
    fn project_default_matches_python() {
        let p = ProjectModel::default();
        assert_eq!((p.width, p.height), (1920, 1080));
        assert_eq!(p.fps, 60);
        assert_eq!(p.codec, "h264");
        assert_eq!(p.crf, 23);
        assert_eq!(p.pix_fmt, "yuv420p");
        assert!(p.aspect_ratio_locked);
    }

    #[test]
    fn project_aspect_ratio_adjusts_even() {
        let mut p = ProjectModel::default();
        p.original_ratio = 16.0 / 9.0;
        // 1281 / (16/9) = 720.5625 → 720 truncated, +1 to even = 720
        // (already even, no bump)
        let h = p.adjust_height_to_aspect_ratio(1281);
        assert_eq!(h % 2, 0);
        // 1280 -> 720 exactly, even.
        assert_eq!(p.adjust_height_to_aspect_ratio(1280), 720);
        // 1000 -> 562.5 truncated = 562, even
        assert_eq!(p.adjust_height_to_aspect_ratio(1000), 562);
    }

    #[test]
    fn project_aspect_ratio_unlocked_keeps_height() {
        let mut p = ProjectModel::default();
        p.aspect_ratio_locked = false;
        assert_eq!(p.adjust_height_to_aspect_ratio(9999), p.height);
    }

    #[test]
    fn project_set_resolution_updates_ratio_when_unlocked() {
        let mut p = ProjectModel::default();
        p.aspect_ratio_locked = false;
        p.set_resolution(2000, 1000);
        assert!((p.original_ratio - 2.0).abs() < 1e-5);
        // locked: ratio frozen at 16/9
        p.aspect_ratio_locked = true;
        p.set_resolution(800, 800);
        assert!((p.original_ratio - 2.0).abs() < 1e-5);
    }

    #[test]
    fn project_ffmpeg_args_crf_default() {
        let p = ProjectModel::default();
        let args = p.ffmpeg_args();
        assert_eq!(
            args,
            vec!["-c:v", "h264", "-crf", "23", "-preset", "medium",
                 "-pix_fmt", "yuv420p"]
        );
    }

    #[test]
    fn project_ffmpeg_args_bitrate_mode() {
        let mut p = ProjectModel::default();
        p.quality_mode = "bitrate".into();
        p.bitrate = "5000k".into();
        let args = p.ffmpeg_args();
        assert!(args.contains(&"-b:v".to_string()));
        assert!(args.contains(&"5000k".to_string()));
        assert!(!args.contains(&"-crf".to_string()));
    }

    #[test]
    fn project_ffmpeg_args_manual_mode() {
        let mut p = ProjectModel::default();
        p.manual_mode = true;
        p.manual_args = "-c:v libx265 -crf 18 -pix_fmt yuv420p10le".into();
        assert_eq!(
            p.ffmpeg_args(),
            vec!["-c:v", "libx265", "-crf", "18",
                 "-pix_fmt", "yuv420p10le"]
        );
    }

    #[test]
    fn project_json_roundtrip() {
        let mut p = ProjectModel::default();
        p.codec = "h265".into();
        p.crf = 18;
        let json = p.to_json();
        let back = ProjectModel::from_json(&json).unwrap();
        assert_eq!(p, back);
    }
}

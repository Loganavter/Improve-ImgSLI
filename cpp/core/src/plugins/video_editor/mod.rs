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

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct TimelineState {
    pub position: i64,
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

    /// Feature groups allowed to change across recorded keyframes.
    /// Disabled groups retain their first-snapshot values for the complete
    /// preview/export sequence.
    pub keyframe_features: KeyframeFeaturePolicy,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct KeyframeFeaturePolicy {
    pub split: bool,
    pub divider: bool,
    pub magnifier: bool,
    pub capture: bool,
    pub guides: bool,
    pub filename_overlay: bool,
    pub paste_overlay: bool,
}

impl Default for KeyframeFeaturePolicy {
    fn default() -> Self {
        Self {
            split: true,
            divider: true,
            magnifier: true,
            capture: true,
            guides: true,
            filename_overlay: true,
            paste_overlay: true,
        }
    }
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
            keyframe_features: KeyframeFeaturePolicy::default(),
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

/// One captured frame in a recording. Mirrors
/// `src/plugins/video_editor/services/keyframing/types.py::FrameSnapshot`
/// in spirit: the visual state needed to recompose this frame later for
/// preview or export.
///
/// Heavy state (full `CanvasRenderPlan`) lives in C++ and is stored
/// alongside the timestamp on the Qt side; here we keep only the metadata
/// that needs to round-trip through serialization (paths and labels) plus
/// the timestamp. C++ can always produce the JSON form by emitting its
/// own payload — this struct documents the contract.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct FrameSnapshot {
    /// Capture time in milliseconds from recording start.
    pub timestamp_ms: i64,
    pub left_path: String,
    pub right_path: String,
    pub left_label: String,
    pub right_label: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Recording {
    pub fps: i32,
    pub snapshots: Vec<FrameSnapshot>,
}

impl Default for Recording {
    fn default() -> Self {
        Self {
            fps: 60,
            snapshots: Vec::new(),
        }
    }
}

impl Recording {
    pub fn new(fps: i32) -> Self {
        Self {
            fps: fps.clamp(1, 144),
            snapshots: Vec::new(),
        }
    }

    pub fn append(&mut self, snapshot: FrameSnapshot) {
        self.snapshots.push(snapshot);
    }

    pub fn clear_snapshots(&mut self) {
        self.snapshots.clear();
    }

    pub fn snapshot_count(&self) -> usize {
        self.snapshots.len()
    }

    /// Duration covered by the recording, in milliseconds. Defined as the
    /// timestamp of the last sample plus one frame duration at `fps`,
    /// matching the Python `KeyframedRecording.duration` property.
    pub fn duration_ms(&self) -> i64 {
        if self.snapshots.is_empty() {
            return 0;
        }
        let last = self.snapshots.last().expect("non-empty").timestamp_ms;
        let frame_ms = (1000 / self.fps.max(1)) as i64;
        last + frame_ms
    }

    /// Index of the sample whose timestamp is the greatest one ≤ `time_ms`.
    /// Returns `None` when the recording is empty or `time_ms` is before
    /// the first sample.
    pub fn frame_index_at_time_ms(&self, time_ms: i64) -> Option<usize> {
        if self.snapshots.is_empty() {
            return None;
        }
        let mut found: Option<usize> = None;
        for (idx, s) in self.snapshots.iter().enumerate() {
            if s.timestamp_ms <= time_ms {
                found = Some(idx);
            } else {
                break;
            }
        }
        found
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("recording serialize")
    }

    pub fn from_json(s: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(s)
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::field_reassign_with_default)]

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
        assert!(p.keyframe_features.magnifier);
        assert!(p.keyframe_features.guides);
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
            vec!["-c:v", "h264", "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p"]
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
            vec!["-c:v", "libx265", "-crf", "18", "-pix_fmt", "yuv420p10le"]
        );
    }

    #[test]
    fn recording_default_fps_60_no_snapshots() {
        let r = Recording::default();
        assert_eq!(r.fps, 60);
        assert_eq!(r.snapshot_count(), 0);
        assert_eq!(r.duration_ms(), 0);
        assert_eq!(r.frame_index_at_time_ms(0), None);
    }

    #[test]
    fn recording_new_clamps_fps() {
        assert_eq!(Recording::new(0).fps, 1);
        assert_eq!(Recording::new(500).fps, 144);
        assert_eq!(Recording::new(30).fps, 30);
    }

    #[test]
    fn recording_append_increments_count_and_duration() {
        let mut r = Recording::new(60);
        for ts in [0_i64, 16, 33, 50] {
            r.append(FrameSnapshot {
                timestamp_ms: ts,
                ..FrameSnapshot::default()
            });
        }
        assert_eq!(r.snapshot_count(), 4);
        // last=50, frame=1000/60=16ms (int division)
        assert_eq!(r.duration_ms(), 50 + 16);
    }

    #[test]
    fn recording_frame_index_at_time_ms() {
        let mut r = Recording::new(60);
        for ts in [0_i64, 100, 200, 300] {
            r.append(FrameSnapshot {
                timestamp_ms: ts,
                ..FrameSnapshot::default()
            });
        }
        assert_eq!(r.frame_index_at_time_ms(-1), None);
        assert_eq!(r.frame_index_at_time_ms(0), Some(0));
        assert_eq!(r.frame_index_at_time_ms(150), Some(1));
        assert_eq!(r.frame_index_at_time_ms(300), Some(3));
        assert_eq!(r.frame_index_at_time_ms(99_999), Some(3));
    }

    #[test]
    fn recording_clear_keeps_fps() {
        let mut r = Recording::new(30);
        r.append(FrameSnapshot::default());
        r.clear_snapshots();
        assert_eq!(r.snapshot_count(), 0);
        assert_eq!(r.fps, 30);
    }

    #[test]
    fn recording_json_roundtrip() {
        let mut r = Recording::new(48);
        r.append(FrameSnapshot {
            timestamp_ms: 42,
            left_path: "/a.png".into(),
            right_path: "/b.png".into(),
            left_label: "A".into(),
            right_label: "B".into(),
        });
        let s = r.to_json();
        let back = Recording::from_json(&s).unwrap();
        assert_eq!(r, back);
    }

    #[test]
    fn project_json_roundtrip() {
        let mut p = ProjectModel::default();
        p.codec = "h265".into();
        p.crf = 18;
        p.keyframe_features.magnifier = false;
        let json = p.to_json();
        let back = ProjectModel::from_json(&json).unwrap();
        assert_eq!(p, back);
    }

    #[test]
    fn project_partial_json_defaults_keyframe_policy_to_enabled() {
        let p = ProjectModel::from_json(r#"{"width":1280}"#).unwrap();
        assert!(p.keyframe_features.split);
        assert!(p.keyframe_features.divider);
        assert!(p.keyframe_features.magnifier);
        assert!(p.keyframe_features.capture);
        assert!(p.keyframe_features.guides);
        assert!(p.keyframe_features.filename_overlay);
        assert!(p.keyframe_features.paste_overlay);
    }
}

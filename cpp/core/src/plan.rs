//! Canvas render plan — plain data describing one frame.
//!
//! Mirrors `src/ui/canvas_presentation/plan.py`. The Python version uses
//! `object` for image handles because Qt types vary. In Rust we keep the
//! handle abstract: an opaque `TextureId` that the C++ PlanApplicator
//! resolves to a real `QRhiTexture*` (or analogous GL handle).
//!
//! Phase 1 deliverable: types only. PlanBuilder logic ports later — first
//! the simplest subset (legacy two-image path), then composition trees.

use serde::{Deserialize, Serialize};

use crate::domain::{Color, Point, Rect};

/// Opaque handle to a GPU texture owned by the C++ side.
///
/// `0` is "no texture". The applicator uses this to look up a `QRhiTexture*`
/// (or GL name) from its resource registry. Rust never dereferences it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(transparent)]
pub struct TextureId(pub u64);

impl TextureId {
    pub const NONE: Self = Self(0);
    pub fn is_some(self) -> bool {
        self.0 != 0
    }
}

/// Magnifier capture circle. Mirrors `plan.CaptureCircle`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CaptureCircle {
    pub center: Point,
    pub radius: f32,
    pub color: Color,
}

/// Guide ring set drawn around the magnifier circle. Mirrors `plan.GuideSet`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GuideSet {
    pub capture_center: Point,
    pub capture_radius: f32,
    pub target_centers: Vec<Point>,
    pub target_radii: Vec<f32>,
    pub color: Color,
}

/// One overlay slot — the magnifier's split or single-source view.
/// Mirrors `plan.OverlaySlot`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct OverlaySlot {
    pub center: Point,
    pub radius: f32,
    /// `(x, y, w, h)` in normalized UV.
    pub uv_rect: [f32; 4],
    pub uv_rect2: [f32; 4],
    pub source: i32,
    pub is_combined: bool,
    pub internal_split: f32,
    pub horizontal: bool,
    pub divider_visible: bool,
    pub divider_color: [f32; 4],
    pub divider_thickness_uv: f32,
    pub border_color: Color,
    pub border_width: f32,
}

/// Aggregated overlay layout for one frame. Mirrors `plan.OverlayLayout`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OverlayLayout {
    #[serde(default)]
    pub slots: Vec<OverlaySlot>,
    #[serde(default)]
    pub capture_circles: Vec<CaptureCircle>,
    #[serde(default)]
    pub guide_sets: Vec<GuideSet>,
    #[serde(default)]
    pub capture_center: Option<Point>,
    #[serde(default)]
    pub capture_radius: f32,
    #[serde(default)]
    pub overlay_centers: Vec<(f32, f32)>,
    #[serde(default)]
    pub overlay_radius: f32,
    #[serde(default)]
    pub border_color: Option<Color>,
    #[serde(default = "default_border_width")]
    pub border_width: f32,
    #[serde(default)]
    pub channel_mode: i32,
    #[serde(default)]
    pub diff_mode: i32,
    #[serde(default = "default_interp_mode")]
    pub interp_mode: i32,
}

const fn default_border_width() -> f32 {
    2.0
}
const fn default_interp_mode() -> i32 {
    1
}

impl Default for OverlayLayout {
    fn default() -> Self {
        Self {
            slots: Vec::new(),
            capture_circles: Vec::new(),
            guide_sets: Vec::new(),
            capture_center: None,
            capture_radius: 0.0,
            overlay_centers: Vec::new(),
            overlay_radius: 0.0,
            border_color: None,
            border_width: default_border_width(),
            channel_mode: 0,
            diff_mode: 0,
            interp_mode: default_interp_mode(),
        }
    }
}

/// One frame's render plan. Mirrors `plan.CanvasRenderPlan`.
///
/// Image fields use [`TextureId`] instead of opaque Python objects; the
/// C++ applicator resolves them. `gl_scene` and `composition_root` from
/// the Python version aren't ported yet — they belong to later Phase 1
/// work (scene graph) and Phase 3 (multi-compare composition).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CanvasRenderPlan {
    pub image1: TextureId,
    pub image2: TextureId,
    pub source_image1: TextureId,
    pub source_image2: TextureId,
    /// Cache key for image-pair identity. Matches the Python tuple shape
    /// loosely — we keep it as a string for the FFI surface.
    #[serde(default)]
    pub source_key: String,
    pub canvas_w: i32,
    pub canvas_h: i32,
    #[serde(default)]
    pub overlay_layout: Option<OverlayLayout>,
    #[serde(default)]
    pub capture_visible: bool,
    #[serde(default)]
    pub capture_color: Color,
    #[serde(default)]
    pub guides_enabled: bool,
    #[serde(default)]
    pub guides_color: Color,
    #[serde(default)]
    pub guides_thickness: i32,
    #[serde(default)]
    pub fill_rgba: Option<Color>,
    #[serde(default)]
    pub display_cache_key: Option<String>,
    #[serde(default = "default_output_scale")]
    pub output_scale: f32,
    #[serde(default)]
    pub preserve_zoom: bool,
    /// Clip rect from the scene graph; falls back to the whole canvas.
    #[serde(default)]
    pub overlay_clip_rect: Option<Rect>,
}

const fn default_output_scale() -> f32 {
    1.0
}

impl CanvasRenderPlan {
    /// Port of `plan.resolve_plan_logical_image_rect`.
    ///
    /// Returns the in-canvas rect overlays should clip against.
    pub fn logical_image_rect(&self) -> Rect {
        if let Some(clip) = self.overlay_clip_rect {
            return Rect::new(clip.x, clip.y, clip.w.max(1), clip.h.max(1));
        }
        Rect::new(0, 0, self.canvas_w.max(1), self.canvas_h.max(1))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn texture_id_default_is_none_sentinel() {
        assert_eq!(TextureId::default(), TextureId::NONE);
        assert!(!TextureId::NONE.is_some());
        assert!(TextureId(1).is_some());
    }

    #[test]
    fn logical_rect_falls_back_to_canvas_when_no_clip() {
        let p = CanvasRenderPlan {
            image1: TextureId(1),
            image2: TextureId(2),
            source_image1: TextureId::NONE,
            source_image2: TextureId::NONE,
            source_key: "k".into(),
            canvas_w: 800,
            canvas_h: 600,
            overlay_layout: None,
            capture_visible: false,
            capture_color: Color::WHITE,
            guides_enabled: false,
            guides_color: Color::WHITE,
            guides_thickness: 1,
            fill_rgba: None,
            display_cache_key: None,
            output_scale: 1.0,
            preserve_zoom: false,
            overlay_clip_rect: None,
        };
        assert_eq!(p.logical_image_rect(), Rect::new(0, 0, 800, 600));
    }

    #[test]
    fn logical_rect_uses_clip_when_present_and_clamps_min_one() {
        let mut p = CanvasRenderPlan {
            image1: TextureId(1),
            image2: TextureId(2),
            source_image1: TextureId::NONE,
            source_image2: TextureId::NONE,
            source_key: String::new(),
            canvas_w: 800,
            canvas_h: 600,
            overlay_layout: None,
            capture_visible: false,
            capture_color: Color::WHITE,
            guides_enabled: false,
            guides_color: Color::WHITE,
            guides_thickness: 1,
            fill_rgba: None,
            display_cache_key: None,
            output_scale: 1.0,
            preserve_zoom: false,
            overlay_clip_rect: Some(Rect::new(10, 20, 0, 0)),
        };
        assert_eq!(p.logical_image_rect(), Rect::new(10, 20, 1, 1));
        p.overlay_clip_rect = Some(Rect::new(5, 6, 100, 50));
        assert_eq!(p.logical_image_rect(), Rect::new(5, 6, 100, 50));
    }

    #[test]
    fn overlay_layout_defaults_match_python() {
        let l = OverlayLayout::default();
        // From plan.py: border_width=2.0, interp_mode=1
        assert_eq!(l.border_width, 2.0);
        assert_eq!(l.interp_mode, 1);
        assert_eq!(l.channel_mode, 0);
        assert_eq!(l.diff_mode, 0);
        assert!(l.slots.is_empty());
    }

    #[test]
    fn overlay_layout_empty_json_roundtrip() {
        let l: OverlayLayout = serde_json::from_str("{}").unwrap();
        assert_eq!(l, OverlayLayout::default());
    }
}

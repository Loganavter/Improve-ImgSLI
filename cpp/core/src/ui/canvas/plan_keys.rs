//! Pure helpers used by the plan-building pipeline.
//!
//! Mirrors three behaviours from `src/ui/canvas_presentation/plan_builder.py`:
//!
//! 1. `source_key` / `display_cache_key` — the cache discriminators the live
//!    and snapshot pipelines use to decide whether the cached plan is still
//!    valid.
//! 2. `compute_letterbox_scale` — the canvas-px ↔ widget-px ratio
//!    (`sr = min(dw/canvas_w, dh/canvas_h)`) that backs the "single scale
//!    factor" invariant called out in `docs/dev/ARCHITECTURE.md`.
//! 3. `letterbox_rect` — the centered rect after scaling, used as overlay
//!    clip.
//!
//! Feature-coupled plan building and snapshot store construction stay outside
//! this module. Normalized virtual-canvas bounds and content placement now
//! live in `virtual_layout`; the remaining shared PlanBuilder work is tracked
//! in `docs/dev/CPP_PORT_HARDENING.md`.

use serde::{Deserialize, Serialize};

use crate::domain::{Color, Rect};

/// Source-key inputs. We pre-hash inside [`SourceKey::compute`] so callers
/// can pass a single `u64` across the FFI boundary instead of a tuple.
///
/// Mirrors `_build_snapshot_store`'s `source_key` tuple:
/// `(image1_path, image2_path, source_img1.size, source_img2.size,
///   fit_content, fill_color)`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SourceKeyInputs {
    pub image1_path: Option<String>,
    pub image2_path: Option<String>,
    pub image1_size: Option<(u32, u32)>,
    pub image2_size: Option<(u32, u32)>,
    pub fit_content: bool,
    pub fill_color: Color,
}

/// Discriminator for the display-cache pipeline. Mirrors `display_cache_key`
/// in `_build_snapshot_store`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DisplayCacheKeyInputs {
    pub source: SourceKeyInputs,
    pub display1_size: Option<(u32, u32)>,
    pub display2_size: Option<(u32, u32)>,
    pub global_bounds: Option<GlobalBoundsKey>,
}

/// The subset of `global_bounds` that participates in cache identity.
/// Mirrors `global_bounds_key` in `_build_snapshot_store`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GlobalBoundsKey {
    pub pad_left: i32,
    pub pad_right: i32,
    pub pad_top: i32,
    pub pad_bottom: i32,
    pub base_width: i32,
    pub base_height: i32,
    pub canvas_x_min: f64,
    pub canvas_x_max: f64,
    pub canvas_y_min: f64,
    pub canvas_y_max: f64,
}

/// Stable 64-bit fingerprint of a key. Two equal inputs hash to equal `u64`s
/// (this is what the Python tuple-as-dict-key ultimately relied on, modulo
/// dict implementation details).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct CacheKey(pub u64);

impl SourceKeyInputs {
    pub fn fingerprint(&self) -> CacheKey {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};
        let mut h = DefaultHasher::new();
        self.image1_path.hash(&mut h);
        self.image2_path.hash(&mut h);
        self.image1_size.hash(&mut h);
        self.image2_size.hash(&mut h);
        self.fit_content.hash(&mut h);
        // Color components hash directly.
        (
            self.fill_color.r,
            self.fill_color.g,
            self.fill_color.b,
            self.fill_color.a,
        )
            .hash(&mut h);
        CacheKey(h.finish())
    }
}

impl DisplayCacheKeyInputs {
    pub fn fingerprint(&self) -> CacheKey {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};
        let mut h = DefaultHasher::new();
        h.write_u64(self.source.fingerprint().0);
        self.display1_size.hash(&mut h);
        self.display2_size.hash(&mut h);
        if let Some(g) = &self.global_bounds {
            g.pad_left.hash(&mut h);
            g.pad_right.hash(&mut h);
            g.pad_top.hash(&mut h);
            g.pad_bottom.hash(&mut h);
            g.base_width.hash(&mut h);
            g.base_height.hash(&mut h);
            // Bit-cast floats so we get NaN-stable hashing.
            h.write_u64(g.canvas_x_min.to_bits());
            h.write_u64(g.canvas_x_max.to_bits());
            h.write_u64(g.canvas_y_min.to_bits());
            h.write_u64(g.canvas_y_max.to_bits());
        } else {
            h.write_u8(0);
        }
        CacheKey(h.finish())
    }
}

/// The letterbox scale factor (`sr` in `ARCHITECTURE.md`):
///
/// ```text
/// sr = min(widget_w / canvas_w, widget_h / canvas_h)
/// ```
///
/// Returns `0.0` if any dimension is non-positive — the only sane fallback
/// when the widget hasn't been sized yet.
pub fn compute_letterbox_scale(widget_w: f64, widget_h: f64, canvas_w: f64, canvas_h: f64) -> f64 {
    if widget_w <= 0.0 || widget_h <= 0.0 || canvas_w <= 0.0 || canvas_h <= 0.0 {
        return 0.0;
    }
    (widget_w / canvas_w).min(widget_h / canvas_h)
}

/// Centered letterboxed rect of the canvas inside the widget.
pub fn letterbox_rect(widget_w: i32, widget_h: i32, canvas_w: i32, canvas_h: i32) -> Rect {
    let sr = compute_letterbox_scale(
        widget_w as f64,
        widget_h as f64,
        canvas_w as f64,
        canvas_h as f64,
    );
    if sr <= 0.0 {
        return Rect::new(0, 0, widget_w.max(0), widget_h.max(0));
    }
    let scaled_w = (canvas_w as f64 * sr).round() as i32;
    let scaled_h = (canvas_h as f64 * sr).round() as i32;
    let x = (widget_w - scaled_w) / 2;
    let y = (widget_h - scaled_h) / 2;
    Rect::new(x, y, scaled_w.max(1), scaled_h.max(1))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> SourceKeyInputs {
        SourceKeyInputs {
            image1_path: Some("a.png".into()),
            image2_path: Some("b.png".into()),
            image1_size: Some((100, 50)),
            image2_size: Some((100, 50)),
            fit_content: false,
            fill_color: Color::TRANSPARENT,
        }
    }

    #[test]
    fn source_key_is_stable_and_distinguishes_inputs() {
        let a = base();
        let b = base();
        assert_eq!(a.fingerprint(), b.fingerprint());

        let mut c = base();
        c.fit_content = true;
        assert_ne!(a.fingerprint(), c.fingerprint());

        let mut d = base();
        d.image2_size = Some((200, 50));
        assert_ne!(a.fingerprint(), d.fingerprint());

        let mut e = base();
        e.fill_color = Color::WHITE;
        assert_ne!(a.fingerprint(), e.fingerprint());
    }

    #[test]
    fn display_cache_key_includes_global_bounds() {
        let s = base();
        let k1 = DisplayCacheKeyInputs {
            source: s.clone(),
            display1_size: Some((800, 400)),
            display2_size: Some((800, 400)),
            global_bounds: None,
        };
        let k2 = DisplayCacheKeyInputs {
            global_bounds: Some(GlobalBoundsKey {
                pad_left: 10,
                pad_right: 10,
                pad_top: 0,
                pad_bottom: 0,
                base_width: 800,
                base_height: 400,
                canvas_x_min: 0.0,
                canvas_x_max: 800.0,
                canvas_y_min: 0.0,
                canvas_y_max: 400.0,
            }),
            ..k1.clone()
        };
        assert_ne!(k1.fingerprint(), k2.fingerprint());
    }

    #[test]
    fn letterbox_scale_picks_min_axis() {
        // Widget wider than canvas → vertical axis limits.
        assert!((compute_letterbox_scale(800.0, 400.0, 100.0, 100.0) - 4.0).abs() < 1e-9);
        // Widget taller than canvas → horizontal axis limits.
        assert!((compute_letterbox_scale(400.0, 800.0, 100.0, 100.0) - 4.0).abs() < 1e-9);
        // Anisotropic.
        let sr = compute_letterbox_scale(400.0, 800.0, 100.0, 50.0);
        assert!((sr - 4.0).abs() < 1e-9);
    }

    #[test]
    fn letterbox_scale_zero_on_invalid() {
        assert_eq!(compute_letterbox_scale(0.0, 100.0, 1.0, 1.0), 0.0);
        assert_eq!(compute_letterbox_scale(100.0, 100.0, 0.0, 1.0), 0.0);
    }

    #[test]
    fn letterbox_rect_centers_canvas() {
        // Canvas 100x100 inside widget 800x400 → scale 4, scaled 400x400,
        // centered at x=(800-400)/2=200, y=0.
        let r = letterbox_rect(800, 400, 100, 100);
        assert_eq!(r, Rect::new(200, 0, 400, 400));
    }

    #[test]
    fn letterbox_rect_handles_unsized_widget() {
        // Widget not yet sized; we still produce a valid (empty-ish) rect.
        let r = letterbox_rect(0, 0, 100, 100);
        assert_eq!(r, Rect::new(0, 0, 0, 0));
    }
}

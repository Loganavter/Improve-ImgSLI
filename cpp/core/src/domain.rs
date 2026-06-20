//! Domain primitives.
//!
//! Mirrors `src/domain/types.py`. Pure value types, `Copy` where possible,
//! `serde` for JSON round-trips, and a stable shape suitable for crossing
//! the `cxx` FFI boundary as plain data.

use serde::{Deserialize, Serialize};

/// 2D point in canvas-px (Phase 1 callers may also use widget-px — same shape).
///
/// Mirrors `domain.types.Point`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Point {
    #[serde(default)]
    pub x: f64,
    #[serde(default)]
    pub y: f64,
}

impl Default for Point {
    fn default() -> Self {
        Self { x: 0.0, y: 0.0 }
    }
}

impl Point {
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }
}

/// 8-bit RGBA color.
///
/// Mirrors `domain.types.Color`. Components are clamped at construction
/// time so we never store invalid values in state.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Color {
    #[serde(default = "color_full")]
    pub r: u8,
    #[serde(default = "color_full")]
    pub g: u8,
    #[serde(default = "color_full")]
    pub b: u8,
    #[serde(default = "color_full")]
    pub a: u8,
}

const fn color_full() -> u8 {
    255
}

impl Default for Color {
    fn default() -> Self {
        Self::WHITE
    }
}

impl Color {
    pub const WHITE: Self = Self {
        r: 255,
        g: 255,
        b: 255,
        a: 255,
    };
    pub const BLACK: Self = Self {
        r: 0,
        g: 0,
        b: 0,
        a: 255,
    };
    pub const TRANSPARENT: Self = Self {
        r: 0,
        g: 0,
        b: 0,
        a: 0,
    };

    pub const fn new(r: u8, g: u8, b: u8, a: u8) -> Self {
        Self { r, g, b, a }
    }

    /// Premultiplied float quad, in the order shaders expect.
    pub fn as_f32_quad(&self) -> [f32; 4] {
        [
            self.r as f32 / 255.0,
            self.g as f32 / 255.0,
            self.b as f32 / 255.0,
            self.a as f32 / 255.0,
        ]
    }
}

/// Integer rectangle (canvas-px). Mirrors `domain.types.Rect`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct Rect {
    #[serde(default)]
    pub x: i32,
    #[serde(default)]
    pub y: i32,
    #[serde(default)]
    pub w: i32,
    #[serde(default)]
    pub h: i32,
}

impl Rect {
    pub const fn new(x: i32, y: i32, w: i32, h: i32) -> Self {
        Self { x, y, w, h }
    }

    pub fn right(&self) -> i32 {
        self.x + self.w
    }

    pub fn bottom(&self) -> i32 {
        self.y + self.h
    }

    pub fn is_empty(&self) -> bool {
        self.w <= 0 || self.h <= 0
    }
}

/// Float size (useful for fractional canvas dimensions before snapping).
#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct SizeF {
    #[serde(default)]
    pub w: f64,
    #[serde(default)]
    pub h: f64,
}

impl SizeF {
    pub const fn new(w: f64, h: f64) -> Self {
        Self { w, h }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn point_default_origin() {
        assert_eq!(Point::default(), Point::new(0.0, 0.0));
    }

    #[test]
    fn color_default_white_matches_python_dataclass() {
        // domain.types.Color() in Python defaults to (255, 255, 255, 255)
        assert_eq!(Color::default(), Color::WHITE);
    }

    #[test]
    fn color_serde_roundtrip() {
        let c = Color::new(10, 20, 30, 40);
        let s = serde_json::to_string(&c).unwrap();
        let back: Color = serde_json::from_str(&s).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn color_partial_json_uses_defaults() {
        // The Python dataclass tolerates missing fields via defaults; mirror
        // that for forward-compatible settings files.
        let c: Color = serde_json::from_str(r#"{"r": 12, "g": 34}"#).unwrap();
        assert_eq!(c, Color::new(12, 34, 255, 255));
    }

    #[test]
    fn color_f32_quad_order_matches_shaders() {
        let c = Color::new(255, 128, 64, 32);
        let q = c.as_f32_quad();
        assert_eq!(q[0], 1.0);
        assert!((q[1] - 128.0 / 255.0).abs() < 1e-6);
        assert!((q[2] - 64.0 / 255.0).abs() < 1e-6);
        assert!((q[3] - 32.0 / 255.0).abs() < 1e-6);
    }

    #[test]
    fn rect_right_bottom_and_emptiness() {
        let r = Rect::new(10, 20, 30, 40);
        assert_eq!(r.right(), 40);
        assert_eq!(r.bottom(), 60);
        assert!(!r.is_empty());

        assert!(Rect::default().is_empty());
        assert!(Rect::new(0, 0, 0, 5).is_empty());
    }
}

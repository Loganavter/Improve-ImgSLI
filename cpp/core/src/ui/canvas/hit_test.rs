//! Pure-geometry hit testing.
//!
//! The Python side iterates a `SCENE_HIT_TESTERS` registry (see
//! `src/ui/canvas_infra/scene/pipeline.py`). The registry itself is a
//! UI-feature concern that ports to C++. The geometric primitives the
//! testers call into — point-in-rect, point-in-circle — live here.
//!
//! Convention (matches the Python implementation): the right and bottom
//! edges of a rect are *exclusive*, circle radius is *inclusive*. This is
//! what the existing magnifier and divider hit-testers assume.

use crate::domain::{Point, Rect};

/// Inclusive on left/top, exclusive on right/bottom — matches Qt's
/// `QRect::contains` integer semantics.
pub fn point_in_rect(p: Point, r: Rect) -> bool {
    if r.is_empty() {
        return false;
    }
    let px = p.x;
    let py = p.y;
    px >= r.x as f64 && px < r.right() as f64 && py >= r.y as f64 && py < r.bottom() as f64
}

/// Inclusive on the boundary — a click exactly on the radius hits.
pub fn point_in_circle(p: Point, center: Point, radius: f64) -> bool {
    if radius <= 0.0 {
        return false;
    }
    let dx = p.x - center.x;
    let dy = p.y - center.y;
    dx * dx + dy * dy <= radius * radius
}

/// Distance from a point to a horizontal or vertical line segment defined by
/// the divider position. Used by the divider hit-tester to decide whether the
/// user grabbed the divider handle.
///
/// `axis = Axis::Vertical` means the divider is a vertical line at `x = pos`
/// across the rect; horizontal is `y = pos`.
pub fn distance_to_divider(p: Point, rect: Rect, axis: Axis, pos: f64) -> f64 {
    match axis {
        Axis::Vertical => {
            let in_band = p.y >= rect.y as f64 && p.y <= rect.bottom() as f64;
            if !in_band {
                return f64::INFINITY;
            }
            (p.x - pos).abs()
        }
        Axis::Horizontal => {
            let in_band = p.x >= rect.x as f64 && p.x <= rect.right() as f64;
            if !in_band {
                return f64::INFINITY;
            }
            (p.y - pos).abs()
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Axis {
    Vertical,
    Horizontal,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pt(x: f64, y: f64) -> Point {
        Point::new(x, y)
    }

    #[test]
    fn point_in_rect_basic() {
        let r = Rect::new(10, 20, 30, 40);
        assert!(point_in_rect(pt(10.0, 20.0), r));
        assert!(point_in_rect(pt(25.0, 35.0), r));
        // exclusive right/bottom
        assert!(!point_in_rect(pt(40.0, 35.0), r));
        assert!(!point_in_rect(pt(25.0, 60.0), r));
        // outside
        assert!(!point_in_rect(pt(5.0, 35.0), r));
        assert!(!point_in_rect(pt(25.0, 10.0), r));
    }

    #[test]
    fn point_in_rect_empty_never_hits() {
        assert!(!point_in_rect(pt(0.0, 0.0), Rect::default()));
        assert!(!point_in_rect(pt(0.0, 0.0), Rect::new(0, 0, 0, 5)));
        assert!(!point_in_rect(pt(0.0, 0.0), Rect::new(0, 0, 5, 0)));
    }

    #[test]
    fn point_in_circle_basic() {
        let c = pt(100.0, 100.0);
        assert!(point_in_circle(pt(100.0, 100.0), c, 10.0));
        assert!(point_in_circle(pt(106.0, 108.0), c, 10.0)); // dist = 10, boundary
        assert!(!point_in_circle(pt(107.0, 108.0), c, 10.0));
        assert!(!point_in_circle(pt(0.0, 0.0), c, 10.0));
    }

    #[test]
    fn point_in_circle_zero_radius_misses() {
        assert!(!point_in_circle(pt(0.0, 0.0), pt(0.0, 0.0), 0.0));
        assert!(!point_in_circle(pt(0.0, 0.0), pt(0.0, 0.0), -1.0));
    }

    #[test]
    fn divider_distance_vertical() {
        let r = Rect::new(0, 0, 100, 100);
        assert_eq!(
            distance_to_divider(pt(50.0, 50.0), r, Axis::Vertical, 50.0),
            0.0
        );
        assert_eq!(
            distance_to_divider(pt(55.0, 50.0), r, Axis::Vertical, 50.0),
            5.0
        );
        // outside vertical band: infinity
        assert_eq!(
            distance_to_divider(pt(50.0, 200.0), r, Axis::Vertical, 50.0),
            f64::INFINITY
        );
    }

    #[test]
    fn divider_distance_horizontal() {
        let r = Rect::new(0, 0, 100, 100);
        assert_eq!(
            distance_to_divider(pt(50.0, 30.0), r, Axis::Horizontal, 30.0),
            0.0
        );
        assert_eq!(
            distance_to_divider(pt(50.0, 25.0), r, Axis::Horizontal, 30.0),
            5.0
        );
        assert_eq!(
            distance_to_divider(pt(200.0, 30.0), r, Axis::Horizontal, 30.0),
            f64::INFINITY
        );
    }
}

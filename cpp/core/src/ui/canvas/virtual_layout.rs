//! Virtual-canvas and content-placement math.
//!
//! Ports the current owners:
//! - `src/shared/rendering/layout_contract.py`
//! - `src/ui/canvas_presentation/layout.py`

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct NormalizedBounds {
    pub x_min: f64,
    pub x_max: f64,
    pub y_min: f64,
    pub y_max: f64,
}

impl NormalizedBounds {
    pub const fn unit() -> Self {
        Self {
            x_min: 0.0,
            x_max: 1.0,
            y_min: 0.0,
            y_max: 1.0,
        }
    }

    pub fn union(self, other: Self) -> Self {
        Self {
            x_min: self.x_min.min(other.x_min),
            x_max: self.x_max.max(other.x_max),
            y_min: self.y_min.min(other.y_min),
            y_max: self.y_max.max(other.y_max),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VirtualCanvasLayout {
    pub canvas_bounds: NormalizedBounds,
    pub content_bounds: NormalizedBounds,
}

impl VirtualCanvasLayout {
    pub fn resolve_padding_pixels(self, base_width: i32, base_height: i32) -> (i32, i32, i32, i32) {
        let width = base_width.max(1) as f64;
        let height = base_height.max(1) as f64;
        let pixels = |units: f64, axis: f64| ((units * axis).round_ties_even() as i32).max(0);
        (
            pixels(self.content_bounds.x_min - self.canvas_bounds.x_min, width),
            pixels(self.canvas_bounds.x_max - self.content_bounds.x_max, width),
            pixels(self.content_bounds.y_min - self.canvas_bounds.y_min, height),
            pixels(self.canvas_bounds.y_max - self.content_bounds.y_max, height),
        )
    }
}

pub fn resolve_virtual_canvas_layout(
    requirements: &[NormalizedBounds],
    content_bounds: NormalizedBounds,
) -> VirtualCanvasLayout {
    let canvas_bounds = requirements
        .iter()
        .copied()
        .fold(content_bounds, NormalizedBounds::union);
    VirtualCanvasLayout {
        canvas_bounds,
        content_bounds,
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ContentLayout {
    pub canvas_width: i32,
    pub canvas_height: i32,
    pub content_x: i32,
    pub content_y: i32,
    pub content_width: i32,
    pub content_height: i32,
}

pub fn compute_content_layout(
    target_width: i32,
    target_height: i32,
    image_width: i32,
    image_height: i32,
    stretch: bool,
) -> ContentLayout {
    let canvas_width = target_width.max(1);
    let canvas_height = target_height.max(1);
    if image_width <= 0 || image_height <= 0 {
        return ContentLayout {
            canvas_width,
            canvas_height,
            content_x: 0,
            content_y: 0,
            content_width: 0,
            content_height: 0,
        };
    }
    let (content_width, content_height) = if stretch {
        (canvas_width, canvas_height)
    } else {
        let ratio = (canvas_width as f64 / image_width as f64)
            .min(canvas_height as f64 / image_height as f64);
        (
            ((image_width as f64 * ratio) as i32).max(1),
            ((image_height as f64 * ratio) as i32).max(1),
        )
    };
    ContentLayout {
        canvas_width,
        canvas_height,
        content_x: (canvas_width - content_width) / 2,
        content_y: (canvas_height - content_height) / 2,
        content_width,
        content_height,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalized_bounds_union_matches_python_contract() {
        let result = NormalizedBounds::unit().union(NormalizedBounds {
            x_min: -0.25,
            x_max: 1.5,
            y_min: 0.1,
            y_max: 1.2,
        });
        assert_eq!(
            result,
            NormalizedBounds {
                x_min: -0.25,
                x_max: 1.5,
                y_min: 0.0,
                y_max: 1.2,
            }
        );
    }

    #[test]
    fn empty_requirements_resolve_to_content_bounds() {
        let layout = resolve_virtual_canvas_layout(&[], NormalizedBounds::unit());
        assert_eq!(layout.canvas_bounds, NormalizedBounds::unit());
        assert_eq!(layout.resolve_padding_pixels(100, 50), (0, 0, 0, 0));
    }

    #[test]
    fn padding_matches_python_round_ties_even() {
        let layout = resolve_virtual_canvas_layout(
            &[NormalizedBounds {
                x_min: -0.125,
                x_max: 1.125,
                y_min: -0.25,
                y_max: 1.5,
            }],
            NormalizedBounds::unit(),
        );
        // Python round(12.5) == 12, not 13.
        assert_eq!(layout.resolve_padding_pixels(100, 50), (12, 12, 12, 25));
    }

    #[test]
    fn contain_layout_centers_without_rounding_up() {
        assert_eq!(
            compute_content_layout(800, 400, 100, 100, false),
            ContentLayout {
                canvas_width: 800,
                canvas_height: 400,
                content_x: 200,
                content_y: 0,
                content_width: 400,
                content_height: 400,
            }
        );
        assert_eq!(
            compute_content_layout(101, 100, 3, 2, false).content_width,
            101
        );
        assert_eq!(
            compute_content_layout(101, 100, 3, 2, false).content_height,
            67
        );
    }

    #[test]
    fn stretch_and_empty_layout_match_python() {
        let stretched = compute_content_layout(320, 180, 10, 20, true);
        assert_eq!(
            (stretched.content_width, stretched.content_height),
            (320, 180)
        );
        let empty = compute_content_layout(0, 0, 0, 20, false);
        assert_eq!(
            empty,
            ContentLayout {
                canvas_width: 1,
                canvas_height: 1,
                content_x: 0,
                content_y: 0,
                content_width: 0,
                content_height: 0,
            }
        );
    }
}

//! Canvas render-plan builder. Single source of truth for assembling the
//! `(texture_id, canvas_w/h, split, divider/magnifier/guides/...)` POD that
//! the QRhi canvas consumes.
//!
//! Mirrors the Python `src/ui/canvas_presentation/plan_builder.py` build path
//! used by every comparison consumer (the canvas widget, the multi-compare
//! grid, the offscreen renderer). Inputs are explicit — there is no implicit
//! feature-registry lookup the way Python does it, because the C++ shell
//! resolves feature toggles before calling in.
//!
//! Defaults follow Python's `plan_builder._FallbackGuidesState` +
//! `_FallbackCaptureState` + the literal constants in the legacy
//! `build_compare_render_plan` adapter that this module supersedes.

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use crate::domain::Color;
use crate::ui::canvas::plan::OverlayLayout;

/// Plain-data inputs the canvas plan needs. All feature toggles are explicit;
/// the caller (ComparisonController, MultiCompareGrid, …) decides them.
#[derive(Debug, Clone)]
pub struct PlanInputs {
    /// Stable identifier for the left image — typically its filesystem path,
    /// but any utf-8 string the caller wants to hash works. Empty means
    /// «no image» and yields a zero texture id.
    pub left_key: String,
    pub right_key: String,
    pub canvas_width: u32,
    pub canvas_height: u32,
    /// Divider position in `[0.0, 1.0]`. Clamped on build.
    pub split: f32,
    pub horizontal: bool,
    pub divider: DividerSpec,
    pub magnifier: MagnifierSpec,
    pub features: FeatureToggles,
    /// Optional display labels. If both are empty, the file-basename of the
    /// `*_key` is used (matches the Python fallback behaviour).
    pub left_label: Option<String>,
    pub right_label: Option<String>,
    pub fill: Rgba8,
    /// Overlay-specific knobs (border, channel/diff/interp modes). When
    /// `None`, the produced plan carries no `OverlayLayout` and the legacy
    /// flat fields drive rendering — the path comparison/multi-compare
    /// take today.
    pub overlay: Option<OverlaySpec>,
}

/// Inputs feeding the rich `OverlayLayout`. Slot/capture/guide synthesis is
/// performed by the builder when the corresponding feature toggles are on;
/// the bare `OverlaySpec` only carries the global knobs (border, modes).
#[derive(Debug, Clone, Copy)]
pub struct OverlaySpec {
    pub border_color: Option<Rgba8>,
    pub border_width: f32,
    /// 0 = all channels, 1..=4 = R/G/B/A. Matches Python `channel_mode` enum.
    pub channel_mode: i32,
    /// 0 = off, 1..= per Python `diff_mode` matrix.
    pub diff_mode: i32,
    /// 0 = nearest, 1 = bilinear. Matches `OverlayLayout::interp_mode`.
    pub interp_mode: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct DividerSpec {
    pub enabled: bool,
    pub thickness: f32,
}

#[derive(Debug, Clone, Copy)]
pub struct MagnifierSpec {
    pub capture_x: f32,
    pub capture_y: f32,
    pub magnifier_x: f32,
    pub magnifier_y: f32,
    pub radius: f32,
    pub zoom: f32,
}

#[derive(Debug, Clone, Copy)]
pub struct FeatureToggles {
    pub magnifier: bool,
    pub guides: bool,
    pub capture: bool,
    pub filename: bool,
    pub paste_overlay: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rgba8 {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl Rgba8 {
    pub const DEFAULT_FILL: Self = Self {
        r: 37,
        g: 37,
        b: 37,
        a: 255,
    };
}

impl Default for DividerSpec {
    fn default() -> Self {
        Self {
            enabled: true,
            thickness: 2.0,
        }
    }
}

impl Default for MagnifierSpec {
    fn default() -> Self {
        Self {
            capture_x: 0.35,
            capture_y: 0.5,
            magnifier_x: 0.7,
            magnifier_y: 0.5,
            radius: 0.16,
            zoom: 2.0,
        }
    }
}

impl Default for FeatureToggles {
    fn default() -> Self {
        Self {
            magnifier: false,
            guides: false,
            capture: false,
            filename: true,
            paste_overlay: false,
        }
    }
}

impl Default for OverlaySpec {
    fn default() -> Self {
        Self {
            border_color: None,
            border_width: 2.0,
            channel_mode: 0,
            diff_mode: 0,
            interp_mode: 1,
        }
    }
}

impl Default for PlanInputs {
    fn default() -> Self {
        Self {
            left_key: String::new(),
            right_key: String::new(),
            canvas_width: 1,
            canvas_height: 1,
            split: 0.5,
            horizontal: false,
            divider: DividerSpec::default(),
            magnifier: MagnifierSpec::default(),
            features: FeatureToggles::default(),
            left_label: None,
            right_label: None,
            fill: Rgba8::DEFAULT_FILL,
            overlay: None,
        }
    }
}

/// POD result. The flat fields mirror the existing cxx ffi struct so the
/// bridge layer can copy 1-to-1; `overlay` carries the rich layout (slots,
/// captures, guides, channel/diff/interp modes) for callers that consume it
/// through the JSON router.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct BuiltPlan {
    pub texture1_id: u64,
    pub texture2_id: u64,
    pub canvas_w: i32,
    pub canvas_h: i32,
    pub split: f32,
    pub horizontal: bool,
    pub divider_enabled: bool,
    pub divider_thickness: f32,
    pub magnifier_enabled: bool,
    pub capture_x: f32,
    pub capture_y: f32,
    pub magnifier_x: f32,
    pub magnifier_y: f32,
    pub magnifier_radius: f32,
    pub magnifier_zoom: f32,
    pub guides_enabled: bool,
    pub capture_enabled: bool,
    pub filename_enabled: bool,
    pub paste_overlay_enabled: bool,
    pub left_label: String,
    pub right_label: String,
    pub fill_r: u8,
    pub fill_g: u8,
    pub fill_b: u8,
    pub fill_a: u8,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub overlay: Option<OverlayLayout>,
}

/// Build the canvas plan from `inputs`. This is the single canonical entry
/// point both for live UI updates and offscreen export.
pub fn build_plan(inputs: &PlanInputs) -> BuiltPlan {
    let canvas_w = i32::try_from(inputs.canvas_width.max(1)).unwrap_or(i32::MAX);
    let canvas_h = i32::try_from(inputs.canvas_height.max(1)).unwrap_or(i32::MAX);
    let texture1_id =
        stable_texture_id(&inputs.left_key, inputs.canvas_width, inputs.canvas_height);
    let texture2_id =
        stable_texture_id(&inputs.right_key, inputs.canvas_width, inputs.canvas_height);
    let left_label = resolve_label(inputs.left_label.as_deref(), &inputs.left_key);
    let right_label = resolve_label(inputs.right_label.as_deref(), &inputs.right_key);
    let split = inputs.split.clamp(0.0, 1.0);
    let overlay = inputs
        .overlay
        .as_ref()
        .map(|spec| build_overlay(inputs, spec, split));

    BuiltPlan {
        texture1_id,
        texture2_id,
        canvas_w,
        canvas_h,
        split,
        horizontal: inputs.horizontal,
        divider_enabled: inputs.divider.enabled,
        divider_thickness: inputs.divider.thickness.max(0.0),
        magnifier_enabled: inputs.features.magnifier,
        capture_x: inputs.magnifier.capture_x,
        capture_y: inputs.magnifier.capture_y,
        magnifier_x: inputs.magnifier.magnifier_x,
        magnifier_y: inputs.magnifier.magnifier_y,
        magnifier_radius: inputs.magnifier.radius,
        magnifier_zoom: inputs.magnifier.zoom,
        guides_enabled: inputs.features.guides,
        capture_enabled: inputs.features.capture || inputs.features.magnifier,
        filename_enabled: inputs.features.filename,
        paste_overlay_enabled: inputs.features.paste_overlay,
        left_label,
        right_label,
        fill_r: inputs.fill.r,
        fill_g: inputs.fill.g,
        fill_b: inputs.fill.b,
        fill_a: inputs.fill.a,
        overlay,
    }
}

fn build_overlay(inputs: &PlanInputs, spec: &OverlaySpec, split: f32) -> OverlayLayout {
    use crate::domain::Point;
    use crate::ui::canvas::plan::{CaptureCircle, GuideSet, OverlaySlot};

    let mut layout = OverlayLayout {
        border_color: spec.border_color.map(rgba_to_color),
        border_width: spec.border_width.max(0.0),
        channel_mode: spec.channel_mode,
        diff_mode: spec.diff_mode,
        interp_mode: spec.interp_mode,
        ..OverlayLayout::default()
    };

    if inputs.features.magnifier {
        let center = Point {
            x: inputs.magnifier.magnifier_x as f64,
            y: inputs.magnifier.magnifier_y as f64,
        };
        let radius = inputs.magnifier.radius.max(0.0);
        // One combined slot — split-aware uv_rect mirrors Python's
        // `overlay.render_build_layout` for the single-magnifier case.
        layout.slots.push(OverlaySlot {
            center,
            radius,
            uv_rect: split_uv_rect(split, inputs.horizontal, true),
            uv_rect2: split_uv_rect(split, inputs.horizontal, false),
            source: 0,
            is_combined: true,
            internal_split: split,
            horizontal: inputs.horizontal,
            divider_visible: inputs.divider.enabled,
            divider_color: [1.0, 1.0, 1.0, 1.0],
            divider_thickness_uv: divider_thickness_uv(inputs.divider.thickness, radius),
            border_color: spec.border_color.map(rgba_to_color).unwrap_or(Color::WHITE),
            border_width: spec.border_width.max(0.0),
        });
        layout
            .overlay_centers
            .push((center.x as f32, center.y as f32));
        layout.overlay_radius = radius;
    }

    if inputs.features.capture || inputs.features.magnifier {
        let capture_center = Point {
            x: inputs.magnifier.capture_x as f64,
            y: inputs.magnifier.capture_y as f64,
        };
        let capture_radius = inputs.magnifier.radius.max(0.0);
        layout.capture_circles.push(CaptureCircle {
            center: capture_center,
            radius: capture_radius,
            color: Color::WHITE,
        });
        layout.capture_center = Some(capture_center);
        layout.capture_radius = capture_radius;
    }

    if inputs.features.guides && inputs.features.magnifier {
        let capture_center = Point {
            x: inputs.magnifier.capture_x as f64,
            y: inputs.magnifier.capture_y as f64,
        };
        let target_center = Point {
            x: inputs.magnifier.magnifier_x as f64,
            y: inputs.magnifier.magnifier_y as f64,
        };
        let radius = inputs.magnifier.radius.max(0.0);
        layout.guide_sets.push(GuideSet {
            capture_center,
            capture_radius: radius,
            target_centers: vec![target_center],
            target_radii: vec![radius],
            color: Color::WHITE,
        });
    }

    layout
}

fn split_uv_rect(split: f32, horizontal: bool, is_left: bool) -> [f32; 4] {
    if horizontal {
        if is_left {
            [0.0, 0.0, 1.0, split]
        } else {
            [0.0, split, 1.0, 1.0 - split]
        }
    } else if is_left {
        [0.0, 0.0, split, 1.0]
    } else {
        [split, 0.0, 1.0 - split, 1.0]
    }
}

fn divider_thickness_uv(thickness_px: f32, radius_norm: f32) -> f32 {
    // Approximation: the divider thickness in UV-space is the pixel thickness
    // divided by the radius's contribution. The real (Python) value comes from
    // `overlay.active_divider_thickness`; this stays close enough for cargo
    // tests and degrades gracefully when the caller has no overlay context.
    if radius_norm <= 0.0 {
        return 0.0;
    }
    (thickness_px / 1000.0).clamp(0.0, 0.05)
}

fn rgba_to_color(rgba: Rgba8) -> Color {
    Color {
        r: rgba.r,
        g: rgba.g,
        b: rgba.b,
        a: rgba.a,
    }
}

fn stable_texture_id(key: &str, width: u32, height: u32) -> u64 {
    if key.is_empty() {
        return 0;
    }
    let mut hasher = DefaultHasher::new();
    key.hash(&mut hasher);
    width.hash(&mut hasher);
    height.hash(&mut hasher);
    hasher.finish().max(1)
}

fn resolve_label(explicit: Option<&str>, key: &str) -> String {
    if let Some(label) = explicit {
        if !label.is_empty() {
            return label.to_string();
        }
    }
    if key.is_empty() {
        return String::new();
    }
    std::path::Path::new(key)
        .file_name()
        .and_then(|value| value.to_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| key.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn baseline() -> PlanInputs {
        PlanInputs {
            left_key: "/tmp/left.png".to_string(),
            right_key: "/tmp/right.png".to_string(),
            canvas_width: 800,
            canvas_height: 600,
            ..PlanInputs::default()
        }
    }

    #[test]
    fn defaults_match_legacy_python_constants() {
        let plan = build_plan(&baseline());
        assert_eq!(plan.canvas_w, 800);
        assert_eq!(plan.canvas_h, 600);
        assert_eq!(plan.split, 0.5);
        assert!(plan.divider_enabled);
        assert_eq!(plan.divider_thickness, 2.0);
        assert_eq!(plan.capture_x, 0.35);
        assert_eq!(plan.capture_y, 0.5);
        assert_eq!(plan.magnifier_x, 0.7);
        assert_eq!(plan.magnifier_radius, 0.16);
        assert_eq!(plan.magnifier_zoom, 2.0);
        assert_eq!(
            (plan.fill_r, plan.fill_g, plan.fill_b, plan.fill_a),
            (37, 37, 37, 255)
        );
        assert!(plan.filename_enabled);
        assert!(!plan.magnifier_enabled);
        assert!(!plan.guides_enabled);
        assert!(!plan.capture_enabled);
        assert!(!plan.paste_overlay_enabled);
        assert_eq!(plan.left_label, "left.png");
        assert_eq!(plan.right_label, "right.png");
    }

    #[test]
    fn empty_keys_yield_zero_texture_ids_and_blank_labels() {
        let plan = build_plan(&PlanInputs::default());
        assert_eq!(plan.texture1_id, 0);
        assert_eq!(plan.texture2_id, 0);
        assert!(plan.left_label.is_empty());
        assert!(plan.right_label.is_empty());
    }

    #[test]
    fn explicit_label_wins_over_key_basename() {
        let inputs = PlanInputs {
            left_label: Some("Custom Left".to_string()),
            ..baseline()
        };
        let plan = build_plan(&inputs);
        assert_eq!(plan.left_label, "Custom Left");
        assert_eq!(plan.right_label, "right.png");
    }

    #[test]
    fn split_is_clamped_into_unit_interval() {
        let low = build_plan(&PlanInputs {
            split: -0.5,
            ..baseline()
        });
        let high = build_plan(&PlanInputs {
            split: 2.0,
            ..baseline()
        });
        assert_eq!(low.split, 0.0);
        assert_eq!(high.split, 1.0);
    }

    #[test]
    fn texture_ids_are_stable_for_same_key_and_size() {
        let a = build_plan(&baseline());
        let b = build_plan(&baseline());
        assert_eq!(a.texture1_id, b.texture1_id);
        assert_eq!(a.texture2_id, b.texture2_id);
        assert_ne!(a.texture1_id, a.texture2_id);
    }

    #[test]
    fn texture_id_depends_on_canvas_size() {
        let a = build_plan(&baseline());
        let b = build_plan(&PlanInputs {
            canvas_width: 1600,
            canvas_height: 1200,
            ..baseline()
        });
        assert_ne!(a.texture1_id, b.texture1_id);
    }

    #[test]
    fn enabling_magnifier_implies_capture_visible() {
        let plan = build_plan(&PlanInputs {
            features: FeatureToggles {
                magnifier: true,
                ..FeatureToggles::default()
            },
            ..baseline()
        });
        assert!(plan.magnifier_enabled);
        assert!(plan.capture_enabled);
    }

    #[test]
    fn explicit_capture_toggle_survives_without_magnifier() {
        let plan = build_plan(&PlanInputs {
            features: FeatureToggles {
                capture: true,
                ..FeatureToggles::default()
            },
            ..baseline()
        });
        assert!(!plan.magnifier_enabled);
        assert!(plan.capture_enabled);
    }

    #[test]
    fn canvas_dimensions_are_at_least_one() {
        let plan = build_plan(&PlanInputs {
            canvas_width: 0,
            canvas_height: 0,
            ..baseline()
        });
        assert_eq!(plan.canvas_w, 1);
        assert_eq!(plan.canvas_h, 1);
    }

    #[test]
    fn no_overlay_spec_yields_no_overlay_layout() {
        let plan = build_plan(&baseline());
        assert!(plan.overlay.is_none());
    }

    #[test]
    fn overlay_spec_without_magnifier_has_empty_slots() {
        let plan = build_plan(&PlanInputs {
            overlay: Some(OverlaySpec::default()),
            ..baseline()
        });
        let layout = plan.overlay.expect("overlay layout");
        assert!(layout.slots.is_empty());
        assert!(layout.capture_circles.is_empty());
        assert!(layout.guide_sets.is_empty());
        assert_eq!(layout.interp_mode, 1);
        assert_eq!(layout.channel_mode, 0);
    }

    #[test]
    fn overlay_synthesises_slot_and_capture_when_magnifier_on() {
        let plan = build_plan(&PlanInputs {
            features: FeatureToggles {
                magnifier: true,
                ..FeatureToggles::default()
            },
            overlay: Some(OverlaySpec::default()),
            ..baseline()
        });
        let layout = plan.overlay.expect("overlay layout");
        assert_eq!(layout.slots.len(), 1);
        let slot = &layout.slots[0];
        assert!(slot.is_combined);
        assert!((slot.center.x - 0.7).abs() < 1e-6);
        assert_eq!(slot.internal_split, 0.5);
        assert!(!slot.horizontal);
        // Vertical split with 0.5 split: left rect = [0,0,0.5,1], right = [0.5,0,0.5,1].
        assert_eq!(slot.uv_rect, [0.0, 0.0, 0.5, 1.0]);
        assert_eq!(slot.uv_rect2, [0.5, 0.0, 0.5, 1.0]);
        assert_eq!(layout.capture_circles.len(), 1);
        assert_eq!(layout.overlay_centers.len(), 1);
        let (cx, cy) = layout.overlay_centers[0];
        assert!((cx - 0.7).abs() < 1e-6);
        assert!((cy - 0.5).abs() < 1e-6);
    }

    #[test]
    fn horizontal_split_swaps_uv_axis() {
        let plan = build_plan(&PlanInputs {
            horizontal: true,
            split: 0.25,
            features: FeatureToggles {
                magnifier: true,
                ..FeatureToggles::default()
            },
            overlay: Some(OverlaySpec::default()),
            ..baseline()
        });
        let layout = plan.overlay.expect("overlay layout");
        let slot = &layout.slots[0];
        assert!(slot.horizontal);
        assert_eq!(slot.uv_rect, [0.0, 0.0, 1.0, 0.25]);
        assert_eq!(slot.uv_rect2, [0.0, 0.25, 1.0, 0.75]);
    }

    #[test]
    fn guides_only_synthesise_when_magnifier_is_also_on() {
        let only_guides = build_plan(&PlanInputs {
            features: FeatureToggles {
                guides: true,
                ..FeatureToggles::default()
            },
            overlay: Some(OverlaySpec::default()),
            ..baseline()
        });
        assert!(only_guides
            .overlay
            .as_ref()
            .map(|l| l.guide_sets.is_empty())
            .unwrap_or(false));

        let guides_with_magnifier = build_plan(&PlanInputs {
            features: FeatureToggles {
                guides: true,
                magnifier: true,
                ..FeatureToggles::default()
            },
            overlay: Some(OverlaySpec::default()),
            ..baseline()
        });
        let guide_sets = &guides_with_magnifier.overlay.unwrap().guide_sets;
        assert_eq!(guide_sets.len(), 1);
        assert_eq!(guide_sets[0].target_centers.len(), 1);
        assert!((guide_sets[0].target_centers[0].x - 0.7).abs() < 1e-6);
    }

    #[test]
    fn overlay_spec_channel_and_diff_modes_pass_through() {
        let plan = build_plan(&PlanInputs {
            overlay: Some(OverlaySpec {
                channel_mode: 3,
                diff_mode: 2,
                interp_mode: 0,
                border_width: 4.5,
                border_color: Some(Rgba8 {
                    r: 10,
                    g: 20,
                    b: 30,
                    a: 255,
                }),
            }),
            ..baseline()
        });
        let layout = plan.overlay.expect("overlay layout");
        assert_eq!(layout.channel_mode, 3);
        assert_eq!(layout.diff_mode, 2);
        assert_eq!(layout.interp_mode, 0);
        assert_eq!(layout.border_width, 4.5);
        assert_eq!(layout.border_color.unwrap().r, 10);
    }

    #[test]
    fn built_plan_round_trips_through_json() {
        let original = build_plan(&PlanInputs {
            features: FeatureToggles {
                magnifier: true,
                guides: true,
                ..FeatureToggles::default()
            },
            overlay: Some(OverlaySpec::default()),
            ..baseline()
        });
        let json = serde_json::to_string(&original).expect("serialize");
        let decoded: BuiltPlan = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(original.texture1_id, decoded.texture1_id);
        assert_eq!(original.left_label, decoded.left_label);
        assert_eq!(
            original.overlay.as_ref().unwrap().slots.len(),
            decoded.overlay.as_ref().unwrap().slots.len()
        );
    }
}

//! FFI surface exposed to C++ via the `cxx` crate.
//!
//! Keep this file narrow. Anything crossing the boundary must be plain data.
//! Qt types never cross. QRHI never crosses.
//!
//! Phase-1 surface:
//! - `core_version` / `core_greeting`         — smoke checks.
//! - `settings_default_json`                  — fresh default config.
//! - `settings_roundtrip_json`                — parse + re-serialize (validation).
//! - `state_default_json`                     — fresh default `AppState`.
//! - `state_dispatch_action`                  — apply one JSON-encoded action to
//!   a JSON-encoded state, return `(new_state_json, scope_string)`.
//! - `RustStore`                              — stateful store owned by C++.
//! - `decode_image_rgba8`                     — Rust image decode to plain RGBA.
//! - `letterbox_rect`                         — pure geometry, no state needed.

use cxx::CxxString;
use std::hash::{Hash, Hasher};
use std::pin::Pin;

pub struct RustStore {
    inner: crate::core::store::Store,
}

#[cxx::bridge(namespace = "imgsli")]
mod ffi {
    /// Result of `state_dispatch_action` — `state_json` is the new state,
    /// `scope` is a short tag suitable for routing to subscribers.
    pub struct DispatchResult {
        pub state_json: String,
        pub scope: String,
    }

    /// Result of `letterbox_rect`.
    pub struct RectI32 {
        pub x: i32,
        pub y: i32,
        pub w: i32,
        pub h: i32,
    }

    pub struct NormalizedBoundsF64 {
        pub x_min: f64,
        pub x_max: f64,
        pub y_min: f64,
        pub y_max: f64,
    }

    pub struct VirtualCanvasLayoutF64 {
        pub canvas_bounds: NormalizedBoundsF64,
        pub content_bounds: NormalizedBoundsF64,
    }

    pub struct PaddingI32 {
        pub left: i32,
        pub right: i32,
        pub top: i32,
        pub bottom: i32,
    }

    pub struct ContentLayoutI32 {
        pub canvas_width: i32,
        pub canvas_height: i32,
        pub content_x: i32,
        pub content_y: i32,
        pub content_width: i32,
        pub content_height: i32,
    }

    pub struct DecodedImage {
        pub pixels: Vec<u8>,
        pub width: u32,
        pub height: u32,
    }

    pub struct AnalysisMetrics {
        pub psnr: f64,
        pub ssim: f64,
    }

    pub struct SingleImageRenderPlan {
        pub texture_id: u64,
        pub canvas_w: i32,
        pub canvas_h: i32,
        pub fill_r: u8,
        pub fill_g: u8,
        pub fill_b: u8,
        pub fill_a: u8,
    }

    pub struct CanvasRenderPlan {
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
    }

    pub struct StackOrder {
        pub phase: i32,
        pub priority: i32,
    }

    /// Inputs for the canonical canvas plan builder. Flat for cxx compatibility —
    /// the Rust side reassembles them into `shared::rendering::plan_builder`'s
    /// nested specs. Field defaults are documented on the Rust types.
    pub struct CanvasPlanInputs {
        pub left_key: String,
        pub right_key: String,
        pub canvas_width: u32,
        pub canvas_height: u32,
        pub split: f32,
        pub horizontal: bool,
        pub divider_enabled: bool,
        pub divider_thickness: f32,
        pub capture_x: f32,
        pub capture_y: f32,
        pub magnifier_x: f32,
        pub magnifier_y: f32,
        pub magnifier_radius: f32,
        pub magnifier_zoom: f32,
        pub feature_magnifier: bool,
        pub feature_guides: bool,
        pub feature_capture: bool,
        pub feature_filename: bool,
        pub feature_paste_overlay: bool,
        /// Empty string means «derive from key basename».
        pub left_label: String,
        pub right_label: String,
        pub fill_r: u8,
        pub fill_g: u8,
        pub fill_b: u8,
        pub fill_a: u8,
        /// When true, the builder produces a rich `OverlayLayout` (consumed via
        /// the JSON router). When false, only flat fields are populated and the
        /// flat `build_canvas_render_plan` covers the caller.
        pub overlay_enabled: bool,
        /// When true, `overlay_border_*` carries an explicit border colour;
        /// otherwise white is used.
        pub overlay_has_border_color: bool,
        pub overlay_border_r: u8,
        pub overlay_border_g: u8,
        pub overlay_border_b: u8,
        pub overlay_border_a: u8,
        pub overlay_border_width: f32,
        pub overlay_channel_mode: i32,
        pub overlay_diff_mode: i32,
        pub overlay_interp_mode: i32,
    }

    unsafe extern "C++" {
        include!("imgsli/store_observer.h");

        type StoreObserver;
        fn on_rust_state_changed(self: Pin<&mut StoreObserver>, state_json: String, scope: String);
    }

    extern "Rust" {
        type RustStore;

        fn core_version() -> String;
        fn core_greeting(name: &str) -> String;

        fn settings_default_json() -> String;
        fn settings_roundtrip_json(input: &str) -> Result<String>;

        fn settings_dialog_default_json() -> String;
        fn settings_dialog_normalize_json(input: &str) -> Result<String>;
        fn settings_dialog_diff_json(prev: &str, next: &str) -> Result<String>;

        fn i18n_init(root: &str);
        fn i18n_set_language(lang: &str);
        fn i18n_translate(key: &str) -> String;

        fn playlist_remove_at(len_before: i32, current: i32, removed_at: i32) -> i32;
        fn playlist_reorder(current: i32, source: i32, dest: i32) -> i32;
        fn playlist_resolve_cross_move(
            previous_path_match: i32,
            target_len_after_move: i32,
            same_list_and_was_current: bool,
            source_index: i32,
        ) -> i32;

        fn video_project_default_json() -> String;
        fn video_project_ffmpeg_args_json(project_json: &str) -> Result<String>;
        fn video_project_adjust_height(project_json: &str, width: i32) -> Result<i32>;
        fn video_project_adjust_width(project_json: &str, height: i32) -> Result<i32>;
        fn video_selection_set_json(start: i64, has_start: bool, end: i64, has_end: bool)
            -> String;
        fn video_timeline_advance(position: i64, step: i64) -> i64;

        fn state_default_json() -> String;
        fn state_dispatch_action(
            state_json: &CxxString,
            action_json: &CxxString,
        ) -> Result<DispatchResult>;

        fn new_store() -> Box<RustStore>;
        fn store_state_json(store: &RustStore) -> String;
        fn store_dispatch(
            store: Pin<&mut RustStore>,
            observer: Pin<&mut StoreObserver>,
            action_json: &CxxString,
        ) -> Result<DispatchResult>;

        fn decode_image_rgba8(path: &CxxString) -> Result<DecodedImage>;
        fn analysis_metrics_rgba8(
            left: &[u8],
            right: &[u8],
            width: u32,
            height: u32,
        ) -> Result<AnalysisMetrics>;
        fn analysis_diff_rgba8(
            left: &[u8],
            right: &[u8],
            width: u32,
            height: u32,
            mode: &str,
            channel_mode: &str,
        ) -> Result<DecodedImage>;
        fn analysis_channel_rgba8(
            image: &[u8],
            width: u32,
            height: u32,
            channel_mode: &str,
        ) -> Result<DecodedImage>;
        fn build_single_image_render_plan(
            path: &CxxString,
            width: u32,
            height: u32,
        ) -> Result<SingleImageRenderPlan>;
        #[allow(clippy::too_many_arguments)]
        fn build_compare_render_plan(
            left_path: &CxxString,
            right_path: &CxxString,
            width: u32,
            height: u32,
            split: f32,
            horizontal: bool,
            magnifier_enabled: bool,
            guides_enabled: bool,
            paste_overlay_enabled: bool,
        ) -> Result<CanvasRenderPlan>;
        /// Canonical canvas plan builder shared by the comparison plugin and
        /// the multi-compare grid. Wraps `shared::rendering::plan_builder`.
        fn build_canvas_render_plan(inputs: &CanvasPlanInputs) -> CanvasRenderPlan;
        /// Same builder, but the result includes the rich `OverlayLayout`
        /// (slots, capture circles, guide sets, channel/diff/interp modes).
        /// Returned as JSON because cxx-bridge cannot express the nested
        /// optional + vector shape directly. C++ parses with `QJsonDocument`.
        fn build_canvas_render_plan_json(inputs: &CanvasPlanInputs) -> Result<String>;
        fn resolve_stack_order(role: i32) -> StackOrder;

        fn letterbox_rect(widget_w: i32, widget_h: i32, canvas_w: i32, canvas_h: i32) -> RectI32;
        fn resolve_virtual_canvas_layout(
            requirements: &[NormalizedBoundsF64],
            content_bounds: &NormalizedBoundsF64,
        ) -> VirtualCanvasLayoutF64;
        fn resolve_virtual_canvas_padding(
            layout: &VirtualCanvasLayoutF64,
            base_width: i32,
            base_height: i32,
        ) -> PaddingI32;
        fn compute_content_layout(
            target_width: i32,
            target_height: i32,
            image_width: i32,
            image_height: i32,
            stretch: bool,
        ) -> ContentLayoutI32;
    }
}

fn core_version() -> String {
    crate::version().to_string()
}

fn core_greeting(name: &str) -> String {
    format!("ImgSLI core {} says hello, {}", crate::version(), name)
}

fn settings_default_json() -> String {
    crate::plugins::settings::model::SettingsState::default().to_json_pretty()
}

fn settings_roundtrip_json(
    input: &str,
) -> Result<String, crate::plugins::settings::model::SettingsError> {
    let s = crate::plugins::settings::model::SettingsState::from_json(input)?;
    Ok(s.to_json_pretty())
}

fn settings_dialog_default_json() -> String {
    crate::plugins::settings::dialog::SettingsDialogData::default().to_json_pretty()
}

fn settings_dialog_normalize_json(input: &str) -> Result<String, serde_json::Error> {
    let mut d = crate::plugins::settings::dialog::SettingsDialogData::from_json(input)?;
    d.normalize();
    Ok(d.to_json_pretty())
}

fn settings_dialog_diff_json(prev: &str, next: &str) -> Result<String, serde_json::Error> {
    crate::plugins::settings::dialog::diff_json(prev, next)
}

fn i18n_init(root: &str) {
    crate::i18n::init(root);
}

fn i18n_set_language(lang: &str) {
    crate::i18n::set_language(lang);
}

fn i18n_translate(key: &str) -> String {
    crate::i18n::translate(key)
}

fn playlist_remove_at(len_before: i32, current: i32, removed_at: i32) -> i32 {
    crate::tabs::multi_compare::playlist::remove_at(len_before, current, removed_at)
}

fn playlist_reorder(current: i32, source: i32, dest: i32) -> i32 {
    crate::tabs::multi_compare::playlist::reorder(current, source, dest)
}

fn playlist_resolve_cross_move(
    previous_path_match: i32,
    target_len_after_move: i32,
    same_list_and_was_current: bool,
    source_index: i32,
) -> i32 {
    crate::tabs::multi_compare::playlist::resolve_after_cross_move(
        previous_path_match,
        target_len_after_move,
        same_list_and_was_current,
        source_index,
    )
}

fn video_project_default_json() -> String {
    crate::plugins::video_editor::ProjectModel::default().to_json()
}

fn video_project_ffmpeg_args_json(project_json: &str) -> Result<String, serde_json::Error> {
    let p = crate::plugins::video_editor::ProjectModel::from_json(project_json)?;
    Ok(serde_json::to_string(&p.ffmpeg_args()).expect("ffmpeg args serialize"))
}

fn video_project_adjust_height(project_json: &str, width: i32) -> Result<i32, serde_json::Error> {
    let p = crate::plugins::video_editor::ProjectModel::from_json(project_json)?;
    Ok(p.adjust_height_to_aspect_ratio(width))
}

fn video_project_adjust_width(project_json: &str, height: i32) -> Result<i32, serde_json::Error> {
    let p = crate::plugins::video_editor::ProjectModel::from_json(project_json)?;
    Ok(p.adjust_width_to_aspect_ratio(height))
}

fn video_selection_set_json(start: i64, has_start: bool, end: i64, has_end: bool) -> String {
    let sel = crate::plugins::video_editor::SelectionState::set(
        if has_start { Some(start) } else { None },
        if has_end { Some(end) } else { None },
    );
    serde_json::to_string(&sel).expect("selection serialize")
}

fn video_timeline_advance(position: i64, step: i64) -> i64 {
    crate::plugins::video_editor::TimelineState::new(position)
        .advance(step)
        .position
}

fn analysis_metrics_rgba8(
    left: &[u8],
    right: &[u8],
    width: u32,
    height: u32,
) -> Result<ffi::AnalysisMetrics, crate::plugins::analysis::AnalysisError> {
    let result = crate::plugins::analysis::metrics(left, right, width, height)?;
    Ok(ffi::AnalysisMetrics {
        psnr: result.psnr,
        ssim: result.ssim,
    })
}

fn analysis_diff_rgba8(
    left: &[u8],
    right: &[u8],
    width: u32,
    height: u32,
    mode: &str,
    channel_mode: &str,
) -> Result<ffi::DecodedImage, crate::plugins::analysis::AnalysisError> {
    Ok(ffi::DecodedImage {
        pixels: crate::plugins::analysis::diff(left, right, width, height, mode, channel_mode)?,
        width,
        height,
    })
}

fn analysis_channel_rgba8(
    image: &[u8],
    width: u32,
    height: u32,
    channel_mode: &str,
) -> Result<ffi::DecodedImage, crate::plugins::analysis::AnalysisError> {
    Ok(ffi::DecodedImage {
        pixels: crate::plugins::analysis::channel(image, width, height, channel_mode)?,
        width,
        height,
    })
}

fn state_default_json() -> String {
    serde_json::to_string_pretty(&crate::core::state::AppState::default()).expect("state serialize")
}

#[derive(Debug, thiserror::Error)]
pub enum BridgeError {
    #[error("invalid state json: {0}")]
    State(serde_json::Error),
    #[error("invalid action json: {0}")]
    Action(serde_json::Error),
    #[error("image decode failed: {0}")]
    Image(#[from] image::ImageError),
    #[error("image file access failed: {0}")]
    ImageIo(#[from] std::io::Error),
    #[error("image path is not valid UTF-8: {0}")]
    ImagePath(String),
    #[error("image dimensions exceed the supported 16384 px edge limit")]
    ImageTooLarge,
    #[error("internal error: {0}")]
    Internal(String),
}

fn state_dispatch_action(
    state_json: &CxxString,
    action_json: &CxxString,
) -> Result<ffi::DispatchResult, BridgeError> {
    let state_str = state_json.to_str().map_err(|e| {
        BridgeError::State(serde_json::Error::io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            e.to_string(),
        )))
    })?;
    let action_str = action_json.to_str().map_err(|e| {
        BridgeError::Action(serde_json::Error::io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            e.to_string(),
        )))
    })?;
    let mut state: crate::core::state::AppState =
        serde_json::from_str(state_str).map_err(BridgeError::State)?;
    let action: crate::core::action::Action =
        serde_json::from_str(action_str).map_err(BridgeError::Action)?;
    let scope = crate::core::reducer::apply(&mut state, &action);
    let scope_str = match scope {
        crate::core::reducer::Scope::Settings => "settings".to_string(),
        crate::core::reducer::Scope::Viewport(tag) => format!("viewport.{}", tag),
        crate::core::reducer::Scope::Document => "document".to_string(),
        crate::core::reducer::Scope::Workspace => "workspace".to_string(),
        crate::core::reducer::Scope::NoOp => "noop".to_string(),
    };
    Ok(ffi::DispatchResult {
        state_json: serde_json::to_string(&state).expect("state serialize"),
        scope: scope_str,
    })
}

fn new_store() -> Box<RustStore> {
    Box::new(RustStore {
        inner: crate::core::store::Store::new(),
    })
}

fn store_state_json(store: &RustStore) -> String {
    serde_json::to_string(store.inner.state()).expect("state serialize")
}

fn store_dispatch(
    mut store: Pin<&mut RustStore>,
    mut observer: Pin<&mut ffi::StoreObserver>,
    action_json: &CxxString,
) -> Result<ffi::DispatchResult, BridgeError> {
    let result = dispatch_store(store.as_mut().get_mut(), action_json)?;
    observer
        .as_mut()
        .on_rust_state_changed(result.state_json.clone(), result.scope.clone());
    Ok(result)
}

fn dispatch_store(
    store: &mut RustStore,
    action_json: &CxxString,
) -> Result<ffi::DispatchResult, BridgeError> {
    let action_str = action_json.to_str().map_err(|e| {
        BridgeError::Action(serde_json::Error::io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            e.to_string(),
        )))
    })?;
    let action: crate::core::action::Action =
        serde_json::from_str(action_str).map_err(BridgeError::Action)?;
    let scope = store.inner.dispatch(&action);
    Ok(ffi::DispatchResult {
        state_json: serde_json::to_string(store.inner.state()).expect("state serialize"),
        scope: scope_to_string(scope),
    })
}

fn scope_to_string(scope: crate::core::reducer::Scope) -> String {
    match scope {
        crate::core::reducer::Scope::Settings => "settings".to_string(),
        crate::core::reducer::Scope::Viewport(tag) => format!("viewport.{}", tag),
        crate::core::reducer::Scope::Document => "document".to_string(),
        crate::core::reducer::Scope::Workspace => "workspace".to_string(),
        crate::core::reducer::Scope::NoOp => "noop".to_string(),
    }
}

fn decode_image_rgba8(path: &CxxString) -> Result<ffi::DecodedImage, BridgeError> {
    let path = path
        .to_str()
        .map_err(|error| BridgeError::ImagePath(error.to_string()))?;
    decode_image_rgba8_path(path)
}

fn decode_image_rgba8_path(path: &str) -> Result<ffi::DecodedImage, BridgeError> {
    let image = image::ImageReader::open(path)?
        .with_guessed_format()?
        .decode()?;
    if image.width() > 16_384 || image.height() > 16_384 {
        return Err(BridgeError::ImageTooLarge);
    }
    let rgba = image.into_rgba8();
    let (width, height) = rgba.dimensions();
    Ok(ffi::DecodedImage {
        pixels: rgba.into_raw(),
        width,
        height,
    })
}

fn build_single_image_render_plan(
    path: &CxxString,
    width: u32,
    height: u32,
) -> Result<ffi::SingleImageRenderPlan, BridgeError> {
    let path = path
        .to_str()
        .map_err(|error| BridgeError::ImagePath(error.to_string()))?;
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    path.hash(&mut hasher);
    width.hash(&mut hasher);
    height.hash(&mut hasher);
    let texture_id = hasher.finish().max(1);
    Ok(ffi::SingleImageRenderPlan {
        texture_id,
        canvas_w: i32::try_from(width).unwrap_or(i32::MAX),
        canvas_h: i32::try_from(height).unwrap_or(i32::MAX),
        fill_r: 37,
        fill_g: 37,
        fill_b: 37,
        fill_a: 255,
    })
}

#[allow(clippy::too_many_arguments)]
fn build_compare_render_plan(
    left_path: &CxxString,
    right_path: &CxxString,
    width: u32,
    height: u32,
    split: f32,
    horizontal: bool,
    magnifier_enabled: bool,
    guides_enabled: bool,
    paste_overlay_enabled: bool,
) -> Result<ffi::CanvasRenderPlan, BridgeError> {
    let left_path = left_path
        .to_str()
        .map_err(|error| BridgeError::ImagePath(error.to_string()))?;
    let right_path = right_path
        .to_str()
        .map_err(|error| BridgeError::ImagePath(error.to_string()))?;
    let inputs = crate::shared::rendering::plan_builder::PlanInputs {
        left_key: left_path.to_string(),
        right_key: right_path.to_string(),
        canvas_width: width,
        canvas_height: height,
        split,
        horizontal,
        features: crate::shared::rendering::plan_builder::FeatureToggles {
            magnifier: magnifier_enabled,
            guides: guides_enabled,
            capture: magnifier_enabled,
            filename: true,
            paste_overlay: paste_overlay_enabled,
        },
        ..Default::default()
    };
    Ok(built_to_ffi(
        &crate::shared::rendering::plan_builder::build_plan(&inputs),
    ))
}

fn ffi_inputs_to_rust(
    inputs: &ffi::CanvasPlanInputs,
) -> crate::shared::rendering::plan_builder::PlanInputs {
    use crate::shared::rendering::plan_builder::{
        DividerSpec, FeatureToggles, MagnifierSpec, OverlaySpec, PlanInputs, Rgba8,
    };
    PlanInputs {
        left_key: inputs.left_key.clone(),
        right_key: inputs.right_key.clone(),
        canvas_width: inputs.canvas_width,
        canvas_height: inputs.canvas_height,
        split: inputs.split,
        horizontal: inputs.horizontal,
        divider: DividerSpec {
            enabled: inputs.divider_enabled,
            thickness: inputs.divider_thickness,
        },
        magnifier: MagnifierSpec {
            capture_x: inputs.capture_x,
            capture_y: inputs.capture_y,
            magnifier_x: inputs.magnifier_x,
            magnifier_y: inputs.magnifier_y,
            radius: inputs.magnifier_radius,
            zoom: inputs.magnifier_zoom,
        },
        features: FeatureToggles {
            magnifier: inputs.feature_magnifier,
            guides: inputs.feature_guides,
            capture: inputs.feature_capture,
            filename: inputs.feature_filename,
            paste_overlay: inputs.feature_paste_overlay,
        },
        left_label: if inputs.left_label.is_empty() {
            None
        } else {
            Some(inputs.left_label.clone())
        },
        right_label: if inputs.right_label.is_empty() {
            None
        } else {
            Some(inputs.right_label.clone())
        },
        fill: Rgba8 {
            r: inputs.fill_r,
            g: inputs.fill_g,
            b: inputs.fill_b,
            a: inputs.fill_a,
        },
        overlay: if inputs.overlay_enabled {
            Some(OverlaySpec {
                border_color: if inputs.overlay_has_border_color {
                    Some(Rgba8 {
                        r: inputs.overlay_border_r,
                        g: inputs.overlay_border_g,
                        b: inputs.overlay_border_b,
                        a: inputs.overlay_border_a,
                    })
                } else {
                    None
                },
                border_width: inputs.overlay_border_width,
                channel_mode: inputs.overlay_channel_mode,
                diff_mode: inputs.overlay_diff_mode,
                interp_mode: inputs.overlay_interp_mode,
            })
        } else {
            None
        },
    }
}

fn build_canvas_render_plan(inputs: &ffi::CanvasPlanInputs) -> ffi::CanvasRenderPlan {
    let rust_inputs = ffi_inputs_to_rust(inputs);
    built_to_ffi(&crate::shared::rendering::plan_builder::build_plan(
        &rust_inputs,
    ))
}

fn build_canvas_render_plan_json(inputs: &ffi::CanvasPlanInputs) -> Result<String, BridgeError> {
    let rust_inputs = ffi_inputs_to_rust(inputs);
    let built = crate::shared::rendering::plan_builder::build_plan(&rust_inputs);
    serde_json::to_string(&built).map_err(|e| BridgeError::Internal(e.to_string()))
}

fn built_to_ffi(plan: &crate::shared::rendering::plan_builder::BuiltPlan) -> ffi::CanvasRenderPlan {
    ffi::CanvasRenderPlan {
        texture1_id: plan.texture1_id,
        texture2_id: plan.texture2_id,
        canvas_w: plan.canvas_w,
        canvas_h: plan.canvas_h,
        split: plan.split,
        horizontal: plan.horizontal,
        divider_enabled: plan.divider_enabled,
        divider_thickness: plan.divider_thickness,
        magnifier_enabled: plan.magnifier_enabled,
        capture_x: plan.capture_x,
        capture_y: plan.capture_y,
        magnifier_x: plan.magnifier_x,
        magnifier_y: plan.magnifier_y,
        magnifier_radius: plan.magnifier_radius,
        magnifier_zoom: plan.magnifier_zoom,
        guides_enabled: plan.guides_enabled,
        capture_enabled: plan.capture_enabled,
        filename_enabled: plan.filename_enabled,
        paste_overlay_enabled: plan.paste_overlay_enabled,
        left_label: plan.left_label.clone(),
        right_label: plan.right_label.clone(),
        fill_r: plan.fill_r,
        fill_g: plan.fill_g,
        fill_b: plan.fill_b,
        fill_a: plan.fill_a,
    }
}

fn resolve_stack_order(role: i32) -> ffi::StackOrder {
    let order = crate::ui::canvas::stacking::resolve(role);
    ffi::StackOrder {
        phase: order.phase,
        priority: order.priority,
    }
}

fn letterbox_rect(widget_w: i32, widget_h: i32, canvas_w: i32, canvas_h: i32) -> ffi::RectI32 {
    let r = crate::ui::canvas::plan_keys::letterbox_rect(widget_w, widget_h, canvas_w, canvas_h);
    ffi::RectI32 {
        x: r.x,
        y: r.y,
        w: r.w,
        h: r.h,
    }
}

fn bounds_from_ffi(
    value: &ffi::NormalizedBoundsF64,
) -> crate::ui::canvas::virtual_layout::NormalizedBounds {
    crate::ui::canvas::virtual_layout::NormalizedBounds {
        x_min: value.x_min,
        x_max: value.x_max,
        y_min: value.y_min,
        y_max: value.y_max,
    }
}

fn bounds_to_ffi(
    value: crate::ui::canvas::virtual_layout::NormalizedBounds,
) -> ffi::NormalizedBoundsF64 {
    ffi::NormalizedBoundsF64 {
        x_min: value.x_min,
        x_max: value.x_max,
        y_min: value.y_min,
        y_max: value.y_max,
    }
}

fn resolve_virtual_canvas_layout(
    requirements: &[ffi::NormalizedBoundsF64],
    content_bounds: &ffi::NormalizedBoundsF64,
) -> ffi::VirtualCanvasLayoutF64 {
    let requirements = requirements.iter().map(bounds_from_ffi).collect::<Vec<_>>();
    let layout = crate::ui::canvas::virtual_layout::resolve_virtual_canvas_layout(
        &requirements,
        bounds_from_ffi(content_bounds),
    );
    ffi::VirtualCanvasLayoutF64 {
        canvas_bounds: bounds_to_ffi(layout.canvas_bounds),
        content_bounds: bounds_to_ffi(layout.content_bounds),
    }
}

fn resolve_virtual_canvas_padding(
    layout: &ffi::VirtualCanvasLayoutF64,
    base_width: i32,
    base_height: i32,
) -> ffi::PaddingI32 {
    let layout = crate::ui::canvas::virtual_layout::VirtualCanvasLayout {
        canvas_bounds: bounds_from_ffi(&layout.canvas_bounds),
        content_bounds: bounds_from_ffi(&layout.content_bounds),
    };
    let (left, right, top, bottom) = layout.resolve_padding_pixels(base_width, base_height);
    ffi::PaddingI32 {
        left,
        right,
        top,
        bottom,
    }
}

fn compute_content_layout(
    target_width: i32,
    target_height: i32,
    image_width: i32,
    image_height: i32,
    stretch: bool,
) -> ffi::ContentLayoutI32 {
    let layout = crate::ui::canvas::virtual_layout::compute_content_layout(
        target_width,
        target_height,
        image_width,
        image_height,
        stretch,
    );
    ffi::ContentLayoutI32 {
        canvas_width: layout.canvas_width,
        canvas_height: layout.canvas_height,
        content_x: layout.content_x,
        content_y: layout.content_y,
        content_width: layout.content_width,
        content_height: layout.content_height,
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::field_reassign_with_default)]

    use super::*;
    use image::{Rgba, RgbaImage};

    #[test]
    fn stateful_store_dispatches_through_bridge_helpers() {
        let mut store = new_store();
        cxx::let_cxx_string!(action = r#"{"SetTheme":"dark"}"#);

        let result = dispatch_store(&mut store, &action).expect("dispatch");

        assert_eq!(result.scope, "settings");
        assert!(result.state_json.contains(r#""theme":"dark""#));
        assert!(store_state_json(&store).contains(r#""theme":"dark""#));
    }

    #[test]
    fn image_decode_returns_rgba_pixels() {
        let path =
            std::env::temp_dir().join(format!("imgsli-core-decode-{}.png", std::process::id()));
        RgbaImage::from_pixel(2, 1, Rgba([10, 20, 30, 40]))
            .save(&path)
            .expect("write fixture");

        let decoded = decode_image_rgba8_path(path.to_str().expect("utf-8 path")).expect("decode");

        assert_eq!((decoded.width, decoded.height), (2, 1));
        assert_eq!(decoded.pixels, vec![10, 20, 30, 40, 10, 20, 30, 40]);
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn single_image_plan_is_stable_and_non_empty() {
        cxx::let_cxx_string!(path = "/tmp/example.png");

        let first = build_single_image_render_plan(&path, 640, 480).expect("plan");
        let second = build_single_image_render_plan(&path, 640, 480).expect("plan");

        assert_eq!(first.texture_id, second.texture_id);
        assert_ne!(first.texture_id, 0);
        assert_eq!((first.canvas_w, first.canvas_h), (640, 480));
        assert_eq!(
            (first.fill_r, first.fill_g, first.fill_b, first.fill_a),
            (37, 37, 37, 255)
        );
    }

    #[test]
    fn compare_plan_clamps_split_and_keeps_distinct_textures() {
        cxx::let_cxx_string!(left = "/tmp/left.png");
        cxx::let_cxx_string!(right = "/tmp/right.png");
        let plan =
            build_compare_render_plan(&left, &right, 800, 600, 2.0, false, true, true, false)
                .expect("compare plan");
        assert_eq!(plan.split, 1.0);
        assert_ne!(plan.texture1_id, plan.texture2_id);
        assert!(plan.magnifier_enabled);
        assert!(plan.guides_enabled);
    }
}

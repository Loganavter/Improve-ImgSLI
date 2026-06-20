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
    inner: crate::store::Store,
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

    pub struct DecodedImage {
        pub pixels: Vec<u8>,
        pub width: u32,
        pub height: u32,
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
        fn build_single_image_render_plan(
            path: &CxxString,
            width: u32,
            height: u32,
        ) -> Result<SingleImageRenderPlan>;
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
        fn resolve_stack_order(role: i32) -> StackOrder;

        fn letterbox_rect(widget_w: i32, widget_h: i32, canvas_w: i32, canvas_h: i32) -> RectI32;
    }
}

fn core_version() -> String {
    crate::version().to_string()
}

fn core_greeting(name: &str) -> String {
    format!("ImgSLI core {} says hello, {}", crate::version(), name)
}

fn settings_default_json() -> String {
    crate::settings::SettingsState::default().to_json_pretty()
}

fn settings_roundtrip_json(input: &str) -> Result<String, crate::settings::SettingsError> {
    let s = crate::settings::SettingsState::from_json(input)?;
    Ok(s.to_json_pretty())
}

fn settings_dialog_default_json() -> String {
    crate::settings_dialog::SettingsDialogData::default().to_json_pretty()
}

fn settings_dialog_normalize_json(input: &str) -> Result<String, serde_json::Error> {
    let mut d = crate::settings_dialog::SettingsDialogData::from_json(input)?;
    d.normalize();
    Ok(d.to_json_pretty())
}

fn settings_dialog_diff_json(prev: &str, next: &str) -> Result<String, serde_json::Error> {
    crate::settings_dialog::diff_json(prev, next)
}

fn state_default_json() -> String {
    serde_json::to_string_pretty(&crate::state::AppState::default()).expect("state serialize")
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
    let mut state: crate::state::AppState =
        serde_json::from_str(state_str).map_err(BridgeError::State)?;
    let action: crate::action::Action =
        serde_json::from_str(action_str).map_err(BridgeError::Action)?;
    let scope = crate::reducer::apply(&mut state, &action);
    let scope_str = match scope {
        crate::reducer::Scope::Settings => "settings".to_string(),
        crate::reducer::Scope::Viewport(tag) => format!("viewport.{}", tag),
        crate::reducer::Scope::Document => "document".to_string(),
        crate::reducer::Scope::Workspace => "workspace".to_string(),
        crate::reducer::Scope::NoOp => "noop".to_string(),
    };
    Ok(ffi::DispatchResult {
        state_json: serde_json::to_string(&state).expect("state serialize"),
        scope: scope_str,
    })
}

fn new_store() -> Box<RustStore> {
    Box::new(RustStore {
        inner: crate::store::Store::new(),
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
    let action: crate::action::Action =
        serde_json::from_str(action_str).map_err(BridgeError::Action)?;
    let scope = store.inner.dispatch(&action);
    Ok(ffi::DispatchResult {
        state_json: serde_json::to_string(store.inner.state()).expect("state serialize"),
        scope: scope_to_string(scope),
    })
}

fn scope_to_string(scope: crate::reducer::Scope) -> String {
    match scope {
        crate::reducer::Scope::Settings => "settings".to_string(),
        crate::reducer::Scope::Viewport(tag) => format!("viewport.{}", tag),
        crate::reducer::Scope::Document => "document".to_string(),
        crate::reducer::Scope::Workspace => "workspace".to_string(),
        crate::reducer::Scope::NoOp => "noop".to_string(),
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

fn stable_texture_id(path: &str, width: u32, height: u32) -> u64 {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    path.hash(&mut hasher);
    width.hash(&mut hasher);
    height.hash(&mut hasher);
    hasher.finish().max(1)
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
    Ok(ffi::CanvasRenderPlan {
        texture1_id: stable_texture_id(left_path, width, height),
        texture2_id: stable_texture_id(right_path, width, height),
        canvas_w: i32::try_from(width).unwrap_or(i32::MAX),
        canvas_h: i32::try_from(height).unwrap_or(i32::MAX),
        split: split.clamp(0.0, 1.0),
        horizontal,
        divider_enabled: true,
        divider_thickness: 2.0,
        magnifier_enabled,
        capture_x: 0.35,
        capture_y: 0.5,
        magnifier_x: 0.7,
        magnifier_y: 0.5,
        magnifier_radius: 0.16,
        magnifier_zoom: 2.0,
        guides_enabled,
        capture_enabled: magnifier_enabled,
        filename_enabled: true,
        paste_overlay_enabled,
        left_label: std::path::Path::new(left_path)
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or(left_path)
            .to_string(),
        right_label: std::path::Path::new(right_path)
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or(right_path)
            .to_string(),
        fill_r: 37,
        fill_g: 37,
        fill_b: 37,
        fill_a: 255,
    })
}

fn resolve_stack_order(role: i32) -> ffi::StackOrder {
    let order = crate::stacking::resolve(role);
    ffi::StackOrder {
        phase: order.phase,
        priority: order.priority,
    }
}

fn letterbox_rect(widget_w: i32, widget_h: i32, canvas_w: i32, canvas_h: i32) -> ffi::RectI32 {
    let r = crate::plan_keys::letterbox_rect(widget_w, widget_h, canvas_w, canvas_h);
    ffi::RectI32 {
        x: r.x,
        y: r.y,
        w: r.w,
        h: r.h,
    }
}

#[cfg(test)]
mod tests {
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

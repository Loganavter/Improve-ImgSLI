//! PyO3 bindings for `imgsli_core`.
//!
//! Purpose: parallel-validation during Phase 1. Each Python module replaced
//! by the Rust core gets a thin wrapper here so the live Python app can run
//! against either implementation.
//!
//! Surface (Phase 1A):
//! - `version() -> str`
//! - `settings_default_json() -> str`
//! - `settings_roundtrip_json(s: str) -> str`
//! - `dispatch(state_json: str, action_json: str) -> tuple[str, str]`
//! - `letterbox_rect(widget_w, widget_h, canvas_w, canvas_h) -> tuple[int, int, int, int]`
//! - `ImagePairCache` — opaque LRU cache, `put` / `get` / `clear` / `__len__`.
//!
//! Build: `pip install maturin && maturin develop` (run from this directory).

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;

use imgsli_core::{
    core::action::Action,
    core::reducer::{apply, Scope},
    core::state::AppState,
    plugins::settings::dialog::{
        is_interpolation_conflict as rust_interp_conflict, SettingsDialogData,
    },
    plugins::settings::model::SettingsState,
    ui::canvas::image_cache::{CachedPair, ImagePairCache, PairKey},
    ui::canvas::plan_keys::letterbox_rect as rust_letterbox_rect,
    version as core_version,
};

#[pyfunction]
fn version() -> &'static str {
    core_version()
}

#[pyfunction]
fn settings_default_json() -> String {
    SettingsState::default().to_json_pretty()
}

#[pyfunction]
fn settings_roundtrip_json(input: &str) -> PyResult<String> {
    let s = SettingsState::from_json(input)
        .map_err(|e| PyValueError::new_err(format!("invalid settings json: {e}")))?;
    Ok(s.to_json_pretty())
}

#[pyfunction]
fn state_default_json() -> String {
    serde_json::to_string_pretty(&AppState::default()).expect("state serialize")
}

#[pyfunction]
fn settings_dialog_default_json() -> String {
    SettingsDialogData::default().to_json_pretty()
}

#[pyfunction]
fn settings_dialog_normalize_json(input: &str) -> PyResult<(String, usize)> {
    let mut d = SettingsDialogData::from_json(input)
        .map_err(|e| PyValueError::new_err(format!("invalid dialog json: {e}")))?;
    let changes = d.normalize();
    Ok((d.to_json_pretty(), changes))
}

#[pyfunction]
fn interpolation_conflict(main_method: &str, optimization_method: &str) -> bool {
    rust_interp_conflict(main_method, optimization_method)
}

/// Apply one action to a state, both serialized as JSON. Returns
/// `(new_state_json, scope_string)`.
#[pyfunction]
fn dispatch(state_json: &str, action_json: &str) -> PyResult<(String, String)> {
    let mut state: AppState = serde_json::from_str(state_json)
        .map_err(|e| PyValueError::new_err(format!("invalid state: {e}")))?;
    let action: Action = serde_json::from_str(action_json)
        .map_err(|e| PyValueError::new_err(format!("invalid action: {e}")))?;
    let scope = apply(&mut state, &action);
    let scope_str = match scope {
        Scope::Settings => "settings".to_string(),
        Scope::Viewport(tag) => format!("viewport.{tag}"),
        Scope::Document => "document".to_string(),
        Scope::Workspace => "workspace".to_string(),
        Scope::NoOp => "noop".to_string(),
    };
    let json = serde_json::to_string(&state).expect("state serialize");
    Ok((json, scope_str))
}

#[pyfunction]
fn letterbox_rect(
    widget_w: i32,
    widget_h: i32,
    canvas_w: i32,
    canvas_h: i32,
) -> (i32, i32, i32, i32) {
    let r = rust_letterbox_rect(widget_w, widget_h, canvas_w, canvas_h);
    (r.x, r.y, r.w, r.h)
}

#[pyclass(name = "ImagePairCache")]
struct PyImagePairCache {
    inner: ImagePairCache,
}

#[pymethods]
impl PyImagePairCache {
    #[new]
    fn new(capacity: usize) -> PyResult<Self> {
        if capacity == 0 {
            return Err(PyValueError::new_err("capacity must be > 0"));
        }
        Ok(Self {
            inner: ImagePairCache::new(capacity),
        })
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }

    fn clear(&mut self) {
        self.inner.clear();
    }

    /// Insert a pair. `mtime1_ns` / `mtime2_ns` accept `int`; pass `0` if
    /// unknown.
    #[pyo3(signature = (path1, path2, mtime1_ns, mtime2_ns, resolution_limit, width, height, bytes_left, bytes_right))]
    #[allow(clippy::too_many_arguments)]
    fn put(
        &mut self,
        path1: String,
        path2: String,
        mtime1_ns: i128,
        mtime2_ns: i128,
        resolution_limit: i32,
        width: u32,
        height: u32,
        bytes_left: Vec<u8>,
        bytes_right: Vec<u8>,
    ) {
        self.inner.put(
            PairKey {
                path1,
                path2,
                mtime1_ns,
                mtime2_ns,
                resolution_limit,
            },
            CachedPair {
                width,
                height,
                bytes_left,
                bytes_right,
            },
        );
    }

    /// Look up. Raises KeyError on miss so the Python side can mirror the
    /// `OrderedDict[key]` access pattern.
    fn get(
        &mut self,
        path1: &str,
        path2: &str,
        mtime1_ns: i128,
        mtime2_ns: i128,
        resolution_limit: i32,
    ) -> PyResult<(u32, u32, Vec<u8>, Vec<u8>)> {
        let key = PairKey {
            path1: path1.to_string(),
            path2: path2.to_string(),
            mtime1_ns,
            mtime2_ns,
            resolution_limit,
        };
        match self.inner.get(&key) {
            Some(v) => Ok((v.width, v.height, v.bytes_left, v.bytes_right)),
            None => Err(PyKeyError::new_err("image pair not in cache")),
        }
    }
}

#[pymodule]
fn imgsli_core_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(settings_default_json, m)?)?;
    m.add_function(wrap_pyfunction!(settings_roundtrip_json, m)?)?;
    m.add_function(wrap_pyfunction!(state_default_json, m)?)?;
    m.add_function(wrap_pyfunction!(settings_dialog_default_json, m)?)?;
    m.add_function(wrap_pyfunction!(settings_dialog_normalize_json, m)?)?;
    m.add_function(wrap_pyfunction!(interpolation_conflict, m)?)?;
    m.add_function(wrap_pyfunction!(dispatch, m)?)?;
    m.add_function(wrap_pyfunction!(letterbox_rect, m)?)?;
    m.add_class::<PyImagePairCache>()?;
    Ok(())
}

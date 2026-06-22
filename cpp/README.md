# cpp/ — C++ Qt + Rust Core Migration Workspace

This directory holds the in-progress C++/Rust port of ImgSLI.
The Python application under `../src/` remains the production build until the
remaining product UI and packaging cutover work is complete.

See [docs/dev/CPP_RUST_MIGRATION.md](../docs/dev/CPP_RUST_MIGRATION.md) for the plan.

## Layout

```
cpp/
  Cargo.toml              cargo workspace
  CMakeLists.txt          top-level CMake build (Qt6 + Corrosion)
  app/                    C++ Qt application
    main.cpp              Phase 2 shell / open workflow
    canvas_widget.*       Phase 3 QRhi plan executor
    shaders/              qsb-compiled canvas shaders
    CMakeLists.txt
  toolkit/                C++ SLI baseline controls + theme tokens
  core/                   imgsli_core (pure-logic Rust)
    Cargo.toml
    build.rs
    src/{lib,bridge,domain,settings,state,action,reducer,store,plan,plan_keys,hit_test,image_cache}.rs
  core_py/                imgsli_core_py (PyO3 bindings — parallel validation)
    Cargo.toml
    pyproject.toml
    src/lib.rs
  include/imgsli/         frozen contract headers (Phase 0)
```

## Build

```sh
cd cpp
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j
./build/app/imgsli_app
```

Cargo is invoked transparently via Corrosion during the CMake build.

## Current phase

**Phase 5 service layer complete; product cutover in progress.** Phase 1A
delivered the pure-logic Rust core (state,
reducer, store, plan
POD, plan keys, hit test, image cache, analysis) with 104 cargo tests, cxx bridge
exercised from C++, PyO3 wrapper for parallel validation.

Phase 1B is now unblocked by the Phase 3 feature contracts and remains active
cutover work — see
[`../docs/dev/CPP_RUST_MIGRATION.md`](../docs/dev/CPP_RUST_MIGRATION.md).

The C++ shell now owns a `QObject` Store wrapper around a stateful Rust
`Store`. Qt dispatches JSON-encoded actions through the Rust reducer and
receives `stateChanged(stateJson, scope)` on the Qt event-loop thread.
The shell can also open a supported image, decode it to RGBA8 in Rust,
transfer the pixels through `cxx`, display them in Qt, and dispatch the
selected path into the Rust document state.

Phase 3 adds a Vulkan `QRhiWidget`, build-time QSB shaders, Rust-produced
single/two-image render plans, semantic stacking, a C++ pass registry, static
feature contracts, and interactive divider/magnifier/guides. For an
automated/manual smoke without the file dialog:

```sh
./build/app/imgsli_app --open /path/to/image.png
```

Two-image comparison:

```sh
./build/app/imgsli_app --compare left.png right.png
```

Workspace sessions can be recreated from a Python-compatible blueprint. An
optional `comparison` object restores the visual state; relative image paths
are resolved beside the JSON file:

```json
{
  "session_type": "image_compare",
  "plugin_name": "comparison",
  "title": "Review",
  "resource_namespaces": [{"namespace": "comparison"}],
  "metadata_defaults": {"plugin": "comparison"},
  "comparison": {
    "left_path": "left.png",
    "right_path": "right.png",
    "split": 0.4,
    "horizontal": false,
    "magnifier": true,
    "guides": true,
    "paste_overlay": false,
    "diff_mode": "off",
    "channel_mode": "RGB"
  }
}
```

```sh
./build/app/imgsli_app --session-blueprint session.json
```

Contract and benchmark checks:

```sh
ctest --test-dir build --output-on-failure
./build/app/imgsli_app --compare left.png right.png --benchmark-frames 300
```

The registered Multi Compare tab now owns the primary comparison controls
through `ComparisonController`. The Export tab saves the current QRhi canvas
through the export plugin:

```sh
./build/app/imgsli_app --compare left.png right.png --snapshot output.png
```

Still export now reallocates the QRhi target to the render-plan dimensions
before readback. The Video Editor tab has real project/timeline controls and
an asynchronous FFmpeg lifecycle; its smoke path is:

```sh
./build/app/imgsli_app \
  --video-transcode input.mp4 output.mp4 \
  --video-size 1920x1080 --video-fps 60
```

The Analysis plugin computes PSNR, local-window SSIM, Highlight, Grayscale,
Edges, SSIM maps, and RGB/R/G/B/L channel views in Rust. Work runs
asynchronously in C++ and feeds the shared canvas/export path:

```sh
./build/app/imgsli_app \
  --compare left.png right.png \
  --diff ssim --channel RGB \
  --analysis-snapshot ssim-map.png
```

Help and Layout are also registered C++ plugins. Help discovers localized
Markdown under `src/resources/help/`, while Layout applies beginner,
advanced, expert, and minimal visibility policies immediately after settings
changes.

The remaining cutover work includes arbitrary-size dedicated offscreen
export, the full multi-compare grid/workflow, snapshot preview/keyframing in
the video editor, Phase 1B typed feature state/plan building, cross-platform
CI, and native packaging.

Current checks:

```sh
cargo test --workspace                                      # 104 passed
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
ctest --test-dir build --output-on-failure
```

### Building the PyO3 module

```sh
cd cpp/core_py
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 maturin develop
python -c "import imgsli_core_py as m; print(m.version())"
```

Forward-compat flag is only needed because the system CPython is newer than
PyO3's pinned support window.

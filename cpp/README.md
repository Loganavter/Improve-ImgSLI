# cpp/ — C++ Qt + Rust Core Migration Workspace

This directory holds the in-progress C++/Rust port of ImgSLI.
The Python application under `../src/` remains the production build until late Phase 3.

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

**Phase 3 complete.** Phase 1A delivered the pure-logic Rust core (state,
reducer, store, plan
POD, plan keys, hit test, image cache) with 55 cargo tests, cxx bridge
exercised from C++, PyO3 wrapper for parallel validation.

Phase 1B is deferred to Phase 3 — see
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

Contract and benchmark checks:

```sh
ctest --test-dir build --output-on-failure
./build/app/imgsli_app --compare left.png right.png --benchmark-frames 300
```

### Building the PyO3 module

```sh
cd cpp/core_py
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 maturin develop
python -c "import imgsli_core_py as m; print(m.version())"
```

Forward-compat flag is only needed because the system CPython is newer than
PyO3's pinned support window.

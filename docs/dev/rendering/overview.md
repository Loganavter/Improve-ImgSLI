# Overview

The render backend is QRhi. This documentation states the target model the
architecture should guarantee, not necessarily a line-by-line audit of every
current file — see [Doc status](#doc-status) at the end.

**Core idea**: a feature doesn't handle zoom, pan, coordinate transforms, raw
Qt events, or serialization — the infrastructure does. See
[Feature Isolation Model](../CONTRACTS.md#feature-isolation-model-the-abstraction).

## Quick Start

1. Copy `src/tabs/image_compare/canvas/features/_template/` to
   `src/tabs/image_compare/canvas/features/<your_feature>/`
2. Rename `_template` to your feature name in `widget.py` (`name=` field)
3. Add your logic
4. Done — all registries auto-discover it

No central files need editing. Packages starting with `_` are excluded from
auto-discovery.

## Top-level Split

### 1. Canvas infrastructure (`src/ui/canvas_infra/`)

The framework layer. Owns scene contracts, feature registries, scene
builder/composer, apply pipeline, hit-test routing, viewport contracts,
zoom/pan/split state and math, render-pass scene contracts. Does not own
feature business logic. Shared across every tab — not tab-owned (see
[Package Structure](package-structure.md) below).

Key files:
- `scene/feature_contract.py` — `CanvasSceneFeature`
- `scene/widget_contract.py` — `CanvasWidgetFeature`, `CanvasFeatureProperty`
- `scene/registry.py` — the one per-tab `CanvasFeatureRegistry`: auto-discovers
  `manifest.py` (fallback `feature.py` / `widget.py`) and `passes.py`, for every
  package registered through `register_canvas_feature_package(tab_type, package)`
- `scene/pass_contract.py` — `CanvasRenderPass`, `SceneVisibility`, single-preview helpers
- `scene/property_access.py` — shared property read/write/persistence
- `scene/pipeline.py` — ordered build/apply/hit-test pipelines
- `scene/builder.py` — builds `CanvasSceneGraph`
- `scene/apply.py` — applies built scene to canvas runtime
- `scene/hit_test.py` — routes hit-testing through registered features
- `scene/stacking_policy.py` — `CanvasStackRole`, central ordering tables
- `viewport/contract.py` — viewport feature contract
- `viewport/state.py` — viewport runtime state accessors
- `viewport/zoom.py` — zoom/pan/split implementation

### 2. Canvas features (`src/tabs/<tab>/canvas/features/<name>/`)

Editor-facing canvas features (magnifier, divider, guides, capture,
filename_overlay). Each keeps its scene logic, state logic, and
widget/reducer integration in its own folder, owned by the tab that
registers the feature package (currently `image_compare` and `multi_compare`).

### 3. Canvas presentation (`src/ui/canvas_presentation/`)

Not a feature home. Used for live store snapshots, render/export-facing
store transformation, canvas surface integration. Feature-specific helpers
should not live here.

### 4. QRhi canvas renderer (`src/tabs/image_compare/canvas/`, backend bits under `src/ui/canvas_infra/rhi/`)

Renderer backend, not a feature home. Owns QRhi resource setup, buffer/texture
upload/readback, renderer-facing consumption of the render scene/runtime
context, base canvas shader source, feature render-pass discovery and
dispatch loop.

Shader ownership:
- `canvas/shaders/` — compiled `.qsb` sources (base_array, label_downsample,
  etc.) loaded by `rhi_renderer`/`load_qshader`; legacy GLSL-string containers
  (`shader_sources/`) were removed in the 2026-08 mass-reduction pass
- Feature shaders live inside `canvas/features/<name>/` (`shaders/*.qsb`, or
  `shaders/qrhi/*.qsb` for a multi-shader feature like the magnifier), not in
  the generic canvas renderer.

## Shader compilation

Shaders are authored as GLSL (`*.vert` / `*.frag`) and baked into committed
`*.qsb` packs by `src/devtools/compile_shaders.py`. Runtime never runs `qsb` —
only Qt reads the packs — so **the bake host, not the app host, owns the
toolchain requirement**.

```bash
python3 src/devtools/compile_shaders.py                   # (re)bake every .qsb
python3 src/devtools/compile_shaders.py --check           # mtime freshness + variant audit
python3 src/devtools/compile_shaders.py --verify-variants # per-file variant list
```

Every pack must contain a compiled `DxbcShader` v50 variant. The D3D11 backend
looks up `{QShader::DxbcShader, 50}` first and only falls back to shipping HLSL
source compiled on the fly with `D3DCompile`; an HLSL-only pack therefore pays a
shader compile on every cold pipeline creation (measured ~4–4.5 s per canvas),
while a baked pack just loads the bytecode. `compile_shaders.py` always passes
qsb's `-c`/`--fxc` and refuses to keep a pack whose DXBC variant is missing —
`--check` and `--verify-variants` both fail on it, so an HLSL-only pack cannot
land silently.

### Bake-host toolchain (fxc)

qsb shells out to `fxc` (found on `PATH`) whenever `-c` is used, so the bake
host needs Microsoft's HLSL compiler: **fxc.exe from the Windows SDK 8.1+ x64**
(no, the app host does not need it — only the machine that regenerates packs).

- **Windows**: install the SDK and put `…\Windows Kits\10\bin\<ver>\x64` on
  `PATH`.
- **Linux**: run that `fxc.exe` under wine behind a small shim named `fxc` on
  `PATH`. Recipe used here:

  ```bash
  # 1) once: create the wine prefix (≈380 MB, ~10 s)
  WINEPREFIX=$PWD/.agent/wine WINEDEBUG=-all winecfg -v >/dev/null 2>&1 || true

  # 2) shim: qsb passes unix paths, fxc wants drive letters
  mkdir -p .agent/tools/bin
  cat > .agent/tools/bin/fxc <<'SH'
  #!/bin/bash
  out=()
  for a in "$@"; do
    case "$a" in
      /nologo|/E|/T|/Fo|/Gfa|/Gfp|/O3) out+=("$a"); continue;;
    esac
    if [[ "$a" == /* ]]; then out+=("Z:$a"); else out+=("$a"); fi
  done
  WINEDEBUG=-all exec wine "$(dirname "$0")/../fxc.exe" "${out[@]}"
  SH
  chmod +x .agent/tools/bin/fxc

  # 3) bake
  WINEPREFIX=$PWD/.agent/wine WINEDEBUG=-all \
    PATH=$PWD/.agent/tools/bin:$PATH \
    python3 src/devtools/compile_shaders.py
  ```

Two failure modes worth knowing:

- **No fxc on `PATH`** — the script exits with the toolchain requirement spelled
  out; it never falls back to an HLSL-only bake.
- **qsb's 30 s external-compiler timeout** — qsb kills the fxc child after 30 s
  and, unhelpfully, still exits **0** with no DXBC variant in the pack. Never
  trust qsb's exit code: the script re-reads every pack it just wrote and fails
  the run, naming the file, so the symptom is a bake error rather than a silent
  runtime regression.

`.qsb` files are build products of this script: always regenerate them, never
hand-edit them.

### Exemptions (pinned, visible)

`DXBC_EXEMPT` in `compile_shaders.py` is the only way to accept a pack without a
DXBC variant, and it is deliberately awkward: each entry needs a repo-relative
path, a **reason** and a **content pin** (`<bytes>:<sha256[:16]>`). Then

- `--verify-variants` prints `EXEMPT <path> <reason>` and does not count that
  file as missing, while every unlisted pack still has to carry `DxbcShader`
  v50;
- `--check` fails when an exempted pack's bytes no longer match the pin — the
  reason has to be re-read and re-justified instead of being silently inherited;
- a full bake skips exempted packs and says so per file.

The map is empty by default. An entry means "this one pack still pays a runtime
`D3DCompile` until someone re-bakes it on a host where the bake works", so the
reason must name the blocker and the host that can clear it — e.g. a shader that
fxc cannot compile through qsb's 30 s child timeout can still be baked from a
native Windows SDK shell with plain
`python src/devtools/compile_shaders.py` (fxc already on `PATH`).

The one entry currently in the map is
`src/tabs/image_compare/canvas/features/magnifier/shaders/qrhi/mag.frag.qsb`
(pinned `23874:9fe33318b6a18cc9`): fxc 8.1 under wine needs >5 min on that HLSL
while qsb kills the compiler at 30 s, so **the magnifier's fragment pass keeps
paying a runtime `D3DCompile` on D3D11 until it is re-baked** — the other 32
packs (base canvas, overlay, magnifier's other passes, …) load bytecode. To
clear it, on a Windows host with Windows SDK 10.x `fxc.exe` on `PATH`:

```bash
# 1) delete the mag.frag entry from DXBC_EXEMPT in src/devtools/compile_shaders.py
python src/devtools/compile_shaders.py
python src/devtools/compile_shaders.py --verify-variants   # rc 0, no EXEMPT line
```

## Examples

- `magnifier/` — largest: scene, state, store, mode, widget, geometry, workers
- `divider/` — small feature
- `guides/` — overlay with owner-state, actions, settings/keyframe properties, render payload
- `capture/` — small overlay with settings/keyframe properties and render payload
- `_template/` — copyable starter template
- `canvas_infra/viewport/` — infrastructure (not a consumer feature)

## Doc status

This documentation states the target model. It does not claim the current
codebase fully complies with it in every corner — most notably, whether every
base-image-anchored pass correctly treats viewport-formula output as final,
and whether every pipeline sets its alpha blend factors explicitly rather
than relying on defaults (see [render-pass-contract.md](render-pass-contract.md)).
A line-by-line audit against this documentation is a separate, ongoing task.
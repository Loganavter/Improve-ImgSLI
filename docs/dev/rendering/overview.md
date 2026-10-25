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
  (`QProcess::waitForFinished()` with no argument) and, unhelpfully, still exits
  **0** with no DXBC variant in the pack. Never trust qsb's exit code: the script
  re-reads every pack it just wrote. When the variant is missing it does **not**
  give up — it takes the slow path below, and only a pack that fails both ways
  becomes a bake error.

### Slow path (shaders that outgrow qsb's window)

Some HLSL explodes under fxc's unroller. Measured on the magnifier fragment
shader (nested EWA sampling loops): `fxc` 8.1 needs **>20 min and rising** on the
generated HLSL, `/Od` and `/Gfp` do not help, and loop bounds made dynamic do
not either — while qsb would kill it at 30 s regardless. The script therefore
falls back, automatically and per pack:

1. qsb has already written the **HLSL** variant; extract it with
   `qsb -x hlsl,50 -o shader.hlsl pack.qsb`;
2. insert `[loop]` before every `for`/`while` — an unroll guard. Semantics are
   unchanged; the same shader then compiles in **5.5 s** instead of >20 min;
3. run `fxc /nologo /E main /T ps_5_0 /Fo shader.dxbc shader.hlsl` directly
   (900 s budget, no qsb window);
4. add the bytecode back with qsb's own
   `qsb pack.qsb -r dxbc,50,shader.dxbc` — the documented "add a target that was
   not present before" mode. The pack is never byte-edited;
5. re-read the pack and require `DxbcShader` v50, exactly like the fast path.

The run prints a `slow-path:` line with the measured fxc time and hint count.
The stored bytecode comes from the same fxc, so this is a scheduling workaround
for qsb's fixed 30 s window, not a different compiler.


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

The map is empty by default — and it is currently **empty**: the only entry it
ever held (the magnifier fragment pack) is now baked by the slow path above. An
entry means "this one pack still pays a runtime `D3DCompile` until someone
re-bakes it on a host where the bake works", so the reason must name the blocker
and the host that can clear it, and it must also say why the slow path did not
apply.

Do not reach for an exemption while the slow path can run: the slow path was
added precisely because the magnifier pack looked un-bakeable on this host
(qsb's 30 s window) and turned out to need only an unroll guard.

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
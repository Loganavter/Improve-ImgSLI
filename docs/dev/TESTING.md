# Testing

Guide to test layout, how to run tests, and how to write new ones.

## Running tests

```bash
# from the repository root
pytest                                   # full suite (top-level tests/ + all src/tabs/*/tests/)
pytest tests/contracts                   # cross-cutting architectural contracts only
./launcher.sh test tests/contracts -q    # same, via launcher (preferred for agents)
pytest src/tabs/image_compare/tests      # image_compare tab tests only
pytest src/tabs/multi_compare/tests/render -q
pytest -k divider                        # all tests whose name contains divider
pytest tests/runtime/test_event_bus_depth.py::TestEventBusDepth
```

For top-level `tests/`, `sys.path` for `src/` is added automatically via
`tests/conftest.py`. Tab tests under `src/tabs/<tab>/tests/` do not need that:
from `src/` down to the test file is an unbroken chain of packages with
`__init__.py`, so pytest inserts `src/` into `sys.path` when building the
rootdir package (standard prepend-import-mode). `sli-ui-toolkit` is installed
as an external dependency from `requirements-gui.txt`; there is no local
fallback path to a vendored toolkit. App tests cover app integration with the
toolkit, not the external library's public API.

The repository does not use a pytest config file (`pytest.ini` /
`pyproject.toml` are absent) — discovery follows pytest defaults.

## Layout

Tests are organized along two axes: **check type**
(contracts/render/runtime/plugins) within **owner** (app-wide code in `tests/`,
tab-specific code in `src/tabs/<tab>/tests/`).

**Ownership rule:** if a test imports `tabs.<tab_name>.*` (including lazily,
inside the test function body) and asserts behavior of that tab specifically —
it lives in `src/tabs/<tab_name>/tests/`, not in `tests/`. If a test exercises
a shared mechanism (tab registry, `TabContract`, Feature State API, event bus,
stacking policy, plugin isolation, etc.) — it stays in `tests/`, even when it
instantiates a concrete tab as an example. Folder structure details —
[tabs/isolation.md](tabs/isolation.md).

| Folder | What it checks | Style |
|---|---|---|
| `tests/contracts/` | Cross-cutting architectural dogmas, not tied to one tab (see `docs/dev/CONTRACTS.md`, `QRHI_CANVAS_FEATURES.md`). Scans sources with AST, no runtime. | Static analysis |
| `tests/runtime/` | Shared import/runtime contracts: registry, event bus, stacking policy, presentation isolation, graceful degradation. | Import + assertions |
| `tests/render/` | Shared composition/render-plan behavior, not tied to a specific tab. | Fake-context |
| `tests/plugins/` | Plugin behavior (`src/plugins/*`) not owned by one tab: settings, help, clipboard, workspace chrome. | Unit/integration |
| `src/tabs/image_compare/tests/{contracts,render,runtime,plugins,video}/` | Everything specific to image_compare (canvas features, magnifier, divider, video editor). | Mixed — see [tabs/isolation.md](tabs/isolation.md) |
| `src/tabs/multi_compare/tests/{contracts,render,runtime,plugins}/` | Everything specific to multi_compare (composition, dividers, labels, context menu). | Mixed — see [tabs/isolation.md](tabs/isolation.md) |

Shared helper for contract tests in `tests/` —
`tests/contracts/_framework.py`: paths (`SRC`, `CANVAS_FEATURES`, `PLUGINS`),
`iter_py`, `read`, `module_imports`, `list_canvas_features`, `list_plugins`,
`feature_name`. Use it instead of hand-rolled `Path(__file__).parent…`. Tab-specific
contract tests do not import this helper directly —
`src/tabs/image_compare/tests/contracts/_framework.py` keeps a narrower copy
with paths recomputed for `src/tabs/<tab>/tests/contracts/` depth so the tab
folder stays self-contained.

## File catalog

What each file guards — so you do not have to read sources one by one. Each
test's dogma is the first line of its docstring. Below covers only `tests/`
(cross-cutting contracts). For a specific tab's catalog, look next to that tab:
`src/tabs/image_compare/tests/`, `src/tabs/multi_compare/tests/` (the docstring
first line plays the same role — we do not duplicate a per-tab table here).

### `contracts/` — structural dogmas (AST scan, no runtime)

| File | What it guards |
|---|---|
| `test_canvas_features_manifest.py` | Every feature under `ui/canvas_features/` exports `WIDGET_FEATURE` with `name`; names are unique. |
| `test_canvas_features_imports.py` | Shared code does not import `tabs.image_compare.canvas.features.<name>` directly. |
| `test_canvas_features_layout.py` | No feature-named helpers in `canvas_presentation`; a feature does not reintroduce its own render pipeline. |
| `test_canvas_features_render_passes.py` | Render passes declare `stack_role`, do not hardcode layer/priority; shared `shader_sources` has no feature shaders. |
| `test_canvas_widget_ownership.py` | Magnifier/toolbar code lives under `tabs.image_compare.*`, not in the shared canvas layer (path-based check). |
| `test_canvas_content_geometry_single_owner.py` | Single owner of content-geometry math; no direct canvas-bounds access outside the allowlist. |
| `test_events_no_feature_branching.py` | `mouse.py`/events do not branch on feature flags or call feature aliases directly. |
| `test_no_manual_theming.py` | No manual theming calls outside theme infrastructure. |
| `test_no_system_tooltips.py` | No system Qt tooltips bypassing the shared tooltip interceptor. |
| `test_plugins_structure.py` | Every plugin: entry point, decorator+base, name matches folder, names unique. |
| `test_plugins_isolation.py` | A plugin does not import canvas features or other plugins' internals. |
| `test_platform_isolation.py` | Platform (non-tab-specific) code does not mention or import concrete tabs directly. |
| `test_tabs.py` | Every tab under `src/tabs/` is a filled `TabContract`; `session_type` is unique. |
| `test_tabs_isolation.py` | Tab does not import app i18n/theme/`ui.icon_manager`; JSON translations use only its own namespace. |
| `test_tab_icons.py` | Tab with `icons.py` has SVGs in `resources/icons/{light,dark}/` for every `Icon` member; resolve is non-null. |
| `test_viewport_state_slots.py` | `ViewportState` is slotted (no `__dict__`); `overlay_clip_rect` lives in runtime cache; writing it on `ViewportState` fails. |

### `runtime/` — import/runtime contracts

| File | What it guards |
|---|---|
| `test_interaction_contracts.py` | Event layer isolated from features; interaction aliases resolve; hit-test pipeline filled with callables. |
| `test_shared_presentation_isolation.py` | `shared/` and plugins use aliases only; Phase-5 aliases resolve. |
| `test_event_bus_depth.py` | EventBus depth guard: cyclic chain stops at `MAX_EMIT_DEPTH`; counter resets between top-level emits. |
| `test_plugin_graceful_degradation.py` | Empty `plugins/` and unknown alias do not break bootstrap (graceful degradation). |
| `test_tabs_lifecycle.py` | Drop routed via `accepts_drop`; `dispose()` is idempotent (generic registry mechanism; uses `ImageCompareTab` only as example). |
| `test_keyboard_movement_contracts.py` | Keyboard movement gestures not tied to a specific tab. |
| `test_dialog_auto_decoration.py` | Dialog auto-decoration (icons/title bar) applied at shared host level. |
| `test_main_window_resize_runtime.py` | Main window resize not tied to a specific tab. |
| `test_tooltip_interceptor.py` | Shared tooltip interceptor captures hints for all widgets, including tab bar. |
| `test_language_broadcast.py` | Language change broadcast to all i18n widgets via `resources.translations`; host sets `store` before `setupUi`. |

### `render/` — shared composition/render-plan behavior (fake-context)

| File | What it guards |
|---|---|
| `test_composition_plan.py` | Shared composition-plan assembly not tied to a specific tab. |
| `test_plan_applicator_composition.py` | Applicator combines composition plans correctly regardless of tab. |
| `test_qrhi_backend_selection.py` | QRhi backend selection is a shared mechanism, not tab-specific. |
| `test_qrhi_canvas_resize_contract.py` | QRhi canvas resize delegates to shared resize-geometry pipeline. |

### `plugins/` — plugin behavior not owned by one tab

| File | What it guards |
|---|---|
| `test_settings_controller.py` | `apply_font_settings` batches and caps; skips cap when unchanged. |
| `test_clipboard_paste_shortcut.py` | Ctrl+V on canvas emits paste event. |
| `test_help_dialog_anchors.py` | Help: anchor suffix strip, heading-id generation, TOC from h3 sections. |
| `test_image_properties.py` | Image properties readable regardless of active tab. |
| `test_main_window_canvas_theme_background.py` | Theme change updates canvas container background and placeholder at host level. |
| `test_main_window_save_button.py` | Main-window save button is host chrome, not tab-specific. |
| `test_settings_dialog_geometry.py` | Settings dialog geometry. |
| `test_workspace_session_menu_translations.py` | Workspace session menu uses host-level translations. |
| `test_workspace_tab_close.py` | Closing last workspace tab closes main window (workspace host mechanics, not a specific tab). |
| `test_workspace_tabs_layout.py` | `workspace_tabs` layout (QTabBar) — host tab-management widget, not a tab itself. |

## Two kinds of tests

### 1. Architectural contracts (`tests/contracts/`, `src/tabs/*/tests/contracts/`)

Do not launch the app — parse sources and enforce discipline:

- `test_canvas_features_manifest.py` — every feature under `src/ui/canvas_features/` exports `WIDGET_FEATURE` with `name`.
- `src/tabs/image_compare/tests/contracts/test_canvas_features_aliases.py` — capability aliases declared and unique.
- `test_canvas_features_imports.py` — features do not import each other directly (communicate via Store/EventBus/aliases).
- `test_canvas_features_layout.py`, `test_canvas_features_render_passes.py` — required submodules and pass signatures.
- `test_plugins_structure.py`, `test_plugins_isolation.py` — same for `src/plugins/*`.

Parameterize such tests via `list_canvas_features()` / `list_plugins()` and
`pytest.mark.parametrize(..., ids=...)` — then a new feature automatically
falls under all rules without editing tests.

### 2. Behavior contracts (`tests/render/`, `tests/runtime/`, `src/tabs/*/tests/{render,runtime,video}/`)

Import runtime classes and build minimal context by hand — no Qt application,
no QRhi/GPU context. Pattern: `SimpleNamespace` instead of mocks:

```python
from types import SimpleNamespace

def _build_ctx(*, show_divider, thickness, images_uploaded, content_rect):
    return SimpleNamespace(
        widget=SimpleNamespace(width=lambda: 100, height=lambda: 100, runtime_state=None),
        images_uploaded=list(images_uploaded),
        scene_frame=SimpleNamespace(
            feature_payloads={"show_divider": show_divider, "divider_thickness": thickness},
            is_horizontal=False,
            content_rect_px=content_rect,
        ),
    )
```

Assert *what* a pass does (did it call the painter, what commands did it record),
not *how* — without a Qt window or real QRhi rendering.

## Rules for writing new tests

1. **One test per contract, not per feature.** If a rule applies to all features — write a parameterized test in `tests/contracts/` that automatically covers future features.
2. **One file — one topic.** Name like `test_<thing>_contracts.py` for contract tests, `test_<feature>.py` for behavioral tests.
3. **No Qt/QRhi in unit tests.** If a test needs `QApplication` — that is integration; place it next to the subsystem under test and create `QApplication.instance() or QApplication([])` explicitly in a fixture.
4. **`SimpleNamespace` over `MagicMock`.** Mocks only fail when invoked; namespaces fail at `AttributeError`. Tests should fail on missing contract fields, not pass silently.
5. **Document the dogma in the docstring.** First line — link to a section in `docs/dev/`, so when a rule changes it is clear which doc to update with the test.
6. **Do not mock Store.** To test a reducer — dispatch a real action into a real store; for a pass — build `scene_frame` by hand.

## When tests break

- Contract test fails after adding a feature/plugin — the feature violates the dogma (`docs/dev/QRHI_CANVAS_FEATURES.md` or `CONTRACTS.md`). Fix the feature, not the test.
- Render contract fails — pass behavior changed. If intentional, update the test docstring and assertion in one change.
- Import failure — check that new code does not import Qt/QRhi at module top level. Use lazy import inside functions.

## What is NOT covered

- Real QRhi rendering — shader pixels (needs GPU context; backend- and driver-dependent). The seam around QRhi (render plan, `render_scene` params, fake-GPU payload) is covered; see `src/tabs/image_compare/tests/video/test_video_export_preview_parity_matrix.py`.
- Multi-window scenarios and OS drag-and-drop (**transport**). Drop routing (`route_drop`/`accepts_drop`) is covered in `contracts/test_tabs.py` + `runtime/test_tabs_lifecycle.py`.
- **Transport** of interactive gestures — live mouse/trackpad event delivery. Gesture **resolution** (priority, `matches`/`is_active` predicates) is covered in `src/tabs/image_compare/tests/runtime/test_gesture_resolution.py`.

For those checks — manual run via `python -m src` or the `verify` skill.

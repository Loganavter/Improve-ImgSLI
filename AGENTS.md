# Improve-ImgSLI Agent Guide

This file is for CLI AI agents and other automated coding assistants. Read it before making changes.

The codebase currently lives in **two parallel trees**:

- `src/` — original Python/PyQt6 implementation (production today, declarative, well-decomposed).
- `cpp/` — in-flight C++ Qt6 + Rust port (skeleton complete, hardening in progress).

The port is being shaped to mirror the Python tree file-for-file. Treat `src/` as the canonical reference for structure, naming, and decomposition — when in doubt about how to lay out a new C++ file or folder, find the Python analogue first.

---

# TOOLKIT PORTING LAW — MECHANICAL TRANSLATION PROTOCOL

**This section overrides all other guidance when porting ANY widget from the Python `sli-ui-toolkit` to C++ `cpp/toolkit/`. Read it before touching any toolkit file.**

## The fundamental truth

PySide6 **is** C++ Qt. Every PySide6 call is a direct alias for the underlying C++ Qt API:

| Python (PySide6) | C++ (Qt6) |
|---|---|
| `self.setFixedSize(36, 36)` | `setFixedSize(36, 36)` |
| `self.setCursor(Qt.PointingHandCursor)` | `setCursor(Qt::PointingHandCursor)` |
| `painter.drawRoundedRect(rect, rx, ry, mode)` | `painter.drawRoundedRect(rect, rx, ry, mode)` |
| `QTimer.singleShot(15, self._tick)` | `QTimer::singleShot(15, this, &This::tick)` |
| `self._some_signal.connect(self._handler)` | `connect(this, &This::someSignal, this, &This::handler)` |

There is **zero semantic distance** between PySide6 and C++ Qt6. The port is a **mechanical translation**, not a rewrite, not a redesign, not a "reimplementation from memory."

## The Law (non-negotiable)

### Rule 1: One Python file → One C++ file pair (.h + .cpp)

Every `.py` file in `sli-ui-toolkit` produces a corresponding C++ header and source. File names match: `button.py` → `button.h` + `button.cpp`. No merging multiple Python files into one C++ file. No splitting one Python file into multiple C++ files unless the original Python file already delegates to sub-modules.

### Rule 2: Every method is ported

For every method in the Python widget, there MUST be a corresponding C++ method. The method name, signature, return type, and body are translated mechanically.

```
Python:  def setFixedSize(self, w, h):  self._w = w; self._h = h
C++:     void setFixedSize(int w, int h) { w_ = w; h_ = h; }
```

A C++ method that exists but is empty or stubbed (`// TODO`) is **not** ported — it's a bug.

### Rule 3: Every literal value is copied exactly

```
Python:  size=(36, 36)        →  C++: size_(36, 36)         ← CORRECT
Python:  size=(36, 36)        →  C++: size_(32, 32)         ← BUG
Python:  Qt.PointingHandCursor → C++: Qt::PointingHandCursor ← CORRECT
Python:  Qt.PointingHandCursor → C++: Qt::ArrowCursor        ← BUG
Python:  corner_radius=12     →  C++: corner_radius_(12)    ← CORRECT
Python:  corner_radius=12     →  C++: corner_radius_(8)     ← BUG
Python:  "button.toggle.background.pressed" → same string    ← CORRECT
```

If the Python source says a value, the C++ port uses THAT value. Your training-data intuition about "typical values for this widget" is **irrelevant and harmful**. Read the Python file. Copy the number.

### Rule 4: Every signal/slot connection is wired

```
Python:  self._timer.timeout.connect(self._on_timeout)
C++:     connect(timer_, &QTimer::timeout, this, &Widget::onTimeout);
```

A connection that "exists architecturally" (the slot method is defined, the signal is declared) but is never `connect()`-ed is **not** ported — it's a bug. Every Python `connect()` call MUST have a corresponding C++ `connect()` call.

### Rule 5: The Python file is the ONLY authoritative source

When in doubt about any detail — a value, a method name, a layout parameter, a color, a behavior — **read the Python file.** Not your memory. Not your training data. Not "what makes sense for a Qt widget." The Python file.

### Rule 6: No creative simplification

```
Python:  10 helper methods, each 5 lines
C++:     3 helper methods, rest "not needed"               ← BUG
```

You do not get to decide which methods are "boilerplate" or "unnecessary." If the Python author wrote it, the C++ port has it. The only exception is Python-specific metaprogramming (`@property`, `__getattr__`) which should be translated to idiomatic C++ getters/setters — but the **behavior** must be preserved.

### Rule 7: Cursor, tooltip, size policy, focus policy — every QWidget property

These are often single-line settings buried in `__init__`. They are the most frequently missed items because LLMs optimize them away as "irrelevant detail." They are NOT irrelevant — they affect user-visible behavior.

```
Python:  self.setCursor(Qt.PointingHandCursor)             ← MUST PORT
Python:  self.setToolTip(tr("Click to select"))            ← MUST PORT
Python:  self.setSizePolicy(QSizePolicy.Expanding, ...)    ← MUST PORT
Python:  self.setFocusPolicy(Qt.StrongFocus)               ← MUST PORT
Python:  self.setMouseTracking(True)                       ← MUST PORT
Python:  self.setAttribute(Qt.WA_Hover, True)              ← MUST PORT
```

## The protocol: HOW to port a widget file

### Step 1: Open the Python file and KEEP IT OPEN

Read the entire Python file first. Do not close it. Reference it during every edit to the C++ file. If you need to check a value, scroll to the Python line — do not guess.

### Step 2: Create the header with mechanical mappings

For each Python class member, produce the C++ equivalent:

```
Python instance variable    →  C++ member variable (trailing _)
Python @property            →  C++ getter/setter pair
Python Signal()             →  Q_SIGNALS: void signalName();
Python def method(...)      →  void/RET method(...) declaration
Python __init__             →  explicit ClassName(QWidget* parent = nullptr)
```

### Step 3: Implement method bodies line-by-line

Walk the Python method body line by line. For each line, write the C++ equivalent. The translation table:

```
self._x = value             →  x_ = value;
self._x                     →  x_
super().__init__(parent)    →  QWidget(parent) in initializer list
self.setFixedSize(w, h)     →  setFixedSize(w, h);
self.setCursor(Qt.X)        →  setCursor(Qt::X);
self.update()               →  update();
self.rect()                 →  rect();
painter.drawText(rect, ...) →  painter.drawText(rect, ...);
QFont("Sans Serif", 10)     →  QFont("Sans Serif", 10);
QColor("#RRGGBB")           →  QColor("#RRGGBB");
signal.emit()               →  Q_EMIT signal();
connect(a, SIG, b, SLOT)    →  connect(a, &A::sig, b, &B::slot);
```

### Step 4: Verify against the parity tester

After porting a widget, add visual cases and query cases to `tests/parity/cases.json`. Run:

```bash
ctest --test-dir cpp/build -R parity_corpus
```

All cases must pass before the port is considered complete.

### Step 5: Run the structural parity checker

```bash
python tests/parity/check_structure.py cpp/toolkit/src/buttons/button.cpp
```

This flags: methods in Python missing from C++, methods in C++ not in Python, signal connections in Python missing from C++, literal value mismatches. All warnings must be resolved or explicitly justified with a comment in the C++ code.

## What the LLM must NEVER do when porting toolkit widgets

### NEVER write a widget from "Qt knowledge"

```cpp
// WRONG — LLM wrote its idea of a Button
class Button : public QAbstractButton {
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.fillRect(rect(), isChecked() ? Qt::blue : Qt::gray);
        p.drawText(rect(), Qt::AlignCenter, text());
    }
};
```

There is already a 709-line Python `button.py`. Translate IT. Do not invent a new Button.

### NEVER round or adjust values

```
Python: 36  →  C++: 36  (not 32, not 40, not 30)
Python: 22  →  C++: 22  (not 20, not 24)
Python: 15  →  C++: 15  (not 16, not 10)
```

### NEVER skip methods because "they're trivial"

```
Python has:  def _compute_rect(self): return QRect(0, 0, self._w, self._h)
LLM skips:  "Not needed, QWidget already has rect()"

WRONG. The Python author wrote it for a reason. Port it, then if it's truly redundant,
the parity tester will catch the behavioral difference and you can address it THEN.
```

### NEVER assume a connection "just works" because the slot exists

```
Python:  connect(btn, &QPushButton::clicked, this, &MyWidget::onClicked);  ← MUST HAVE
LLM:     // onClicked slot is defined, it'll be called somehow               ← BUG
```

### NEVER use QSS (Qt Style Sheets) instead of the painter pipeline

The Python toolkit uses a layered painter + theme token system. The C++ port uses the SAME architecture. Inline `setStyleSheet("background: blue")` is not a valid shortcut — it bypasses the entire theming engine.

### Read in chunks; fix in chunks

When porting a Python file larger than ~200 lines, DO NOT read the entire file in one shot and then write the entire C++ file in one shot. The LLM's attention degrades over long context — by line 500, values from line 50 have been forgotten.

**The chunked protocol:**

1. Read the full Python file to understand structure (one read, but don't memorize values).
2. Port the file in **chunks of 80–120 lines**: read the Python chunk, immediately write the C++ equivalent, move to the next chunk.
3. **Before each chunk, re-read the relevant Python lines** — do not rely on memory of what you read 5 minutes and 400 lines ago.
4. After the full file is ported, do a final pass: re-read the Python file top-to-bottom and verify every method, constant, and connection is present in the C++ file.

**Why this matters**: the parity tester caught that `Button::sizeHint` used `height=36` instead of Python's `max(32, fontHeight+16)`, that the cursor was `PointingHandCursor` when Python sets no cursor, and that the checked-state color was accent (bright blue) instead of subtle grey. All three were cases where the LLM ported from "what makes sense for a Qt button" rather than from the Python source — a direct consequence of reading the entire file at once and then writing from degraded memory.

**For files >500 lines**: split the port across multiple sessions or subagent tasks. A 571-line `combo_box.py` should be ported as 4–5 chunks, each re-reading the relevant Python slice.

---

## C++/Rust Port

The port is laid out so every Python folder has a one-to-one C++ counterpart. This is the **prime directive** of port work: do not invent new structure — mirror `src/` exactly.

### Layout

```
cpp/
  core/                 # Rust crate — backend / single source of truth for logic
    src/
      lib.rs
      bridge.rs         # CXX FFI surface (narrow; no Qt types cross)
      domain.rs         # value primitives (Point, Color, Rect)
      i18n.rs           # translation catalog
      core/             # state, store, reducer, action (mirrors src/core/)
      plugins/<name>/   # plugin models (mirrors src/plugins/<name>/)
      ui/canvas/        # plan, plan_keys, virtual_layout, stacking,
                        # hit_test, image_cache
      tabs/<name>/      # tab logic (e.g. multi_compare/playlist.rs)
      workspace/        # session blueprint hydration
  core_py/              # PyO3 bridge crate (legacy Python-side glue)
  include/imgsli/
    contracts/          # public C++ contracts: plugin, tab, canvas_widget_feature
    store_observer.h    # store observer interface
  toolkit/              # cpp/toolkit — atomic + composite UI primitives
                        # (Button, ComboBox, SpinBox, CheckBox, RadioButton,
                        #  SectionHeader, Divider, Toolbar, Flyout, ChipGroup,
                        #  Icon, GroupBox, Switch, Slider, Label, LineEdit,
                        #  LoadingSpinner, DropZoneLabel)
  app/                  # the Qt application — flat tree intentionally avoided
    cli/                # per-command CLI translation units
    core/               # store, *_registry, render-pass contracts (runtime glue)
    shell/              # main.cpp (bootstrap), custom_window, i18n_helper
    ui/canvas/          # canvas widget, canvas_features, feature_passes, shaders/
    plugins/<name>/     # one folder per plugin, mirrors src/plugins/<name>/
      plugin.cpp        # service registration + dispatch only
      controller.{h,cpp}# presenter/controller surface
      services/         # plugin-owned services (recorder, offscreen renderer, …)
      sections/         # declarative UI sections (when split out of tabs/dialog)
    tabs/<name>/        # one folder per workspace tab, mirrors src/tabs/<name>/
      tab.cpp           # TabContract impl + section composition
      sections/         # tab-specific UI sections
      grid.cpp/.h       # tab-specific helpers (e.g. multi_compare grid)
```

### Symmetry rule (load-bearing)

Before adding or splitting C++ code, **find the Python counterpart first**:

| If you are touching … | Read first … |
|---|---|
| `cpp/app/plugins/<name>/` | `src/plugins/<name>/` |
| `cpp/app/tabs/<name>/` | `src/tabs/<name>/` |
| `cpp/app/ui/canvas/` | `src/ui/canvas_infra/`, `src/ui/canvas_features/`, `src/ui/widgets/gl_canvas/` |
| `cpp/app/core/` | `src/core/`, `src/ui/canvas_infra/scene/` |
| `cpp/app/shell/` | `src/__main__.py`, `src/ui/main_window/` |
| `cpp/toolkit/` | external `sli-ui-toolkit` (local checkout: `/home/jorj/Загрузки/sli-ui-toolkit`) — **follow the Toolkit Porting Law above** |
| `cpp/core/src/` | `src/core/`, `src/domain/`, `src/shared/rendering/`, and the corresponding plugin model file (e.g. `src/plugins/video_editor/model.py`) |

The Python side is **declarative** — sections, pages, feature manifests, dialog schemas are data, not inline widget construction. The C++ side must follow the same shape.

### Where logic lives — Rust is the backend

Treat the Rust crate at `cpp/core/` as **the backend of the application**. C++ is the Qt/UI shell. The split is hard, not aspirational.

**Rust owns** (`cpp/core/src/`, mirroring `src/`):

- `core/` — `state.rs`, `store.rs`, `reducer.rs`, `action.rs` (mirrors `src/core/`).
- `plugins/<name>/` — pure logic for each plugin: settings (`model.rs`, `dialog.rs`), video editor (timeline, project model, ffmpeg argument synthesis), analysis (PSNR/SSIM/diff).
- `ui/canvas/` — `plan.rs`, `plan_keys.rs`, `virtual_layout.rs`, `stacking.rs`, `hit_test.rs`, `image_cache.rs` (LRU).
- `tabs/multi_compare/playlist.rs` — playlist math.
- `workspace/session_blueprint.rs` — session blueprint hydration.
- `domain.rs` — value primitives (`Point`, `Color`, `Rect`).
- `i18n.rs` — translation catalog.
- `bridge.rs` — CXX FFI surface. Keep it narrow. Qt and QRHI types must never cross.

**C++ owns** (`cpp/app/`):

- Qt event loop, widgets, dialogs, QRhiWidget pipelines, QProcess, file I/O against the OS.
- Subscriptions to scoped `StoreUpdate`s and dispatch of typed `Action`s.
- Anything that requires `QObject`, `QWidget`, `QImage`, `QPainter`, `QRhi`, GL/Vulkan, threading via Qt.

### When to use Rust vs C++

Use **Rust** when you are adding or changing:

- application state, settings, or any field on `AppState`;
- a state transition — add an `Action` variant + reducer branch + scope;
- a pure-data model (project, dialog schema, render plan POD, blueprint shape);
- math or geometry the canvas/export both depend on (layout, plan keys, hit-test, letterbox, stacking);
- a caching policy that holds raw bytes/pixels (LRU, generation counters);
- i18n catalog or translation lookups;
- pipeline argument synthesis (ffmpeg args, encoder configs);
- serialization formats (JSON shapes, persisted blueprints, settings round-trip).

Use **C++** when you are adding or changing:

- a widget, dialog, toolbar, or section;
- a QRhi/GL pipeline or shader binding;
- a Qt signal/slot wiring or `QProcess` launcher;
- a Qt threading construct (`QtConcurrent`, `QThreadPool`, `QFuture`);
- a file-dialog flow, clipboard interaction, or other OS integration;
- a CLI command flag (parsing into `StartupOptions`, then handing the typed result to a command translation unit).

If a piece of work has both — say, a new plugin export option — split it: model + serialization + validation in Rust; widget + dispatch in C++. Do not duplicate the model in C++.

### Decision rule when adding a feature

1. **State shape change?** Rust first: add field to `AppState`, default value, action variant, reducer branch, scope. Add a focused Rust test.
2. **Expose to C++.** Extend `bridge.rs` minimally — one FFI function or struct per concept. Never leak Rust types into Qt headers; never leak Qt types into Rust.
3. **Wire C++ widgets.** Controller dispatches the typed action and subscribes to the scope it cares about. No `QSettings` for app state, no JSON parsing in widget code.
4. **Verify** with the commands in [Verification](#verification).

If you ever find yourself writing domain logic directly in a `.cpp` file — stop. Move it to Rust.

### Contracts

Three public C++ contracts in `cpp/include/imgsli/contracts/`:

- `plugin_contract.h` + `IMGSLI_REGISTER_PLUGIN` — plugin registration, service surface.
- `tab_contract.h` — workspace tab interface (session type, display name, build).
- `canvas_widget_feature.h` — canvas feature contract (mirrors Python `CanvasWidgetFeature`).

When adding a plugin or tab, implement the contract; do not bypass the registry.

### Verification

Run these before considering a change done. All must stay green:

```bash
cmake --build cpp/build -j2
ctest --test-dir cpp/build --output-on-failure -R phase3_contracts
ctest --test-dir cpp/build --output-on-failure -R parity_corpus
cargo test --workspace --manifest-path cpp/Cargo.toml
cargo fmt --check --manifest-path cpp/Cargo.toml
cargo clippy --workspace --all-targets --manifest-path cpp/Cargo.toml -- -D warnings
```

For changes touching the canvas or render plan, also run the smoke CLI commands:

```bash
cpp/build/app/imgsli_app --snapshot <out.png>            # offscreen render
cpp/build/app/imgsli_app --analysis-snapshot <out.png>   # analysis render
cpp/build/app/imgsli_app --video-transcode <args>        # video pipeline
```

### Wayland decoration caveat

Do **not** add `WA_NativeWindow` on the top-level window or attach a `QVulkanInstance` to it — that re-triggers the Qt-Wayland 6.11 + QRhiWidget + Mutter decoration regression. The custom CSD in `cpp/app/shell/custom_window.{h,cpp}` is the working solution; preserve it. Context: `docs/dev/CPP_PORT_HARDENING.md` and the comment in `custom_window.cpp`.

### When refactoring port code

- Mirror the Python file layout exactly (folder for folder, file for file).
- Prefer many small files over one large file. A C++ source file > 500 lines is a smell; > 800 lines is a structural problem to fix in the same patch.
- Each plugin folder should expose: `plugin.cpp` (registration), `controller.{h,cpp}` (presenter), `services/` (plugin-owned services), `sections/` (UI sections, if split from the tab/dialog).
- `plugin.cpp` should contain registration and a service-id dispatch table — nothing more. Long handlers go into `services/` or `controller.cpp`.
- Tab `tab.cpp` files should contain the `TabContract` impl and a list of section instances. Inline form-building belongs in `sections/`.

---

# Toolkit Quality Gates

Three automated checks that MUST pass before any toolkit port is considered complete.

## Gate 1: Structural parity checker

Location: `tests/parity/check_structure.py` (to be created)

For each `.py` file in `sli-ui-toolkit` and its `.cpp`/`.h` counterpart in `cpp/toolkit/`:

1. **Method inventory**: Every public and private method in Python must have a C++ counterpart. Methods in C++ but not in Python are flagged (possible invention).
2. **Signal/connection inventory**: Every `Signal()` declaration and `connect()` call in Python must have a C++ equivalent.
3. **Literal audit**: Key numeric literals (36, 22, 15, 12, 10, etc.) and enum values (PointingHandCursor, StrongFocus, etc.) are extracted from Python and verified in C++.

Output: a list of warnings. Zero warnings = gate passed.

Run with: `python tests/parity/check_structure.py <cpp_file>`

## Gate 2: Parity corpus (pixel-diff)

Location: `tests/parity/cases.json` + `tests/parity/run_parity.py` + `cpp/toolkit/tests/parity_renderer.cpp` + `tests/parity/python_renderer.py`

For each widget family, render the SAME widget configuration on both Python and C++ sides, paint to PNG, and compare pixel-by-pixel. Since both sides use Qt6 on the same machine, any sustained pixel difference is a PORT BUG — same fonts, same DPI, same rendering engine.

Current coverage (19 visual + 6 query cases for Button):
- Button: text × {default, hover, pressed, focused, disabled}, toggle × {unchecked, checked}, size variants, corner radius, ghost/default variants, underline, background colors, icon+text
- Queries: focusPolicy, hasExplicitCursor, isCheckable, sizeHintWidth, rippleActiveAfterPress

**To extend coverage** to a new widget family:
1. Add `cases` entries to `tests/parity/cases.json` for the widget
2. Add factory logic to `tests/parity/python_renderer.py` and `cpp/toolkit/tests/parity_renderer.cpp`
3. For each state × variant combination, define expected diff_max_per_pixel
4. Run `ctest --test-dir cpp/build -R parity_corpus`

**Target**: every widget family must have at minimum 3 visual cases (default state, hover, and one variant).

## Gate 3: Raw-Qt-widget sweep

Location: `docs/dev/TOOLKIT_PORT_AUDIT.md` — "Audit of remaining raw-Qt-widget usages" table

Every `QLabel`, `QLineEdit`, `QSlider`, `QPushButton`, `QToolButton` used in `cpp/app/` that has a toolkit equivalent (`sli::toolkit::Label`, `CustomLineEdit`, `Slider`, `Button`) must be migrated to the toolkit widget.

The migration table in `TOOLKIT_PORT_AUDIT.md` is the tracking document. After each migration, verify the app builds and `parity_corpus` stays green.

---

## Python Codebase Areas

The Python tree under `src/` is the reference implementation and is still the production code. Port work depends on it. When a port task touches a plugin, **always read the Python equivalent first** — it documents the intended decomposition.

### Canvas, magnifier, overlays, render/export parity

Read:

1. [docs/dev/CANVAS_FEATURES.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CANVAS_FEATURES.md)
2. [docs/dev/CONTRACTS.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CONTRACTS.md) — complete contracts reference
3. [src/ui/canvas_presentation](/home/jorj/Загрузки/Improve-ImgSLI/src/ui/canvas_presentation)
4. [src/ui/widgets/gl_canvas](/home/jorj/Загрузки/Improve-ImgSLI/src/ui/widgets/gl_canvas)

C++ counterparts: `cpp/app/ui/canvas/` and `cpp/core/src/plan.rs` / `plan_keys.rs` / `stacking.rs`.

Important:

- Live canvas, export preview, final export, and video snapshot rendering must stay visually consistent.
- If you change diff rendering, verify `highlight`, `grayscale`, `edges`, and `ssim` in both live and export paths.
- Avoid appending feature-specific logic to generic `canvas_presentation` helpers if it belongs in a feature folder.

### Help system and documentation UI

Read:

1. [docs/dev/HELP_WIDGET.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/HELP_WIDGET.md)
2. [src/plugins/help/dialog.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/dialog.py)
3. `sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog` in the external `Loganavter/sli-ui-toolkit` repository

C++ counterpart: `cpp/app/plugins/help/`.

Important:

- Help content lives in `src/resources/help/<lang>/` and is shared by both Python and C++ builds.
- Keep help pages scenario-based, anchor-friendly, and split into short `###` sections.
- When features change, update help pages as part of the same task.

### Toolkit widgets and reusable UI

Read:

1. External toolkit repository: `https://github.com/Loganavter/sli-ui-toolkit`
2. Local toolkit checkout: [/home/jorj/Загрузки/sli-ui-toolkit](/home/jorj/Загрузки/sli-ui-toolkit)
3. Toolkit [README.md](/home/jorj/Загрузки/sli-ui-toolkit/README.md)
4. Toolkit [docs/README.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/README.md)
5. Toolkit [docs/ARCHITECTURE.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/ARCHITECTURE.md)
6. Toolkit [docs/API_CATALOG.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/API_CATALOG.md)
7. Toolkit [docs/DESIGN_LANGUAGE.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/DESIGN_LANGUAGE.md)
8. For button/control work, also read [docs/BUTTON_API.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/BUTTON_API.md), [docs/FLYOUT_SYSTEM.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/FLYOUT_SYSTEM.md), and [docs/KEYBOARD.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/KEYBOARD.md) when relevant.

C++ counterpart: `cpp/toolkit/`. **Follow the Toolkit Porting Law at the top of this file for every widget port.**

Important:

- Prefer public imports from `sli_ui_toolkit.widgets` for Python app code, and `sli/toolkit/...` headers for C++ app code.
- Keep app-specific logic out of toolkit code.
- If a control family grows, split it into a folder like `buttons/` or `comboboxes/`.
- **Never** use raw `QFormLayout`/`QVBoxLayout` blocks for widget construction — use the toolkit painter pipeline.
- **Never** use QSS (`setStyleSheet`) to style toolkit widgets — the painter pipeline owns all visual output.

### Export, snapshot rendering, video editor

Read:

1. [src/plugins/export/services/image_export.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/export/services/image_export.py)
2. [src/plugins/export/services/snapshot_render_plan_builder.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/export/services/snapshot_render_plan_builder.py)
3. [src/plugins/video_editor/services/video_snapshot_rendering.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/video_editor/services/video_snapshot_rendering.py)

C++ counterparts: `cpp/app/plugins/export/`, `cpp/app/plugins/video_editor/`, plus Rust `cpp/core/src/video_editor.rs` (timeline cursor, selection, ffmpeg argument synthesis).

Important:

- Export paths are easy to desync from live rendering. Check them explicitly.
- Toast/progress UX for long-running export work is part of the product, not a side detail.

## Project Structure (Python)

Use this mental model for `src/`:

- `src/core/`: app state, settings, events, reducers, shared runtime contracts
- `src/plugins/`: feature/domain plugin layer
- `src/ui/`: presenters, canvas integration, Qt widgets, main window
- `src/shared/`: shared processing and rendering helpers
- `src/shared_toolkit/`: app-side QSS/resources and older shared UI integration points
- `sli-ui-toolkit`: external reusable PyQt toolkit installed from `requirements-gui.txt`
- `src/resources/help/`: localized in-app help content (shared with the C++ build)

## Project Rules

- Do not treat this as a generic CRUD app. Rendering parity and interaction fidelity matter.
- Do not assume export preview and final export work the same as live canvas. Verify them.
- Do not move app code into `sli-ui-toolkit` unless it is truly reusable and app-agnostic.
- Do not add visible user-facing behavior without checking translations and help impact.
- Do not silently remove legacy compatibility imports from the toolkit unless the whole tree is migrated.
- **C++ port**: do not put domain logic in C++ files when it can live in Rust. Do not invent new C++ structure when a Python folder already shows the right one.
- **Toolkit port**: follow the Toolkit Porting Law. Every Python method → C++ method. Every literal → same literal. Every connection → wired. The Python file is the only authoritative source.

## Known Constraints

- Images above `16384 px` on either side are currently unsupported by software guard.
- `ssim` has special handling because some paths depend on cached diff images and GPU diff textures.
- Help pages now support anchors and generated in-page TOC. Keep headings stable.
- C++ build under Qt-Wayland 6.11 requires the custom CSD in `cpp/app/shell/custom_window.cpp`. Do not regress it.

## Workflow (mandatory for toolkit ports)

1. **Read the Python file first** — the entire file. Keep it open during the edit.
2. **Create/update the C++ file** by mechanical translation, not by writing "what makes sense."
3. **Add parity cases** for the widget to `tests/parity/cases.json` (at minimum: default, hover, one variant).
4. **Run all three gates**: `cmake --build cpp/build -j2`, `ctest -R parity_corpus`, `ctest -R phase3_contracts`.
5. **If the parity tester fails**: fix the C++ code, not the test. The Python side is the reference.
6. **After 3+ widgets are ported**: run the full app side-by-side with Python for visual A/B.

## Tests

### Python

See [docs/dev/TESTING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TESTING.md) for full layout and conventions.

Tests are grouped by subsystem under `tests/`:

- `tests/contracts/` — static architectural dogmas (AST scan, no runtime).
- `tests/runtime/` — registry, Feature State API, stacking policy.
- `tests/render/` — GL pass behavior with fake `SimpleNamespace` context.
- `tests/plugins/` — plugin behavior (export, help, settings, toast, clipboard).
- `tests/toolkit/` — `sli-ui-toolkit` public API.
- `tests/video/` — video editor preview/timeline/keyframes contracts.
- `tests/parity/` — cross-language widget pixel-diff parity tester.

Common focused test pattern:

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/<target_test>.py
```

When fixing a rendering/export/UI wiring bug, prefer adding a focused regression test in the matching folder rather than at the top level of `tests/`.

### C++ / Rust

- `cargo test --workspace --manifest-path cpp/Cargo.toml` — Rust unit tests (state, reducer, virtual_layout, analysis, video_editor, …). Add a test next to the module it covers.
- `ctest --test-dir cpp/build -R phase3_contracts` — load-bearing integration smoke executed via `--contract-check` of the compiled `imgsli_app`. Extend it when introducing a new contract.
- `ctest --test-dir cpp/build -R parity_corpus` — cross-language widget parity tester. Extend `tests/parity/cases.json` when porting a new widget family.
- For new GoogleTest-less C++ components, at minimum add a probe inside the `--contract-check` path.

## Debugging Runtime Issues

When something goes wrong after a click / zoom / state change and the cause is not obvious from the diff, use the runtime tracer described in [docs/dev/TRACING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TRACING.md). It captures the causal chain across Redux dispatches, EventBus publishes, and render frames — much faster than instrumenting with `logger` calls by hand.

## When To Update Docs

Update documentation in the same task if you change:

- help page behavior or content
- toolkit public widget API
- rendering/export architecture
- user-visible hotkeys, settings, or workflow
- the C++ port layout or any of the contracts in `cpp/include/imgsli/contracts/`
- parity test corpus (`tests/parity/cases.json`)

Usually this means touching one of:

- [src/resources/help/en](/home/jorj/Загрузки/Improve-ImgSLI/src/resources/help/en)
- external `sli-ui-toolkit` docs/API_CATALOG.md
- external `sli-ui-toolkit` docs/ARCHITECTURE.md
- [docs/dev/HELP_WIDGET.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/HELP_WIDGET.md)
- [docs/dev/CANVAS_FEATURES.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CANVAS_FEATURES.md)
- [docs/dev/CPP_PORT_HARDENING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CPP_PORT_HARDENING.md)
- [docs/dev/TOOLKIT_PORT_AUDIT.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TOOLKIT_PORT_AUDIT.md)

## Good Defaults For Agents

- Prefer `search_files` for code search.
- Prefer small, explicit patches.
- Prefer adding a focused regression test when fixing rendering/export/UI wiring bugs.
- If a bug involves preview vs export mismatch, inspect both code paths before changing anything.
- When porting C++ structure, mirror the Python folder layout exactly. Do not invent.
- When a C++ file passes ~500 lines, plan its split in the same patch.
- **When porting toolkit widgets, follow the Toolkit Porting Law at the top of this file. The Python file is the only truth.**
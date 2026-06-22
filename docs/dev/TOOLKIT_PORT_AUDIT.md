# C++ Toolkit Port — Audit of real port gaps

Track D claims toolkit depth is fully ported («architecture landed,
visual fidelity pending»). When trying to use the C++ toolkit from the
shell to match Python's main-window UI, multiple **real porting bugs**
surfaced — not «we need a token system»-style visual gaps, but logic
that was scaffolded with the right shape and then left non-functional.

This doc catalogues what was found during the bootstrap-rewrite pass so
that the next toolkit pass can close it as one batch instead of being
discovered one widget at a time.

## Confirmed porting bugs

### 1. `ButtonGroup::paintEvent` — label position wrong

**Symptom.** Group labels («Линия», «Вид», «Лупа», «Запись»…) showed up
as a small badge in the **top-left** of the group rect, painted over the
top border, instead of being centred at the bottom with a gap punched in
the bottom border line (Python style — a classic legend group box).

**Root cause.** Port of `paintEvent` was incomplete:

```cpp
// C++ — wrong
const QRect borderRect = rect.adjusted(0, labelHeight / 2, -1, -1);
…
const QRect labelRect(12, 0, labelWidth, labelHeight);
painter.fillRect(labelRect, bgColor);
painter.drawText(labelRect, Qt::AlignLeft | Qt::AlignVCenter, label_);
```

Python's source paints from the bottom with a centred punched gap:

```python
# python — right
draw_rect = QRect(margin_h, margin_v,
                  rect.width() - margin_h*2 - 1,
                  bottom_y - margin_v*2)
…
gap_rect  = QRect(center_x - label_w//2 - 3, gap_y,
                  label_w + 6, gap_height)
text_rect = QRect(center_x - label_w//2,
                  rect.height() - label_h - 2,
                  label_w, label_h)
```

**Status.** Fixed in `cpp/toolkit/src/buttons/button_group.cpp` — paint
now mirrors Python one-to-one.

### 2. `CustomWindow` / `TitleBar` ignore the active theme

**Symptom.** Switching `Theme::apply(app, Light)` left the title bar +
outer frame + window control buttons (`min` / `max` / `×`) dark. Result
was a bizarre mix of light buttons over dark decoration.

**Root cause.** Three hard-coded dark colours in
`cpp/app/shell/custom_window.cpp`:

```cpp
pal.setColor(QPalette::Window, QColor(24, 24, 26));   // outerCentral
pal.setColor(QPalette::Window, QColor(32, 32, 34));   // TitleBar
"QToolButton { … color: #DCDCDC; … }"                  // glyph
```

Theme was applied to `QApplication::palette()` only; widgets that ran
their own `setPalette(...)` overrode it.

**Status.** Fixed — all three now read from `sli::toolkit::Theme::palette()`.

### 3. `Button::paintEvent` always paints `TextContent` — `region.icon` ignored

**Symptom.** `Button` constructed with an icon-bearing spec (via
`setSpec`) still rendered as text-only — icon never appeared.

**Root cause.** `cpp/toolkit/src/buttons/button.cpp:162`:

```cpp
ctx.content = std::make_shared<buttons::TextContent>(text());
```

This unconditionally overrides any content the spec would produce.
Python builds content from spec state:

```python
def _build_content(self):
    if self._rows: return RowsContent(...)
    if text and icon: return IconTextContent(...)
    if text:         return TextContent(...)
    if icon:         return IconContent(...)
    return None
```

The C++ port never ported `_build_content` for the widget-scope path; it
just hard-codes text.

**Status.** Fixed. `Button::paintEvent` now derives content from the
first region of the controller's spec via `buildContentFromRegion`
(`cpp/toolkit/src/buttons/content/content.cpp`), mirroring Python's
`_build_content`: rows → `RowsContent`, icon+text → `IconTextContent`,
text → `TextContent`, icon → `IconContent`. Falls back to widget
`text()` when no spec was attached, so bare `Button("foo")` still
works.

### 4. `Painter::paint` region-scope only emits `TextContent`

**Symptom.** Even if the widget-scope hard-code were removed,
multi-region specs (split buttons with one icon-only region) would still
not render icons.

**Root cause.** `cpp/toolkit/src/buttons/painter.cpp:74-78`:

```cpp
if (!region.text.isEmpty()) {
  args.content = std::make_shared<TextContent>(region.text);
} else {
  args.content = ctx.content;
}
```

Python's region-scope mirror (`_build_region_content` in `button.py`)
selects between `RowsContent` / `IconTextContent` / `TextContent` /
`IconContent` based on `region.icon` + `region.text` + `region.rows`.
The C++ port stopped at «text → TextContent».

**Status.** Fixed. `Painter::paint`'s region-scope branch now calls
the shared `buildContentFromRegion` helper instead of the
text-or-inherit shortcut, so split buttons with icon-only regions
render their icons (and rows/icon+text combinations) end-to-end.

### 5. `Button` ergonomic constructor missing icon / toggle / size args

**Symptom.** Building a Python-style icon-only toggle button:

```python
Button(AppIcon.MAGNIFIER, toggle=True, variant="surface")  # 1 line
```

…has no C++ equivalent. The only ctor is:

```cpp
explicit Button(const QString& text = {},
                Variant variant = Variant::Surface,
                QWidget* parent = nullptr);
```

Everything else (icon, toggle, size, icon_size, badge, scrollable,
long_press, …) requires hand-building a `ButtonSpec` with regions, then
calling `setSpec(...)` — verbose enough that the shell falls back to
`QPushButton + setStyleSheet(":checked …")` instead.

**Status.** Fixed. `Button` now exposes a nested `Config` struct
mirroring Python's keyword args (`text`, `icon`, `iconChecked`,
`variant`, `toggle`, `size`, `iconSize`, `badge`, `scrollable`,
`longPressMs`, `menu`, `showUnderline`) and a
`Button(const Config&, QWidget*)` ctor that builds the spec
internally **and** auto-attaches the matching
`ScrollCapability` / `LongPressCapability` / `MenuCapability`. The
shell can drop its `QPushButton + setStyleSheet(":checked …")`
fallback and call `Button({.icon = …, .toggle = true, .variant = …})`.

### 6. `Button` doesn't propagate `region.toggle` to `setCheckable`

**Symptom.** Even after `setSpec` with `region.toggle = true`, the
button is not checkable at the Qt level — `isChecked()` always returns
false, painter never sees `ButtonState::Checked`.

**Root cause.** `setSpec` only forwards to the controller; nothing wires
`region.toggle` → `QAbstractButton::setCheckable(true)`. Caller has to
manually call `setCheckable(true)` in addition to `setSpec`.

**Status.** Fixed. `Button::setSpec` now walks
`controller_->regions()` after applying the new spec and calls
`setCheckable(true)` if any region declares `toggle` (which
`RegionSpec::toRegion()` already maps from `BehaviorKind::Toggle`).
The `Button(Config)` ctor reaches the same wire via `setSpec`.

## Likely / suspected gaps (not yet verified)

These were not reached during the current pass but the pattern of #3-6
suggests they are likely affected by the same «scaffold the shape,
leave logic stub» mode:

- **`Button.scrollable`** — auto-attach now done by the new
  `Button(Config)` ctor (Config.scrollable → `ScrollCapability`). The
  raw `setSpec(...)` path still requires a hand `addCapability(...)`.
- **`Button.long_press`** — same: auto-attached when constructed via
  `Config.longPressMs`; not auto-attached from a raw spec.
- **`Button.menu`** — same: auto-attached when constructed via
  `Config.menu`; not auto-attached from a raw spec.
- **`Button.badge`** — `ButtonRegion::badge` field exists, `BadgeLayer`
  is ported — is the spec-to-layer wiring done end-to-end? Untested.
- **`Button.show_underline`** — `UnderlineLayer` ported; spec field
  exists; same question.
- **`AdaptiveTabStrip`** — used at top of Python main window (workspace
  tabs row, `Image Compare 1` + `+` button). C++ port: **not present**.
  Bootstrap currently fakes it with a bare `QTabBar` + disabled `+`
  push button.
- **`ScrollableComboBox`** — used by Python combobox row under image
  selectors. C++ port: present (`cpp/toolkit/.../comboboxes/`) but
  unused in the shell yet.
- **`unified_flyout`** depth — 13 modules claimed ported (D7). Not yet
  exercised by the shell; visual fidelity unknown.

## What the depth-port claim actually covered

Reading the track-D diff vs the actual code:

- **Architecture** (file shape, controller / layers / capabilities
  split, painter pipeline ABC, content classes) — yes, mirror Python
  shape.
- **Wiring between layers** — partial. The connectors that map
  `ButtonSpec` ↔ visual output are stubs in places (#3, #4).
- **Convenience surface** (the ergonomic `Button(icon, toggle=...)`
  the rest of the shell calls into) — not ported.
- **Theme propagation through hand-built widgets** — `CustomWindow`
  bypasses theme entirely (#2).

«Architecture landed, visual fidelity pending» understates the gap.
The architecture is **wired-as-shape but not as logic** in places — a
deep paint pipeline that reaches the icon-rendering content class via
spec is in place, but the path from `Button(icon=…)` to that content
class is severed at two points (`Button::paintEvent` hard-code +
`Painter::paint` region-content selector).

## Follow-up status

The items #3–#6 are **closed** in this pass:

1. ✅ `_build_region_content` ported into `Painter::paint` via the
   shared `buildContentFromRegion` helper.
2. ✅ `Button::paintEvent` no longer hard-codes `TextContent`; it
   derives content from the first region of the controller spec.
3. ✅ `Button::setSpec` propagates `region.toggle` →
   `QAbstractButton::setCheckable(true)`.
4. ✅ `Button::Config` + `Button(const Config&, QWidget*)` ctor —
   builds the spec internally and auto-attaches
   `ScrollCapability` / `LongPressCapability` / `MenuCapability`.

Still open as a small follow-up:

5. Smoke-test the «suspect» list (badge / underline end-to-end paint,
   menu drop-down position, scroll-on-wheel value clamping) using the
   new ergonomic ctor — instantiate one of each variant in a test
   harness and verify visual + behavioral parity with Python.

The shell bootstrap can now drop its `QPushButton + setStyleSheet`
workarounds and use `sli::toolkit::Button({...})` as Python does — one
expression per button, with theme-aware paint instead of QSS.

## Audit of remaining raw-Qt-widget usages in the app

Python keeps every leaf control (button, label, line edit, slider,
combo, checkbox, radio, switch, group box, etc.) on the toolkit. The
C++ app already routes most form controls through `sli::toolkit::*`,
but the following call sites still construct raw Qt widgets where a
toolkit equivalent exists. Most are 1–3 lines, the rest are larger
because they were ported before the toolkit equivalents landed.

### Raw widget → toolkit equivalent (low-friction migrations)

| File | Raw widget(s) | Toolkit replacement |
|---|---|---|
| `cpp/app/shell/bootstrap.cpp` | `QSlider` (split slider), `QLabel` (footer resolution / PSNR / SSIM / filenames) | `sli::toolkit::Slider`, `sli::toolkit::Label` |
| `cpp/app/shell/custom_window.cpp` | `QLabel` (window title) | `sli::toolkit::Label` |
| `cpp/app/ui/widgets/form_controls.cpp` | `QPushButton` × 5, `QLineEdit` × 3, `QLabel` × 3 — **whole file is raw Qt** | `sli::toolkit::Button`, `CustomLineEdit`, `Label` |
| `cpp/app/ui/widgets/zoom_indicator.cpp` | `QLabel`, `QPushButton` (reset) | `Label`, `Button` |
| `cpp/app/ui/widgets/startup_placeholder.cpp` | `QLabel` × 2 | `Label` |
| `cpp/app/tabs/export/tab.cpp` | `QLabel`, `QLineEdit` (path / status) | `Label`, `CustomLineEdit` |
| `cpp/app/tabs/multi_compare/tab.cpp` + `sections/*.cpp` | `QLabel` (status + headers), `QSlider` in `comparison_controls_section.cpp` | `Label`, `Slider` |
| `cpp/app/tabs/video_editor/sections/preview_section.cpp` | `QLabel`, `QSlider`, `QToolButton` × 3 | `Label`, `Slider`, `Button` (icon variant via `Config`) |
| `cpp/app/tabs/video_editor/sections/timeline_section.cpp` | `QSlider` × 4 (timeline scrubbers) | `Slider` |
| `cpp/app/tabs/video_editor/sections/export_section.cpp` | `QLabel`, `QLineEdit` × 5 (input/output paths, status) | `Label`, `CustomLineEdit` |
| `cpp/app/tabs/video_editor/sections/project_section.cpp` | `QLabel`, `QLineEdit` × 2 (bitrate / output) | `Label`, `CustomLineEdit` |
| `cpp/app/tabs/video_editor/sections/recording_section.cpp` | `QLabel` (recording status) | `Label` |
| `cpp/app/tabs/video_editor/tab.cpp` | `QLineEdit` × 2 (project input field) | `CustomLineEdit` |
| `cpp/app/plugins/settings/pages/general_page.cpp` | `QLabel` × 2 (inline field labels) | `Label` |
| `cpp/app/plugins/settings/pages/performance_page.cpp` | `QLabel` × 5 (inline field labels) | `Label` |
| `cpp/app/plugins/help/dialog.cpp` | `QLabel` (header) | `Label` |

The pattern: section controllers/composers were migrated to toolkit
for the «interactive» widgets (Button, ComboBox, SpinBox, CheckBox,
GroupBox, Slider in some cases) but inline `QLabel` and `QLineEdit`
constructions were left as plain Qt. This is a per-file mechanical
sweep — each migration is a 1–3 line change and there is no behavior
risk; the failure mode is a label/field that doesn't pick up theme
tokens.

### Stays raw — no toolkit equivalent yet

| File | Raw widget | Why |
|---|---|---|
| `cpp/app/shell/bootstrap.cpp` | `QTabBar` workspace tabs + `+` button | C++ port has no `AdaptiveTabStrip` (Python's tab strip). Tracked in this doc's «suspect» list. |
| `cpp/app/plugins/settings/dialog.cpp`, `cpp/app/plugins/help/dialog.cpp` | `QDialog` (base class) | C++ toolkit has no `DialogShell`. Python wraps both in the toolkit. |
| `cpp/app/shell/custom_window.cpp` | `QToolButton` × 3 (min / max / close window controls) | Custom paint (`WindowControlButton`) with hover animation; the toolkit's `Button` doesn't expose the same hover-tint animation hook. Could be migrated once the paint pipeline exposes a hover-bg-animation layer. |
| `cpp/app/tabs/video_editor/sections/preview_section.cpp` | `QToolButton` × 3 (zoom / pan / rotate transport) | Same hover-color pattern. |

### Inline TODO / «placeholder» / «not yet wired» markers

Comment audit across `cpp/app/` (excluding tests / docs):

1. `cpp/app/shell/bootstrap.cpp:5` — «workspace tabs bar (Image
   Compare 1, +)         [placeholder]». Linked to AdaptiveTabStrip
   gap above.
2. `cpp/app/shell/bootstrap.cpp:13–14` — «plugin TabRegistry tabs
   (collapsed below — kept reachable until plugin surfaces migrate
   into save dialog / video editor flyout)». Hidden `QTabWidget` host
   is constructed only to drive `bindServices` lifecycles.
3. `cpp/app/shell/bootstrap.cpp:117` — workspace `+` button
   `setEnabled(false)` because «multi-session not wired yet».
4. `cpp/app/shell/bootstrap.cpp:159–161` — «Both image buttons
   currently open the same file-pair dialog — per-slot loading needs
   Rust store wiring that's not exposed in C++ yet.»
5. `cpp/app/shell/bootstrap.cpp:241–248` — `pasteOverlay` is an
   orphan `Button(toggle=true)` kept alive only so existing controller
   wiring stays connectable; it's `hide()`-d and never reachable from
   the UI.
6. `cpp/app/tabs/multi_compare/grid.h:23–26` — «Per-cell composition,
   drag/drop transport, and the full GL grid widget remain
   Python-side until the dedicated grid renderer lands; the v1
   implementation here delivers the user-visible playlist + composite
   export contract end-to-end.» This is the largest still-Python
   shape inside the C++ app.
7. `cpp/app/tabs/video_editor/tab.cpp:6` — comment references
   «decomposition Python-side» — the video-editor flyout itself is
   here but tracks Python's section split.
8. `cpp/app/CMakeLists.txt:20` — comment about «Feature flyouts» that
   `form_controls` / `zoom_indicator` / `startup_placeholder` are
   still mirrored from Python verbatim (and thus still on raw Qt
   widgets, see the migration table above).

None of the above are silent stubs — every comment names the
prerequisite that's blocking it. The two structural prerequisites
that would close most of them are:

- A C++ `AdaptiveTabStrip` (closes #1, #3 and removes the
  `QTabBar`/`QPushButton+` fallback from `buildWorkspaceTabsBar`).
- A C++ `DialogShell` (closes the `QDialog` base in settings + help).

## Cross-language parity tester

`tests/parity/cases.json` + `tests/parity/python_renderer.py` +
`cpp/toolkit/tests/parity_renderer.cpp` + `tests/parity/run_parity.py`.
Both renderers consume the same case dict, build a widget, force a
state, paint into a PNG at the same canvas size with offscreen Qt and
identical font/theme. The Python side uses `sli_ui_toolkit` (the
reference); the C++ side uses `sli::toolkit`. The driver pixel-diffs
the pair per case; any sustained mean-diff above the per-case
threshold is a port divergence (both sides are Qt6, so platform
artefacts cannot mask).

Registered as ctest `parity_corpus`. Seeded with **13 visual cases**
(Button × {default, hover, pressed, checked, focused, disabled,
toggle on/off, size, corner_radius, variant, underline}) and **6
functional query cases** (focusPolicy, hasExplicitCursor, isCheckable
true/false, sizeHint width, ripple active after press).

### Divergences the parity tester already caught

When the tester first ran, it immediately surfaced four real port
gaps **without changing a line of test code**:

1. **No `setFixedSize` in `Button(Config)`**. Python's
   `Button(size=(80,32))` calls `setFixedSize`. The C++ `Config` ctor
   only set `setMinimumHeight`. The `button_size_param_drives_sizeHint`
   query failed on the C++ side with width=32. — *Fixed.*
2. **Default `setCursor(Qt::PointingHandCursor)`** in the Button ctor
   when Python never sets a cursor. The
   `button_default_has_no_cursor_override` query failed. — *Fixed.*
3. **Ripple never fires.** `RippleLayer` read a `_ripple` widget
   property nobody ever set; controller's `runtime.ripple` stayed
   `nullptr`; `Button::mousePressEvent` never called `trigger()`.
   The `button_ripple_active_after_press` query failed. — *Fixed.*
4. **Checked-state background colour** wildly off: Python paints a
   subtle grey checked variant, the C++ port paints a bright blue
   panel. Root cause: C++ `Theme` defined
   `button.dialog.default.background.checked = accent` while Python's
   palette deliberately omits that token so the resolver falls back to
   `.background.pressed`. — *Fixed* (token removed from light and
   dark trees).
5. **`Button::sizeHint` formula diverged.** Python: `w = textW +
   iconW + 24`, `h = max(32, fontHeight + 16)`. C++ port:
   hard-coded `max(44, textW + 24)` width floor and `shape.height =
   36`. Caught by the lingering visual diff on the checked case after
   the colour token fix. — *Fixed* — sizeHint now mirrors Python
   1:1.

The point of (4) is that it proves the parity tester is doing its
job: it found a regression that no unit test was specifically looking
for, just because the rendered pixels disagreed.

## Cross-link

- `docs/dev/CPP_PORT_HARDENING.md` — track D «toolkit depth port»
  section can now be promoted back to «done» for items #1–#6: paint,
  region content, toggle propagation, and the ergonomic ctor are
  ported one-to-one with Python. The remaining gap is the smoke-test
  pass for the «suspect» capabilities listed above.

---

# Combobox port audit (2026-06-22)

Side-by-side comparison of Python `sli_ui_toolkit/ui/widgets/comboboxes/`
against C++ `cpp/toolkit/src/comboboxes/` and `cpp/toolkit/include/sli/toolkit/comboboxes/`.

## Files checked

| Python | C++ | Verdict |
|---|---|---|
| `combo_box.py` (571 LOC) | `combo_box.h` (19 LOC) + `combo_box.cpp` (44→71 LOC, fixed this pass) | ❌ ARCHITECTURE — Python inherits `Button`; C++ inherits `QComboBox` |
| `_models.py` (15 LOC) | `models.h` + `models.cpp` (29 LOC) | ✅ faithful port |
| `_search.py` (78 LOC) | `search.h` + `search.cpp` (117 LOC) | ✅ faithful port (NFKD + casefold + match scoring 1:1) |
| `_overlay.py` (341 LOC) | `overlay.h` + `overlay.cpp` (218 LOC) | ⚠️ simplified — no MinimalistScrollBar, no slot pool, no shadow, no GAP handling |
| `scrollable_combobox.py` (225 LOC) | `scrollable_combo_box.h` (67 LOC, expanded) + `scrollable_combo_box.cpp` (155→265 LOC, expanded this pass) | ⚠️ improved — added debounce, auto-width, signals, theme tokens; still inherits `QWidget` instead of `Button` |

## Fixed this pass

### `combo_box.cpp`
- **RADIUS**: 8 → 6 (matches Python)
- **Text padding**: 10/28 → 12/(14+14) (matches Python's `TEXT_HORIZONTAL_PADDING=12` + arrow margin)
- **Arrow**: path → polyline, coordinates `(cx-4, cy-1), (cx, cy+2), (cx+4, cy-1)` (matches Python)
- **Border**: accent-on-focus → always `input.border.thin` token, 1.0 width (matches Python)
- **Background**: `colors.base`/`colors.hover` → `dialog.input.background`/`list_item.background.hover` theme tokens (matches Python's `_ComboFieldBgLayer`)

### `scrollable_combo_box.h/.cpp`
- **Height**: 30 → 33 (matches Python's `size=(0, 33)`)
- **Arrow**: filled triangle → polyline matching ComboBox (matches Python's `_ComboContentLayer`)
- **Text padding**: 8/24 → 12/28 (matches Python)
- **Added**: `currentTextChanged` signal emission in `setCurrentIndex`
- **Added**: `wheelScrolledToIndex` signal + debounce timer (300ms, matches Python)
- **Added**: `setAutoWidthEnabled`, `adjustWidthToContent` (matches Python)
- **Added**: `setText`, `updateState`, `getItemFont`, `getItemHeight` methods (matches Python API surface)
- **Added**: `changeEvent` for font changes (matches Python)
- **Added**: `count()` accessor
- **Removed**: `setCursor(Qt::PointingHandCursor)` — Python doesn't set cursor
- **Wheel**: clamp → modulo wrapping (matches Python behavior)

### Theme tokens added
- `dialog.input.background` — light: `#ffffff`, dark: `#3c3c3c`
- `list_item.background.hover` — light: `#f0f0f0`, dark: `#484848`
- `input.border.thin` — light: `#c8c8c8`, dark: `#555555`
- `flyout.background` — light: `#ffffff`, dark: `#3c3c3c`
- `flyout.border` — light: `#d0d0d0`, dark: `#555555`

### `overlay.cpp`
- **Paint**: raw `Palette` members → theme tokens (`flyout.background`, `flyout.border`, `dialog.text`, `list_item.background.hover`)
- **Hover row**: `fillRect` → rounded rect with RADIUS=6 (matches Python's `_SlotBgLayer`)
- **Overlay radius**: 6 → 8 (matches Python's `RADIUS = 8`)

## Remaining gaps (not fixed — architectural)

### `combo_box.h/cpp` — needs full rewrite
Python's `ComboBox` inherits from `Button` (custom widget with layered painter pipeline, ripple, theme tokens, capabilities). C++ inherits from `QComboBox` (Qt's stock widget). This is not a «fix the constants» problem — the entire architecture must be rewritten to match Python.

**What's missing** (35 methods flagged by `check_structure.py`):
- All item management: `addItem`, `addItems`, `insertItem`, `removeItem`, `clear`, `count`, `items`, `itemText`, `itemData`, `findText`, `findData`, `setItemText`, `setItemData`
- Search: `setSearchEnabled`, `isSearchEnabled`, `searchText`, `clearSearch`, `_set_search_text`
- Dropdown: `showDropdown`, `hideDropdown`, `_ensure_overlay`
- Keyboard: `keyPressEvent` with text-based search, `_move_visible_selection`
- Focus: `focusOutEvent`, `eventFilter` (window move/resize/deactivate/click-outside)
- Scroll: `_scroll_offset`, `_max_visible_items`, `setMaxVisibleItems`, `maxVisibleItems`, `_ensure_current_visible`
- Layout: `sizeHint`, `minimumSizeHint`, `_content_width_hint`, `setMinimumContentsLength`
- Data: `currentData`, `setCurrentData`, `setCurrentText`

**Effort estimate**: 571 LOC Python → ~500 LOC C++ (chunked: 5 sessions of ~100 lines each)

### `_overlay.py` — missing scrollbar, slot pool, shadow, geometry
Python's `_DropdownOverlay` is 341 LOC with:
- `MinimalistScrollBar` integration (scrollbar sync, mouse event forwarding)
- Slot pool (`_DropdownItemSlot` × maxVisibleItems) for virtual scrolling
- Shadow rendering (`draw_rounded_shadow`, SHADOW=10)
- Anchor-aware positioning (`calculate_centered_overlay_geometry`)
- Window resize/move tracking (reposition via ComboBox.eventFilter)

C++ overlay is a basic popup with search — functional but visually incomplete.

**Effort estimate**: requires C++ `MinimalistScrollBar` (not yet ported) + ~200 LOC overlay expansion

### `ScrollableComboBox` — still inherits QWidget, not Button
The expanded C++ version (this pass) adds the missing methods, signals, debounce, and auto-width. But it still inherits `QWidget` instead of `Button` — meaning it doesn't benefit from the Button painter pipeline (BackgroundLayer, RippleLayer, theme variant system, capability composition). Python's `ScrollableComboBox` gets hover/pressed background, ripple on click, and consistent theme token resolution from the Button base class.

**Effort estimate**: once `combo_box` is rewritten on Button base, `scrollable_combo_box` can be ported similarly (~150 LOC delta)

## What was NOT checked yet

- **SpinBox** — `atomic/spinbox.py` → `cpp/toolkit/src/atomic/spin_box.cpp`
- **CheckBox** — `atomic/checkbox.py` → `cpp/toolkit/src/atomic/check_box.cpp`
- **RadioButton** — `atomic/radio.py` → `cpp/toolkit/src/atomic/radio_button.cpp`
- **Slider** — `atomic/slider.py` → `cpp/toolkit/src/atomic/slider.cpp`
- **Switch** — `atomic/switch.py` → `cpp/toolkit/src/atomic/switch.cpp`
- **Label / TextLabels** — `atomic/text_labels.py` → `cpp/toolkit/src/atomic/text_labels.cpp`
- **LineEdit** — `atomic/custom_line_edit.py` → `cpp/toolkit/src/atomic/custom_line_edit.cpp`
- **GroupBox** — `atomic/custom_group_widget.py` → `cpp/toolkit/src/atomic/group_box.cpp`
- **LoadingSpinner** — `atomic/loading_spinner.py` → `cpp/toolkit/src/atomic/loading_spinner.cpp`
- **DropZoneLabel** — `atomic/drop_zone_label.py` → `cpp/toolkit/src/atomic/drop_zone_label.cpp`
- **Toolbar** — `composite/toolbar.py` → `cpp/toolkit/src/composite/toolbar.cpp`
- **ChipGroup** — `buttons/button_group.py` (chip variant) → `cpp/toolkit/src/buttons/chip_group.cpp`
- **SectionHeader** — Python equivalent → `cpp/toolkit/src/atomic/section_header.cpp`
- **Divider** — Python equivalent → `cpp/toolkit/src/atomic/divider.cpp`

## Priority order for next audit

1. **atomic widgets used in app shell**: Slider (bootstrap.cpp split slider), Label (everywhere), LineEdit (form_controls.cpp)
2. **GroupBox** — used by settings pages and video editor sections
3. **CheckBox / RadioButton** — used by settings pages
4. **SpinBox** — used by video editor sections
5. **Toolbar / ChipGroup** — used by comparison toolbar

---

# Button port audit (2026-06-22)

Side-by-side comparison of Python `buttons/button.py` (709 LOC) against
C++ `buttons/button.h` (119→147 LOC, expanded) + `buttons/button.cpp` (524→590 LOC, expanded this pass).

## Fixed this pass

### `corner_radius` derivation
- **Before**: hard-coded `ctx.cornerRadius = 6` for all buttons
- **After**: `ctx.cornerRadius = 2` for text buttons, `6` for icon-only (matches Python line 255-257: `corner_radius = 2 if self._has_text else 6`)

### Theme change connection
- **Before**: no connection — buttons didn't repaint on light ↔ dark switch
- **After**: `Theme::onThemeChanged(this, [this] { update(); })` in both constructors (matches Python line 305: `theme_manager.theme_changed.connect(self.update)`)
- **Infrastructure**: added `Theme::onThemeChanged(QObject*, callback)` static method + callback cleanup on owner destruction

### `Config` struct expanded
Added 5 missing fields matching Python's `ButtonConfig`:
- `cornerRadius` — overrides default 2/6
- `borderColor` — overrides theme border
- `density` — "normal" | "compact"
- `wheelRequiresFocus` — matches Python's `wheel_requires_focus`
- `deferClick` — matches Python's `defer_click`

### Size policy for text buttons with default size
- **Before**: `setFixedSize(36, 36)` for text buttons with default config
- **After**: text buttons with default (36,36) get `setMinimumHeight(32)` + `Fixed` policy (matches Python lines 291-293)

### Signals added (8 new signals)
- `pressed()`, `released()` — emitted in mousePressEvent/mouseReleaseEvent
- `rightClicked()`, `middleClicked()` — emitted on right/middle button press
- `valueChanged(int)` — emitted by setValue()
- `regionPressed(QString)`, `regionReleased(QString)` — per-region press/release

### Scroll API
- `setValue(int val)` — clamped setter with signal emission
- `value()` — getter
- `setRange(int minV, int maxV)` — range setter matching Python

### Config wiring for new fields
- `config.cornerRadius` → `shape.cornerRadius` in ShapeSpec + context propagation in paintEvent
- `config.borderColor` → `region.overrideBorderColor`
- `config.density` → `args.density`
- `config.wheelRequiresFocus` → `args.wheelRequiresFocus`
- `config.deferClick` → `args.deferClick`
- `config.scrollable` now initializes `scrollMin_`, `scrollMax_`, `scrollValue_`

## Remaining gaps (not fixed)

### `_build_content` widget-scope logic — simplified
Python's `_build_content` (line 570-580) checks `self._rows`, `self._rows_compact`, dual icons (`_icon_unchecked`/`_icon_checked`), and returns `RowsContent`/`IconTextContent`/`TextContent`/`IconContent`. C++ uses `buildContentFromRegion(regions.front())` which only does region-level content. Widget-scope rows and dual-icon support are missing.

### `iter_regions` multi-region paint
Python's `iter_regions` yields scoped contexts for every region with per-region states, content, variant, colors. C++ paintEvent only handles single-region in the widget-scope path. Multi-region buttons (split buttons) may not render correctly.

### `_state_property` / `_hovered`, `_pressed`, `_checked`, `_is_scrolling`
Python has property wrappers that mutate StateSet and call update(). C++ uses QAbstractButton's built-in checked/hover/pressed — close but not identical semantics.

### `setChecked` gating on `_has_toggle`
Python won't emit toggled if `!_has_toggle`. C++ QAbstractButton always emits. Only affects programmatic toggle calls.

### `_do_toggle_scroll_click` — missing entirely
Python's combined toggle+scroll click behavior (save/restore scroll value on toggle) is not ported.

### `attach_capability` / `detach_capability` / `get_capability` — simplified
Python has a full capability registry with per-type-per-region dedup. C++ has a flat vector.

### Missing signals
- `regionToggled(str, bool)`, `regionValueChanged(str, int)`, `regionLongPressed(str)`, `regionMenuTriggered(str, object)`, `actionTriggered(str, object)`

## Files touched

| File | Change |
|---|---|
| `cpp/toolkit/include/sli/toolkit/buttons/button.h` | +28 lines: Config fields, signals, scroll API, members |
| `cpp/toolkit/src/buttons/button.cpp` | +66 lines: corner_radius, theme connect, size policy, signals, scroll API |
| `cpp/toolkit/include/sli/toolkit/theme.h` | +5 lines: onThemeChanged API |
| `cpp/toolkit/src/theme.cpp` | +27 lines: onThemeChanged impl + callback fire in apply() |

## Verification

```bash
cmake --build cpp/build -j2      # ✅ green
ctest --test-dir cpp/build       # ✅ 11/11 pass (incl. parity_corpus)
cargo test --workspace           # ✅ 138 pass
```

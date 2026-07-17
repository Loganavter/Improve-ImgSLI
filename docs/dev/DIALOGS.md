# App Dialogs / Windows

How to build modal dialogs in Improve-ImgSLI. This guide reflects hard-won rules
from the export dialog work (geometry, CSD chrome, i18n, crush-resistant layouts).

Reference implementation: `src/plugins/export/` (`dialog.py`, `layout_geometry.py`, `dialog_sections.py`).

Related:

- [UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md) — toolkit widgets / painters
- [THEMING.md](THEMING.md) — palettes, QSS, `polish_themed_dialog`
- [RESOURCES_I18N.md](RESOURCES_I18N.md) — translation packs and roots
- Toolkit CSD: `sli_ui_toolkit.ui.windows` (`decorate_dialog`, rounded mask)

---

## Skeleton

```text
ThemedDialog
  ├─ build widget tree (_init_ui)
  ├─ bind i18n (translatable_* / _tr_func — never shadow QObject.tr)
  ├─ install_dialog_geometry(apply_fn)
  ├─ mark_theme_ui_ready()
  ├─ decorate_dialog(...)          # CSD title bar + rounded body
  ├─ populate / suggest defaults
  └─ QTimer.singleShot(0, finalize)  # geometry after polish / CSD margins
```

Minimal ctor pattern:

```python
class MyDialog(ThemedDialog):
    def __init__(self, ..., tr_func=None):
        super().__init__(parent)
        self._tr_func = tr_func if callable(tr_func) else app_tr
        self._init_ui()
        self._bind_translations()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        self.mark_theme_ui_ready()
        decorate_dialog(self, title=self._tr("...", "Fallback"))
        # ... populate ...
        QTimer.singleShot(0, self._finalize_layout_and_size)

    def _tr(self, key: str, default: str | None = None) -> str:
        text = self._tr_func(key, self._language)
        if text == key and default is not None:
            return default
        return text

    def _apply_dialog_geometry(self) -> None:
        apply_my_dialog_geometry(self)

    def _finalize_layout_and_size(self) -> None:
        apply_my_dialog_geometry(self, force_resize=True)
        sync_csd_chrome(self)  # rebuild rounded mask after programmatic resize
```

Use toolkit controls (`Button`, `CheckBox`, `ComboBox`, …) and the painter pipeline.
Do **not** style toolkit widgets with `setStyleSheet`.

---

## Geometry recipe

Keep sizing in a per-dialog module: `plugins/<name>/layout_geometry.py`.

1. **Primitives** (`shared_toolkit/ui/layout_sizing.py`) —
   `widget_*_hint`, `sum_visible_widget_height_hint`, `max_visible_widget_width_hint`,
   `clamp` / `clamp_to_screen`, `HorizontalPaneMinimum`.
2. **Recipe** — combine primitives with dialog-specific margins / floors.
3. **Apply** — `apply_dialog_geometry(..., policy=GeometryApplyPolicy(...))`.
4. **Lifecycle** — after build (`singleShot(0, …)`), and on language / theme / font
   via `install_dialog_geometry` / `ThemedDialog`.

### Measurement rules

- Prefer **`isHidden()`** over **`isVisible()`** when deciding whether a child
  counts toward size. While the parent dialog is still hidden, children report
  `isVisible() == False` even when they are not explicitly hidden — pre-show
  sizing would under-count and crush controls after show.
- For a **stacked form**, sum row heights (`sum_visible_widget_height_hint`).
  Never take `max()` of one row as the form height.
- Include CSD title-bar height and layout margins in the total. Title bar is
  overlaid; `decorate_dialog` bumps the layout top margin by
  `CustomTitleBar.HEIGHT`.

### `GeometryApplyPolicy`

| Flag | When |
|------|------|
| `lock_minimum_to_computed=True` | Non-scroll dialogs (export). User must not shrink below content. |
| `lock_minimum_to_computed=False` | Scroll shells (settings). Keep a low floor; pages scroll. |
| `force_resize=True` | **Initial** finalize only. CSD `adjustSize` often overgrows from pixmap / sizeHints; without force, a visible dialog only raises `minimumSize` and never shrinks back — constants like preview min width look “broken”. |
| `force_resize=False` | Later updates (format toggle, language) so a user-grown window is not reset. |

Also pin `QWindow.setMinimumSize` after apply when a handle exists — Wayland/X11
CSD `startSystemResize` often ignores `QWidget` minimum alone.

---

## Layout that survives height squeeze

Vertical `Preferred` children **shrink below content** and clip Fixed-height
buttons (Browse / favorite / OK / Cancel). Defense in depth:

1. Critical blocks: vertical **`Minimum`** or **`Fixed`** (path section, action bar).
2. Pin height with `lock_content_minimum_height()` after text/hardening.
3. Let **preview / stretch** absorb pressure — soft preview min height, not a
   hard 300×300 that competes with the form.
4. Do **not** `setMinimumHeight(full_form_content)` on the form frame. A hard
   form min makes the form overflow the window when the WM ignores dialog
   minimum → OK/Cancel clip at the bottom. Prefer layout-driven minimum +
   stretchable gaps.
5. Distribute extra height with **several equal `addStretch(1)`** between
   sections, not one blob above the action bar. Keep label→field pairs tight
   (no stretch between them). Use `addSpacing(N)` where a section needs a
   larger **minimum** gap (e.g. filename → format).

Text buttons:

- Create toolkit `Button`s with **real text** (empty → `setText` clears minimum
  width and collapses buttons).
- Do **not** `setFixedHeight(32)` on text buttons — toolkit hint is often
  `fontMetrics.height() + 16` and a tighter fixed height clips the bottom edge.

---

## Preview panes and pixmap sizeHints

`QLabel.setPixmap` makes `sizeHint()` follow the pixmap. After CSD
`adjustSize`, the dialog can jump to hundreds of pixels of preview width and
ignore your `EXPORT_PREVIEW_*` constants.

Fix:

- Use a small label subclass whose `sizeHint` / `minimumSizeHint` return the
  configured minimum (see `_ExportPreviewLabel` in export `dialog_sections.py`).
- In the geometry recipe, **do not** feed `export_preview_frame` /
  `preview_label` width hints into the dialog minimum — only the constant
  (and maybe the title label text width).
- Read constants via the **module** (`export_geo.EXPORT_PREVIEW_MIN_WIDTH`),
  not a copied `from … import CONST` binding, if you expect live edits during
  development.

---

## CSD / custom decorations

`decorate_dialog` installs:

- frameless window + `WA_TranslucentBackground`
- `CustomTitleBar` overlay
- `CsdRoundedBackground` child
- rounded **mask** on the shell

### Transparent “zagagulina” (corner arc through the body)

Symptoms: a curved transparent hole that matches the window radius; often
fixes itself after a manual resize; more common on dialogs that **resize a
lot after** `decorate_dialog` (export).

Causes:

1. Mask left on a **pre-resize** silhouette while the widget grew.
2. HiDPI-unsafe `QBitmap` masks (fixed in toolkit: device-pixel bitmap with
   matching `devicePixelRatio`, dense polygon fallback).

### Jagged / staircased corners

`QWidget.setMask` is binary — it destroys the antialiased edge painted by
`CsdRoundedBackground` / title-bar `paintEvent`. Shell and title bar must
**not** carry a full rounded mask; only opaque child hosts that reach the
edge (main-window content stack, window-control cluster) use a dense
HiDPI-safe mask. Always call `sync_csd_chrome(dialog)` after programmatic
geometry changes and on first show (export also defers one more sync on
`QTimer.singleShot(0, …)`).

Implementation: `sli_ui_toolkit.ui.windows.csd_helpers.sync_csd_chrome`.

---

## i18n

- **Never** assign `self.tr = …` — that shadows `QObject.tr` and makes UI show
  raw keys or worse.
- Prefer `self._tr_func` / `_tr(key, default)` and toolkit
  `translatable_text` / `translatable_tooltip`.
- Plugin packs: `add_i18n_root` must **rebuild the live `_translations` pack**,
  not only clear the cache. Otherwise `tr("export.*", language=current)` keeps
  returning the key until the next language switch.
- Re-apply / harden button minimums after language changes (text width changes).

---

## Checklist for a new dialog

1. Subclass `ThemedDialog`; wire geometry + `mark_theme_ui_ready` + `decorate_dialog`.
2. Add `layout_geometry.py` with constants, `compute_*`, `apply_*`, and a clear
   `GeometryApplyPolicy` (scroll vs content-locked; initial `force_resize`).
3. Measure with `isHidden`-aware helpers; stack heights with **sum**, not max.
4. Protect crush-sensitive rows (`Minimum`/`Fixed` + lock height); distribute
   vertical stretch across section gaps.
5. If there is a pixmap preview: cap `sizeHint`, exclude preview frame width
   from the minimum recipe, sync CSD chrome after resize.
6. Own i18n root + defaults; never shadow `tr`; re-harden controls on language.
7. Add a focused regression test under `tests/runtime/` or `tests/plugins/`
   for the sizing invariant you care about (stack height, force_resize,
   path/action bar survival under height squeeze, preview min not driven by
   pixmap hint).

---

## Anti-patterns

| Don’t | Do instead |
|-------|------------|
| `max(row_heights)` as form height | `sum_visible_widget_height_hint` |
| Trust `isVisible()` pre-show | `isHidden()` / contribute helpers |
| One `addStretch` above OK only | Equal stretches between sections |
| Form `setMinimumHeight(full content)` | Layout min + stretch; lock children |
| Geometry apply on visible without `force_resize` after CSD overgrow | Initial `force_resize=True` |
| Feed pixmap `sizeHint` into dialog min width | Constant + title hint only |
| Skip `sync_csd_chrome` after resize | Sync mask/bg/title bar |
| `self.tr = custom` | `_tr_func` / `_tr` |
| `Button("")` then `setText` | Create with real text |
| `setFixedHeight(32)` on toolkit text buttons | `setMinimumSize` from `sizeHint` |

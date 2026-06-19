# UI Inspector

Developer-only inspector for PyQt widgets, QSS candidates, palette roles, and
theme-token color lookup.

## Goal

Provide an in-app visual tool for answering:

- what widget is under the cursor
- which object name, class name, and dynamic properties identify it
- which `QPalette` colors it currently exposes
- which theme tokens match those colors
- which registered QSS rules are likely candidates for the widget

The inspector is a diagnostic tool. It is not a user-facing feature and should
not be documented in in-app Help.

## Launch

```bash
./launcher.sh run --ui-inspector
./launcher.sh --ui-inspector
```

The launcher forwards `--ui-inspector` to `src/__main__.py`. The Python entry
point stores it in runtime flags and enables the inspector after the main UI is
bootstrapped.

## Wayland Constraints

The inspector must avoid desktop-global overlay behavior. Wayland compositors do
not allow the same global pointer and transparent top-level-window assumptions
that X11 tools often use.

Implementation rules:

- use an in-process child overlay parented to the main window
- do not create a transparent always-on-top top-level window over the desktop
- do not grab the global mouse or keyboard
- do not depend on reading pixels outside the application
- use Qt event filters and widget geometry inside the app window
- keep highlight overlays parented to the inspected application window; the
  details panel may be a normal opaque tool window because it is not a desktop
  capture/transparent overlay

This keeps hover highlighting reliable on Wayland and avoids compositor-specific
behavior.

## Architecture

Files live under:

```text
src/devtools/ui_inspector/
  installer.py
  controller.py
  overlay.py
  panel.py
  qss_index.py
  widget_snapshot.py
```

Responsibilities:

- `installer.py` wires the inspector into a running `QApplication` and
  `MainWindow`.
- `controller.py` handles keyboard/mouse events, `Shift+LeftClick` selection,
  per-window highlight overlays, and ignores inspector-owned widgets.
- `overlay.py` draws the highlight rectangle and compact label inside the
  inspected application window.
- `panel.py` shows the selected widget details and copy actions in a separate
  opaque tool window, so dialogs and plugin windows remain inspectable.
- `widget_snapshot.py` collects widget identity, palette, inline style sheet,
  dynamic properties, parent path, and theme-token matches.
- `qss_index.py` reads registered QSS files and returns likely selector
  candidates. Qt does not expose browser-like computed CSS origins, so these
  rules are shown as candidates, not guaranteed matched rules.

## Initial Feature Set

1. Add `RuntimeFlags(debug, ui_inspector)`.
2. Add launcher and argparse support for `--ui-inspector`.
3. Install the inspector after `MainWindowStartupRuntime.bootstrap_main_app()`.
4. Select and highlight a widget on `Shift+LeftClick`.
5. Keep the details panel outside the inspected widget tree.
6. Show a floating panel with widget identity, palette roles, theme-token
   matches, inline style sheet, dynamic properties, and QSS candidates.
7. Add focused tests for snapshot collection and QSS candidate lookup.

## Future Canvas Inspector

The QWidget inspector is intentionally separate from canvas/render diagnostics.
Canvas elements are often GL passes or `QPainter` drawings rather than Qt
widgets. A later canvas tab can inspect render passes, feature payloads, and
store-backed colors around the cursor.

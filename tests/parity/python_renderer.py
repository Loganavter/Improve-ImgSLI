"""Python side of the cross-language widget parity harness.

Same shape as ``cpp/toolkit/tests/parity_renderer.cpp``: reads a JSON case id,
builds a widget via ``sli_ui_toolkit``, forces the requested state, and
either renders to PNG or prints a query value. Driven by ``run_parity.py``.

The Python toolkit is the reference. Any pixel difference vs. the C++ side
is a port divergence.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

# Force offscreen before importing Qt so the harness works without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt
from PySide6.QtGui import (
    QFocusEvent,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import Button
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState


# ---------- factory ----------

def _build_button(config: dict, parent: QWidget) -> Button:
    kwargs: dict[str, Any] = {"parent": parent}
    if "text" in config:
        kwargs["text"] = config["text"]
    if "variant" in config:
        kwargs["variant"] = config["variant"]
    if "size" in config:
        kwargs["size"] = tuple(config["size"])
    if "icon_size" in config:
        kwargs["icon_size"] = config["icon_size"]
    if "toggle" in config:
        kwargs["toggle"] = config["toggle"]
    if "scrollable" in config:
        kwargs["scrollable"] = tuple(config["scrollable"])
    if "long_press_ms" in config:
        kwargs["long_press"] = True
        kwargs["long_press_ms"] = config["long_press_ms"]
    if "show_underline" in config:
        kwargs["show_underline"] = config["show_underline"]
    if "corner_radius" in config:
        kwargs["corner_radius"] = config["corner_radius"]
    if "background_color" in config:
        from PySide6.QtGui import QColor
        kwargs["background_color"] = QColor(config["background_color"])
    return Button(**kwargs)


# ---------- state forcing ----------

def _apply_state(btn: Button, state: str) -> None:
    if state == "default":
        return
    if state == "hover":
        # Mirror the C++ side: set the controller _main region into Hovered
        # directly. Synthesizing mouseMoveEvent under offscreen is flaky.
        btn._controller.set_state("_main", ButtonState.HOVERED, True)
        return
    if state == "pressed":
        btn._controller.set_state("_main", ButtonState.PRESSED, True)
        return
    if state == "checked":
        btn.setChecked(True)
        return
    if state == "focused":
        btn.setFocus()
        QApplication.sendEvent(btn, QFocusEvent(QEvent.FocusIn, Qt.OtherFocusReason))
        return
    if state == "disabled":
        btn.setEnabled(False)
        return
    raise SystemExit(f"python_renderer: unknown state: {state}")


# ---------- modes ----------

def _render_case(corpus: dict, case_id: str, output: str) -> None:
    case = _find(corpus["cases"], case_id, "cases")
    canvas = tuple(case["canvas"])
    host = QWidget()
    host.resize(*canvas)
    pal = host.palette()
    pal.setColor(QPalette.Window, ThemeManager.get_instance().get_color("Window"))
    host.setAutoFillBackground(True)
    host.setPalette(pal)

    config = case["config"]
    btn = _build_button(config, host)

    if "size" in config:
        btn_size = QSize(*config["size"])
    else:
        btn_size = btn.sizeHint()
    btn.resize(btn_size)
    btn.move((canvas[0] - btn_size.width()) // 2,
             (canvas[1] - btn_size.height()) // 2)

    _apply_state(btn, case.get("state", "default"))

    host.ensurePolished()
    btn.ensurePolished()

    image = QImage(host.size(), QImage.Format_ARGB32_Premultiplied)
    image.fill(ThemeManager.get_instance().get_color("Window"))
    painter = QPainter(image)
    host.render(painter, QPoint(), host.rect(),
                QWidget.DrawWindowBackground | QWidget.DrawChildren)
    painter.end()

    if not image.save(output, "PNG"):
        raise SystemExit(f"python_renderer: failed to write {output}")


def _run_query(corpus: dict, case_id: str) -> None:
    q = _find(corpus["queries"], case_id, "queries")
    config = q["config"]
    query = q["query"]

    host = QWidget()
    host.resize(200, 100)
    btn = _build_button(config, host)

    if query == "focusPolicy":
        fp = btn.focusPolicy()
        print({
            Qt.NoFocus: "NoFocus",
            Qt.TabFocus: "TabFocus",
            Qt.ClickFocus: "ClickFocus",
            Qt.StrongFocus: "StrongFocus",
            Qt.WheelFocus: "WheelFocus",
        }.get(fp, str(fp)))
    elif query == "hasExplicitCursor":
        print("true" if btn.testAttribute(Qt.WA_SetCursor) else "false")
    elif query == "isCheckable":
        # Python's Button is a QWidget, not a QAbstractButton, so it exposes
        # checkable-ness via the internal `_has_toggle` flag.
        print("true" if getattr(btn, "_has_toggle", False) else "false")
    elif query == "sizeHintWidth":
        # Python's Button(size=(w,h)) calls setFixedSize, so the actual
        # instance width equals the configured w. We measure that, not
        # sizeHint, so the assertion is on the user-observable behavior.
        print(int(btn.width()))
    elif query == "rippleActiveAfterPress":
        host.show()
        btn.show()
        btn.resize(40, 40)
        btn._controller.set_state("_main", ButtonState.PRESSED, True)
        ripple = btn.region_ripple("_main")
        if ripple is None:
            print("false")
        else:
            ripple.trigger(QRectF(0, 0, 40, 40).center())
            print("true" if ripple.is_active() else "false")
    else:
        raise SystemExit(f"python_renderer: unknown query: {query}")


def _find(arr: list, case_id: str, section: str) -> dict:
    for c in arr:
        if c.get("id") == case_id:
            return c
    raise SystemExit(f"python_renderer: case id not found in {section}: {case_id}")


# ---------- entry ----------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["render", "query"])
    parser.add_argument("--case", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    cases_path = os.environ.get("IMGSLI_PARITY_CASES")
    if not cases_path:
        raise SystemExit("python_renderer: IMGSLI_PARITY_CASES env var must be set")
    with open(cases_path, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    app = QApplication.instance() or QApplication([])

    # Same fixture as the C++ side — explicit family + size so font rendering
    # is reproducible across machines.
    font = QFont("Sans Serif", 10)
    font.setStyleStrategy(QFont.NoSubpixelAntialias | QFont.PreferAntialias)
    app.setFont(font)

    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    if args.mode == "render":
        if not args.output:
            raise SystemExit("python_renderer: --output required in render mode")
        _render_case(corpus, args.case, args.output)
    else:
        _run_query(corpus, args.case)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

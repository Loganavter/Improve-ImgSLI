"""Recent-card text rows elide instead of crawling (task-session-picker-elide-2026-10-21).

Product decision: an overflowing card row truncates with an ellipsis, the same
way the gallery list already does (`tabs/image_gallery/ui/list/regions.py`), so
idle cards do not run a 60fps marquee driver for a label nobody is reading.

The tests are split deliberately:

* a field pin on the rows the two builders return (cheap, but alone it only
  restates the code);
* a behaviour pin that paints those very rows through the toolkit's real
  resolved draw path and requires the painted pixels to equal a pre-elided
  reference and to differ from the clipped render;
* a widget-level pin that no marquee timer arms / no marquee repaint rect is
  registered for card rows, plus a negative control proving that assertion
  can fail (a deliberately `marquee=True` fixture row still arms it).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtGui import QFontMetrics, QImage, QPainter
from sli_ui_toolkit.managers import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow
from sli_ui_toolkit.ui.widgets.buttons.content import RowsContent
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import MarqueeDriver
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.recent.cards import grid_text_rows, list_text_rows
from ui.widgets.shelf.relative_time import format_relative_opened

# Wider than any row width used below, in a normal UI font.
LONG_NAME = (
    "a_very_long_annotated_project_name_that_cannot_fit_any_card_strip_2026.imgsli"
)
ROW_W = 140
ROW_H = 24


def _tr(key: str, default: str | None = None, *args, **kwargs) -> str:
    return default if default is not None else key


def _record(tmp_path, *, missing: bool = False) -> RecentProjectRecord:
    path = tmp_path / "proj.imgsli"
    if not missing:
        path.write_text("{}")
    return RecentProjectRecord(
        path=str(path),
        display_name=LONG_NAME,
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare", "multi_compare"),
    )


def _overflowing_rows(record: RecentProjectRecord) -> list[tuple[str, list[ButtonRow]]]:
    """(label, rows) for every builder branch; each label holds text rows."""
    return [
        ("grid", grid_text_rows(record, missing=False, translate=_tr)),
        ("grid-missing", grid_text_rows(record, missing=True, translate=_tr)),
        ("list", list_text_rows(record, missing=False, translate=_tr)),
        ("list-missing", list_text_rows(record, missing=True, translate=_tr)),
    ]


# --------------------------------------------------------------------------
# 1. Field pin — every card row is static, overflowing text is elided.
# --------------------------------------------------------------------------


def test_grid_text_rows_elide_and_never_marquee(tmp_path):
    for missing in (False, True):
        record = _record(tmp_path, missing=missing)
        rows = grid_text_rows(record, missing=missing, translate=_tr)
        assert rows, "grid builder returned no rows"
        assert all(row.marquee is False for row in rows)

        title = [row for row in rows if row.text == record.display_name]
        assert title, "title row missing"
        assert title[0].elide is True

        types_text = ", ".join(("Image Compare", "Multi Compare"))
        types_rows = [row for row in rows if row.text == types_text]
        assert types_rows, f"session-types row missing (rows={[r.text for r in rows]})"
        assert types_rows[0].elide is True
        if not missing:
            # Composite "relative time · type" line stays static AND unelided.
            time_row = next(
                row
                for row in rows
                if row.text == format_relative_opened(record.opened_at, _tr)
            )
            assert time_row.marquee is False
            assert time_row.elide is False


def test_list_text_rows_elide_and_never_marquee(tmp_path):
    for missing in (False, True):
        record = _record(tmp_path, missing=missing)
        rows = list_text_rows(record, missing=missing, translate=_tr)
        assert len(rows) == 2
        assert all(row.marquee is False for row in rows)
        assert all(row.elide is True for row in rows)
        assert rows[0].text == record.display_name


# --------------------------------------------------------------------------
# 2. Behaviour pin — the painted pixels are the elided string.
# --------------------------------------------------------------------------


class _Ctx:
    """Minimal DrawContext stand-in for the toolkit's row resolver."""

    def __init__(self, widget, painter) -> None:
        self.widget = widget
        self.painter = painter


def _paint_row(row: ButtonRow, *, width: int = ROW_W) -> tuple[QImage, object]:
    """Paint one row through the real resolved path; return (image, resolved)."""
    host = Button(text="x")
    host.resize(width, ROW_H)
    host.show()
    image = QImage(width, ROW_H, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        resolved = RowsContent._resolve_row(
            row,
            _Ctx(host, painter),
            read_widget_style(host),
            ThemeManager.get_instance(),
            padded_x=0,
            padded_w=width,
            full_x=0,
            full_w=width,
            y=0,
            height=ROW_H,
        )
        RowsContent._draw_resolved(painter, resolved, 0.0)
    finally:
        painter.end()
        host.deleteLater()
    return image, resolved


def test_card_title_paints_the_elided_text_not_a_clipped_or_crawling_one(tmp_path, qapp):
    del qapp
    record = _record(tmp_path)
    title_row = next(
        row
        for row in grid_text_rows(record, missing=False, translate=_tr)
        if row.text == record.display_name
    )
    painted, resolved = _paint_row(title_row)
    assert resolved.marquee_active is False

    metrics = QFontMetrics(resolved.font)
    elided = metrics.elidedText(
        title_row.text, Qt.TextElideMode.ElideRight, resolved.rect.width()
    )
    assert elided.endswith("…")
    assert len(elided) < len(title_row.text)

    reference, _ = _paint_row(
        ButtonRow(
            text=elided,
            size=title_row.size,
            weight=title_row.weight,
            h_align=title_row.h_align,
        )
    )
    clipped, _ = _paint_row(
        ButtonRow(
            text=title_row.text,
            size=title_row.size,
            weight=title_row.weight,
            h_align=title_row.h_align,
            marquee=False,
            elide=False,
        )
    )
    # Elide paints exactly the truncated string (ellipsis glyph included) …
    assert painted == reference
    # … and the pre-change clip rendering is visibly different, so the
    # equality above is not vacuous.
    assert painted != clipped


# --------------------------------------------------------------------------
# 3. Widget-level pin + negative control (marquee driver must stay disarmed).
# --------------------------------------------------------------------------


def _rows_widget(rows: list[ButtonRow]) -> Button:
    host = Button(text="", rows=rows, size=(ROW_W, ROW_H * 2))
    host.resize(ROW_W, ROW_H * 2)
    host.show()
    return host


def _active_marquee_timer(host: Button) -> QTimer | None:
    """The driver's tick timer, if the toolkit armed one for this host."""
    driver = host.findChild(MarqueeDriver)
    if driver is None:
        return None
    for timer in driver.findChildren(QTimer):
        if timer.isActive():
            return timer
    return None


def _marquee_rect(host: Button) -> QRect | None:
    driver = host.findChild(MarqueeDriver)
    return None if driver is None else driver.dirty_rect()


def test_card_rows_arm_no_marquee_driver(tmp_path, qapp):
    record = _record(tmp_path)
    for label, rows in _overflowing_rows(record):
        host = _rows_widget(rows)
        try:
            qapp.processEvents()
            host.grab()
            qapp.processEvents()
            assert _active_marquee_timer(host) is None, f"{label} row is crawling"
            assert _marquee_rect(host) is None, f"{label} row claims a marquee rect"
            assert getattr(host, "_marquee_phase", 0.0) == 0.0
        finally:
            host.close()
            host.deleteLater()


def test_negative_control_marquee_row_still_arms_the_driver(qapp):
    """Proves the assertion above can fail: marquee=True still crawls."""
    host = _rows_widget(
        [
            ButtonRow(
                text=LONG_NAME,
                size=13,
                weight="bold",
                h_align=Qt.AlignmentFlag.AlignLeft,
                marquee=True,
            )
        ]
    )
    try:
        qapp.processEvents()
        host.grab()
        qapp.processEvents()
        assert _active_marquee_timer(host) is not None
        assert _marquee_rect(host) is not None
    finally:
        host.close()
        host.deleteLater()

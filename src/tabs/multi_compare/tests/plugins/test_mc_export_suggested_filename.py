"""Multi Compare export dialog proposes a real filename, not the literal ``multi_compare``.

Owner report (2026-10-28): the save dialog always suggested ``multi_compare``.
Cause: ``use_cases/export.py`` handed ``suggested_filename="multi_compare"``
straight to the host dialog, which prints it verbatim
(``plugins/export/dialog.py`` ``edit_name.setText(self.suggested_filename or
"comparison")``).

Contract under test (``build_suggested_export_filename``): first filled slot's
stem + ``_<N>images`` for N filled slots, 80-character cap that trims the stem
and never the tail, filesystem-hostile characters replaced with ``_``, and the
bare literal ``multi_compare`` only when no slot carries a path or label.

Red-before: the helper does not exist on the pre-change tree, so every import
here fails there; the end-to-end test additionally sees the literal
``multi_compare`` in ``open_export_dialog`` kwargs.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QColor, QImage

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import CompareSlot, LeafNode, SplitNode
from tabs.multi_compare.use_cases.export import (
    EXPORT_SUGGESTED_NAME_MAX_LEN,
    build_suggested_export_filename,
)


def _controller_with_slots(slots) -> SimpleNamespace:
    """Minimal controller: only ``widget.state.slots`` is read by the helper."""
    return SimpleNamespace(
        widget=SimpleNamespace(state=SimpleNamespace(slots=list(slots)))
    )


def _slot(slot_id: int, path=None, label: str = "") -> CompareSlot:
    return CompareSlot(id=slot_id, path=path, label=label)


def test_two_filled_slots_name_is_first_stem_plus_count(tmp_path):
    controller = _controller_with_slots(
        [
            _slot(1, tmp_path / "AniScale2_DITN_i16_75K.png"),
            _slot(2, tmp_path / "second_source.jpg"),
        ]
    )

    name = build_suggested_export_filename(controller)

    assert name == "AniScale2_DITN_i16_75K_2images"
    assert "multi_compare" not in name


def test_empty_grid_falls_back_to_literal():
    assert build_suggested_export_filename(_controller_with_slots([])) == (
        "multi_compare"
    )


def test_slots_without_path_or_label_fall_back_to_literal():
    controller = _controller_with_slots(
        [_slot(1), _slot(2, path=None, label="")]
    )

    assert build_suggested_export_filename(controller) == "multi_compare"


def test_label_stands_in_when_a_slot_has_no_path():
    controller = _controller_with_slots(
        [_slot(1, path=None, label="Pasted from clipboard")]
    )

    assert (
        build_suggested_export_filename(controller)
        == "Pasted from clipboard_1images"
    )


def test_long_stem_is_trimmed_to_cap_and_keeps_the_count_tail():
    long_stem = "A" * 200

    controller = _controller_with_slots(
        [
            _slot(1, Path("/tmp") / f"{long_stem}.png"),
            _slot(2, Path("/tmp") / "b.png"),
        ]
    )

    name = build_suggested_export_filename(controller)

    assert len(name) == EXPORT_SUGGESTED_NAME_MAX_LEN == 80
    assert name.endswith("_2images")
    assert name == "A" * (80 - len("_2images")) + "_2images"


def test_forbidden_characters_are_replaced():
    controller = _controller_with_slots([_slot(1, path=None, label="a/b:c*?")])

    name = build_suggested_export_filename(controller)

    assert name == "a_b_c__" + "_1images"
    for ch in '\\/*?:"<>|':
        assert ch not in name


def test_forbidden_characters_in_a_path_stem_are_replaced(tmp_path):
    # A user-supplied filename that survived on a permissive filesystem is
    # sanitized the same way as a label.
    controller = _controller_with_slots(
        [_slot(1, tmp_path / "view:1*final?.png")]
    )

    name = build_suggested_export_filename(controller)

    assert name == "view_1_final__1images"


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _widget_two_slots(tmp_path):
    left = Path(tmp_path) / "AniScale2_DITN_i16_75K.png"
    right = Path(tmp_path) / "reference.png"
    widget = SimpleNamespace(
        state=SimpleNamespace(
            root=SplitNode(
                direction="h",
                children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
                weights=[1.0, 1.0],
            ),
            slots=[CompareSlot(id=1, path=left), CompareSlot(id=2, path=right)],
        ),
        canvas=SimpleNamespace(width=lambda: 32, height=lambda: 24),
        images_dropped=SimpleNamespace(connect=lambda *_: None),
        add_requested=SimpleNamespace(connect=lambda *_: None),
        save_requested=SimpleNamespace(connect=lambda *_: None),
        quick_save_requested=SimpleNamespace(connect=lambda *_: None),
        settings_requested=SimpleNamespace(connect=lambda *_: None),
        help_requested=SimpleNamespace(connect=lambda *_: None),
        divider_color_picker_requested=SimpleNamespace(connect=lambda *_: None),
    )
    seed = QImage(32, 24, QImage.Format.Format_RGBA8888)
    seed.fill(QColor(9, 9, 9, 255))
    return widget, seed, left, right


def test_save_request_hands_the_computed_name_to_the_dialog(
    qapp, tmp_path, monkeypatch
):
    """End-to-end through ``on_save_requested`` — the production entry point."""
    opened: list[dict] = []
    widget, seed, left, right = _widget_two_slots(tmp_path)
    settings = SimpleNamespace(
        current_language="en",
        export_default_dir=str(tmp_path),
        export_use_default_dir=True,
        export_favorite_dir=None,
        export_last_format="PNG",
        export_quality=90,
        export_png_compress_level=6,
        export_png_optimize=True,
        export_fill_background=True,
        export_background_color=SimpleNamespace(r=1, g=2, b=3, a=255),
        export_comment_keep_default=False,
        export_comment_text="",
        export_resolution_scale=1.0,
    )
    controller = MultiCompareController(
        widget,
        store=SimpleNamespace(settings=settings),
        open_export_dialog=lambda **kwargs: opened.append(kwargs) or object(),
    )
    controller.pixel_cache.put_preview(left, seed)
    controller.pixel_cache.put_preview(right, seed)
    monkeypatch.setattr(controller, "_native_canvas_size", lambda: (32, 24))
    monkeypatch.setattr(
        "tabs.multi_compare.use_cases.export.render_export_preview",
        lambda *a, **kw: object(),
    )

    controller._on_save_requested()

    assert len(opened) == 1
    assert opened[0]["suggested_filename"] == "AniScale2_DITN_i16_75K_2images"

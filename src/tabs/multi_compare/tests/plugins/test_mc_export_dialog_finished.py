"""Multi Compare's dialog save continues in the export dialog's ``finished`` handler.

The export dialog is non-modal (see ``tests/plugins/test_export_dialog_nonmodal.py``
— mutter drags a modal transient's parent), so ``on_save_requested`` opens it
and returns; composition + the save worker start only when the dialog reports
``Accepted``. Cancel must stay a no-op: no compose, no worker, no settings
persistence.

Red-before: on the previous tree the stub dialog service returned
``(code, options)`` synchronously and the save ran inside ``on_save_requested``,
so ``open_export_dialog`` was never handed an ``on_finished`` callback at all —
the first assertion in each test fails there.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QDialog

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import CompareSlot, LeafNode


def _widget_with_pixels(tmp_path):
    """A one-slot widget whose slot resolves a cached pixel tier."""
    widget = SimpleNamespace(
        state=SimpleNamespace(
            root=LeafNode(slot_id=1),
            slots=[CompareSlot(id=1)],
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
    widget.state.slots[0].path = Path(tmp_path) / "slot1.png"
    seed = QImage(32, 24, QImage.Format.Format_RGBA8888)
    seed.fill(QColor(9, 9, 9, 255))
    return widget, seed


def _settings(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
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


def _controller(tmp_path, monkeypatch):
    opened: list[dict] = []
    saved: list[tuple] = []
    composed: list[tuple] = []

    widget, seed = _widget_with_pixels(tmp_path)
    controller = MultiCompareController(
        widget,
        store=SimpleNamespace(settings=_settings(tmp_path)),
        open_export_dialog=lambda **kwargs: opened.append(kwargs) or object(),
    )
    controller.pixel_cache.put_preview(widget.state.slots[0].path, seed)
    monkeypatch.setattr(controller, "_native_canvas_size", lambda: (32, 24))
    monkeypatch.setattr(
        controller,
        "_compose_image",
        lambda w, h, background_color=None, fill_background=True: composed.append(
            (w, h)
        )
        or QImage(w, h, QImage.Format.Format_RGBA8888),
    )
    monkeypatch.setattr(
        controller,
        "_get_save_flow",
        lambda: SimpleNamespace(
            start_save_worker=lambda pil, opts: saved.append((pil, opts))
        ),
    )
    monkeypatch.setattr(
        "shared.image_processing.qt_conversion.qimage_to_pil",
        lambda _img: object(),
    )
    monkeypatch.setattr(
        "tabs.multi_compare.use_cases.export.render_export_preview",
        lambda *a, **kw: object(),
    )
    return controller, SimpleNamespace(opened=opened, saved=saved, composed=composed)


def _options(tmp_path) -> dict:
    return {
        "output_dir": str(tmp_path),
        "file_name": "grid",
        "format": "PNG",
        "quality": 90,
        "png_compress_level": 6,
        "png_optimize": True,
        "fill_background": True,
        "background_color": (1, 2, 3, 255),
        "width": 32,
        "height": 24,
        "resolution_scale": 1.0,
        "comment_text": "",
        "comment_keep_default": False,
    }


def test_save_request_opens_dialog_with_finished_callback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shared.untested_export_resolution.confirm_untested_export_resolution",
        lambda *a, **kw: True,
    )
    controller, seen = _controller(tmp_path, monkeypatch)

    controller._on_save_requested()

    assert len(seen.opened) == 1
    assert callable(seen.opened[0].get("on_finished")), (
        "the dialog service must receive on_finished — it no longer blocks "
        "until accepted"
    )
    assert seen.composed == [], "nothing may be composed before the user accepts"
    assert seen.saved == []


def test_accepted_composes_and_saves_with_dialog_options(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shared.untested_export_resolution.confirm_untested_export_resolution",
        lambda *a, **kw: True,
    )
    controller, seen = _controller(tmp_path, monkeypatch)
    options = _options(tmp_path)

    controller._on_save_requested()
    seen.opened[0]["on_finished"](QDialog.DialogCode.Accepted, options)

    assert seen.composed == [(32, 24)]
    assert len(seen.saved) == 1
    _pil, saved_options = seen.saved[0]
    assert saved_options is options, "the accepted options must be the ones written"
    assert controller.store.settings.export_last_format == "PNG"
    assert controller.store.settings.export_default_dir == str(tmp_path)


def test_cancel_composes_nothing_and_saves_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shared.untested_export_resolution.confirm_untested_export_resolution",
        lambda *a, **kw: pytest.fail("cancel must not prompt about resolution"),
    )
    controller, seen = _controller(tmp_path, monkeypatch)

    controller._on_save_requested()
    seen.opened[0]["on_finished"](QDialog.DialogCode.Rejected, {})

    assert seen.composed == []
    assert seen.saved == []
    assert list(tmp_path.iterdir()) == []

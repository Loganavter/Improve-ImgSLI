"""Overlay translator seam: ``retranslate()`` changes *visible* text.

Falsification (pre-fix): ``CleanReviewOverlay`` / ``QuickLookOverlay`` had no
translator at all — the title and the Move/Restore buttons were frozen English
regardless of the active language, and ``retranslate`` did not exist. This
asserts the rendered label is a function of the wired translator (content
identity: the exact string, not "a method exists" / "text is non-empty").
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from tabs.image_gallery.ui.clean_review import CleanReviewOverlay

# pytest-qt keeps only weakrefs; a top-level parent with no Python reference
# would be GC-collected and destroy the overlay with it (same idiom as
# test_clean_review_parity.py).
_KEEP_ALIVE: list[QWidget] = []


def _btn_text(btn) -> str:
    """Toolkit Button text lives on its region (or region rows)."""
    try:
        for region in btn.regions():
            text = getattr(region, "text", "") or ""
            if text:
                return text
            for row in getattr(region, "rows", None) or []:
                text = getattr(row, "text", "") or ""
                if text:
                    return text
    except Exception:
        pass
    return ""


def _owner():
    item = SimpleNamespace(
        rejected=True,
        path="/tmp/gallery-i18n/a.jpg",
        name="a.jpg",
        thumbnail=None,
        provenance_series_id="series_1",
    )
    return SimpleNamespace(state=SimpleNamespace(items=[item], folder="/tmp/gallery-i18n"))


def _make_overlay(qtbot, translate) -> CleanReviewOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    overlay = CleanReviewOverlay(parent, _owner(), translate=translate)
    qtbot.addWidget(overlay)
    overlay._populate(_owner())
    _KEEP_ALIVE.append(parent)
    return overlay


def test_clean_review_retranslate_changes_visible_text(qtbot) -> None:
    overlay = _make_overlay(qtbot, lambda k, d: f"A[{k}]")
    assert overlay._title.text() == "A[image_gallery.clean_review.title]"
    assert _btn_text(overlay._move_btn) == "A[image_gallery.clean_review.move]"

    overlay.retranslate(lambda k, d: f"B[{k}]")
    assert overlay._title.text() == "B[image_gallery.clean_review.title]"
    assert _btn_text(overlay._move_btn) == "B[image_gallery.clean_review.move]"


def test_clean_review_en_defaults_when_no_translator(qtbot) -> None:
    overlay = _make_overlay(qtbot, None)
    assert overlay._title.text() == "Review rejected files"
    assert _btn_text(overlay._move_btn) == "Move 1"

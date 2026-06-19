"""UI inspector QSS index reports selector candidates by widget type, object
name, parent type, and dynamic properties.

Dogma source: docs/dev/UI_INSPECTOR.md.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from devtools.ui_inspector.qss_index import QssIndex

_APP = None


def _app():
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def test_qss_index_finds_object_property_and_parent_candidates(tmp_path):
    _app()
    qss = tmp_path / "inspector.qss"
    qss.write_text(
        """
        QLabel#ratingLabel { color: @list_item.text.rating; }
        QLabel[class="rating-label"] { font-weight: bold; }
        QWidget > QLabel#ratingLabel { background: transparent; }
        QPushButton#ratingLabel { color: red; }
        """,
        encoding="utf-8",
    )

    parent = QWidget()
    child = QLabel("Rating", parent)
    child.setObjectName("ratingLabel")
    child.setProperty("class", "rating-label")

    index = QssIndex.from_paths((str(qss),))
    selectors = {rule.selector for rule in index.candidates_for(child)}

    assert "QLabel#ratingLabel" in selectors
    assert 'QLabel[class="rating-label"]' in selectors
    assert "QWidget > QLabel#ratingLabel" in selectors
    assert "QPushButton#ratingLabel" not in selectors

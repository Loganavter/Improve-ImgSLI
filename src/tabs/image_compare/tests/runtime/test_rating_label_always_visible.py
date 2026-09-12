"""Rating labels always reserve space (never collapse the combo row).

Regression: ``update_rating_display`` hid the label when the slot had no
current item (score None). The hidden label collapsed its rated-combo
half, so the two combos ended up different widths (1268 vs 1234 with one
side loaded) — asymmetric anchors, asymmetric flyout panels, plus a layout
jump the moment the first image lands. The label now always stays visible
(showing "–" when there is no score); it is fixed-width so the space is
reserved either way.
"""

from __future__ import annotations

from tabs.image_compare.widget import ImageCompareWidget


class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.visible = True

    def setText(self, text):
        self.text = text

    def setVisible(self, value):
        self.visible = bool(value)

    def isVisible(self):
        return self.visible


def _make_widget():
    widget = ImageCompareWidget.__new__(ImageCompareWidget)
    widget.label_rating1 = _FakeLabel()
    widget.label_rating2 = _FakeLabel()
    return widget


def test_rating_label_stays_visible_without_score():
    widget = _make_widget()
    widget.update_rating_display(1, None, "en")
    assert widget.label_rating1.text == "–"
    assert widget.label_rating1.isVisible()


def test_rating_label_stays_visible_with_score():
    widget = _make_widget()
    widget.update_rating_display(2, 4, "en")
    assert "4" in widget.label_rating2.text
    assert widget.label_rating2.isVisible()


def test_both_sides_keep_their_labels():
    widget = _make_widget()
    widget.update_rating_display(1, None, "en")
    widget.update_rating_display(2, 0, "en")
    assert widget.label_rating1.isVisible()
    assert widget.label_rating2.isVisible()

"""Image Compare tells the host which placement hint it reads.

The control surface refuses a hint the receiving tab does not read (measured
2026-10-28: ``open_file(side="right", tab="image_compare")`` answered
``opened: true`` and put the file in the LEFT slot). The answer is a *class*
attribute so the host can ask without touching a widget.
"""

from __future__ import annotations

from tabs.image_compare.tab import ImageCompareTab
from tabs.multi_compare.tab import MultiCompareTab


def test_image_compare_reads_slot_only():
    assert ImageCompareTab.drop_hint_key == "slot"


def test_multi_compare_reads_side_only():
    assert MultiCompareTab.drop_hint_key == "side"

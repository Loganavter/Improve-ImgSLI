"""A1 entries + placement-purity guards (plan-mc-pipeline-refactor, phase A1).

- bug-a1 guard: IC and MC accepted-sets are equal (single source
  ``shared.image_extensions`` — a ``.jxl`` drop must not load in one tab
  and bounce in the other);
- double-drop dedup: the MC ``DropQueue`` (IC mirror, key
  ``(anchor_slot, normpath)``, max-1-inflight) emits once for a rapid
  double-drop of the same file;
- placement purity: the pure core falls back deterministically to
  ``((), "right")`` on empty geometry and never reads the live canvas.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QRect


def _pump(qapp, rounds: int = 20) -> None:
    for _ in range(rounds):
        qapp.processEvents()


def test_accepted_sets_equal_ic_mc_bug_a1_guard():
    """IC/MC must accept the same suffixes — including ``.jxl``."""
    from shared import image_extensions as ext
    from tabs.image_compare.use_cases import drag_drop as ic_dnd
    from tabs.multi_compare.ui import drag_drop as mc_dnd
    from tabs.multi_compare.tab import _filter_image_paths

    assert ".jxl" in ext.ACCEPTED_IMAGE_EXTENSIONS
    # Both tabs filter from the single source: dialog glob is built from it.
    assert ext.IMAGE_FILTER_GLOB == " ".join(
        f"*{e}" for e in sorted(ext.ACCEPTED_IMAGE_EXTENSIONS)
    )
    assert ".jxl" in ext.build_image_dialog_filter()

    # IC entry: suffix verdict from the shared set.
    assert ic_dnd.accepts_drop([Path("a.jxl"), Path("b.txt")]) is True
    assert ic_dnd.accepts_drop([Path("b.txt")]) is False
    # MC entries: same verdicts through the shared helper.
    assert mc_dnd.is_accepted_image_path("a.jxl") is True
    assert mc_dnd.is_accepted_image_path("b.txt") is False
    assert _filter_image_paths([Path("a.jxl"), Path("b.txt")]) == [Path("a.jxl")]

    def _mime(names):
        urls = [SimpleNamespace(toLocalFile=lambda n=n: n) for n in names]
        return SimpleNamespace(hasUrls=lambda: True, urls=lambda: list(urls))

    assert mc_dnd.has_image_urls(_mime(["a.jxl"])) is True
    assert mc_dnd.has_image_urls(_mime(["b.txt"])) is False


def test_placement_pure_core_deterministic_fallback():
    """Empty geometry → ``((), "right")``; largest leaf wins otherwise."""
    from tabs.multi_compare.use_cases import placement

    assert placement.pick_largest_leaf_target([]) == ((), "right")
    assert placement.pick_largest_leaf_target(None) == ((), "right")

    wide = (object(), QRect(0, 0, 400, 100), (0,))
    tall = (object(), QRect(0, 0, 100, 300), (1,))
    assert placement.pick_largest_leaf_target([tall, wide]) == ((0,), "right")
    assert placement.pick_largest_leaf_target([wide, tall]) == ((0,), "right")
    assert placement.pick_largest_leaf_target([tall]) == ((1,), "bottom")

    # Pure anchor: tree data in, no canvas reads.
    from tabs.multi_compare.models import LeafNode, SplitNode

    root = SplitNode(
        direction="h", children=[LeafNode(7), LeafNode(9)], weights=[1.0, 1.0]
    )
    assert placement.anchor_slot_for_path(root, (1,)) == 9
    assert placement.anchor_slot_for_path(root, (5,)) is None
    assert placement.anchor_slot_for_path(None, ()) is None


def test_hit_projection_pure_core():
    """Letterbox math is a pure function of its inputs."""
    from tabs.multi_compare.ui import hit_projection as hp

    assert hp.letterbox_transform(0, 100, 200.0, 200.0) is None
    assert hp.letterbox_transform(100, 100, 0.0, 200.0) is None
    sr, ox, oy = hp.letterbox_transform(200, 100, 200.0, 200.0)
    assert (sr, ox, oy) == (1.0, 0.0, 50.0)
    # Batch projection agrees with the single-rect path.
    rects = [QRect(0, 0, 200, 100)]
    assert hp.project_canvas_rects(rects, sr, ox, oy) == [
        hp.project_canvas_rect(rects[0], sr, ox, oy)
    ]
    # Gap policy: hidden divider → 0, missing settings → default.
    assert hp.divider_gap_thickness(None, 4) == 4
    assert hp.divider_gap_thickness(SimpleNamespace(visible=False, thickness=8), 4) == 0
    assert hp.divider_gap_thickness(SimpleNamespace(visible=True, thickness=8), 4) == 8


def test_double_drop_same_file_emits_once(qapp, tmp_path):
    """Rapid double-drop of one file → single emit (FIFO dedup)."""
    from tabs.multi_compare.ui.drag_drop import DropQueue

    queue = DropQueue()
    emitted: list = []
    widget = SimpleNamespace(
        images_dropped=SimpleNamespace(
            emit=lambda paths, target, side: emitted.append((list(paths), target, side))
        )
    )
    path = tmp_path / "img.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    assert queue.enqueue(None, [path], widget, (None, False), None) is True
    # Second enqueue while the first is queued/inflight → deduped.
    assert queue.enqueue(None, [path], widget, (None, False), None) is False
    # Textual variants (str vs Path) share the normpath key → deduped too.
    assert queue.enqueue(None, [str(path)], widget, (None, False), None) is False

    _pump(qapp)
    assert len(emitted) == 1
    assert [str(p) for (ps, _, _) in emitted for p in ps] == [str(path)]

    # After the emit lands the keys release — a later drop flows again.
    assert queue.enqueue(None, [path], widget, (None, False), None) is True
    _pump(qapp)
    assert len(emitted) == 2


def test_drop_queue_distinct_files_both_flow(qapp, tmp_path):
    """Different files are never deduped against each other."""
    from tabs.multi_compare.ui.drag_drop import DropQueue

    queue = DropQueue()
    emitted: list = []
    widget = SimpleNamespace(
        images_dropped=SimpleNamespace(
            emit=lambda paths, target, side: emitted.append((list(paths), target, side))
        )
    )
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 64)
    second.write_bytes(b"\x89PNG\r\n\x1a\n" + b"2" * 64)

    assert queue.enqueue(None, [first], widget, (None, False), None) is True
    assert queue.enqueue(None, [second], widget, (None, False), None) is True
    _pump(qapp)
    got = sorted(str(p) for (ps, _, _) in emitted for p in ps)
    assert got == sorted([str(first), str(second)])

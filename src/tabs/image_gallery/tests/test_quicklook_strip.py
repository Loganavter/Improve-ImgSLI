"""Quick look series-strip rework regression tests.

- Thumb pixmaps cover-crop to exactly 66×44 (``_thumb_pixmap`` w/h contract).
- ``regionClicked`` on a strip thumb switches the preview (clicked alone
  never fired: the thumb region id is ``"thumb"``, not ``"_main"``).
- Card-style badge contract: rejected → no pill, leader → ``#N`` like every
  ranked item (no BEST pill), ranked → ``#N`` (``_gallery_badge`` +
  ``_gallery_badge_style`` overlay pills; the toolkit badge stays ``None``
  except tie-break pending).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look.preview import _thumb_pixmap


def _item(name: str, **kwargs) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, **kwargs)


def _real_png(tmp_path: Path, name: str, w: int = 200, h: int = 100) -> Path:
    # QPixmap fatals without a QApplication; the full suite usually has one
    # by now, but standalone runs of this file must not depend on that.
    if QApplication.instance() is None:
        QApplication([])
    pm = QPixmap(w, h)
    pm.fill(QColor("#3a6ea5"))
    p = tmp_path / name
    assert pm.save(str(p), "PNG")
    return p


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent  # strong ref, keeps C++ tree alive
    return ov


def _show(overlay: QuickLookOverlay, item: GalleryItem, series, mode=Mode.FIDELITY, source=None):
    if series and not isinstance(series[0], (list, tuple)):
        series = [list(series)]
    owner = SimpleNamespace(
        state=SimpleNamespace(
            mode=mode,
            source_path=source,
            series=series,
            items=[m for cl in series for m in cl],
        )
    )
    overlay.show_for(item, owner)
    try:
        parent = getattr(overlay, "_parity_test_parent", None) or overlay.parentWidget()
        if parent is not None:
            parent.resize(1280, 800)
            parent.show()
    except Exception:
        pass
    QApplication.processEvents()


def _strip_buttons(ov):
    from sli_ui_toolkit.widgets import Button

    return [b for b in ov._strip_host.findChildren(Button) if b.objectName().startswith("quicklook_strip_")]


def test_thumb_pixmap_cover_crops_to_exact_66x44(tmp_path):
    """Wide and tall sources both land on exactly 66×44 (cover, center-crop)."""
    wide_p = _real_png(tmp_path, "wide.png", 200, 50)
    tall_p = _real_png(tmp_path, "tall.png", 50, 200)
    for p in (wide_p, tall_p):
        item = GalleryItem(path=p, mtime_ns=1)
        pm = _thumb_pixmap(item)
        assert pm is not None and not pm.isNull()
        assert (pm.width(), pm.height()) == (66, 44)
    # Explicit w/h honored too.
    item = GalleryItem(path=wide_p, mtime_ns=1)
    pm = _thumb_pixmap(item, 100, 60)
    assert pm is not None and not pm.isNull()
    assert (pm.width(), pm.height()) == (100, 60)


def test_thumb_region_has_rounded_corners(qtbot, tmp_path):
    """Strip thumb cover region carries corner radii (painter clips to them)."""
    p1 = _real_png(tmp_path, "v.png")
    viewing = GalleryItem(path=p1, mtime_ns=1)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing])
    for b in _strip_buttons(ov):
        regions = [r for r in b.regions() if r.id == "thumb"]
        assert regions, "thumb region missing"
        assert tuple(regions[0].corner_radii) == (6, 6, 6, 6)
    ov.hide()


def test_region_clicked_switches_preview(qtbot, tmp_path):
    """Emitting regionClicked on a strip thumb switches _current_item/idx.

    Clicks the MIDDLE thumb of three: with late binding every thumb would
    lead to the last member, so only a non-last target proves the mapping.
    """
    paths = [_real_png(tmp_path, f"c{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    assert ov._current_idx == 0
    target = None
    for b in _strip_buttons(ov):
        if b.property("gallery_path") == str(paths[1]):
            target = b
            break
    assert target is not None
    target.regionClicked.emit("thumb")
    # Series switch re-populates after the press ripple (defer_click).
    qtbot.wait(450)
    QApplication.processEvents()
    assert ov._current_item.path == paths[1]
    assert ov._current_idx == 1
    ov.hide()


def test_rejected_thumb_has_no_badge(qtbot, tmp_path):
    """Rejected strip thumbs carry no pill (dim effect is the signal)."""
    p1 = _real_png(tmp_path, "v.png")
    p2 = _real_png(tmp_path, "r.png")
    viewing = GalleryItem(path=p1, mtime_ns=1)
    rejected = GalleryItem(path=p2, mtime_ns=2, rejected=True)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, rejected])
    by_path = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert getattr(by_path[str(p2)], "_gallery_badge", None) is None
    assert by_path[str(p2)]._badge is None
    ov.hide()


def test_leader_badge_is_rank_like_rest(qtbot, tmp_path):
    """Leader → #N like every ranked item (no BEST pill); ranked → #N (black on toggle bg)."""
    paths = [_real_png(tmp_path, f"s{i}.png") for i in range(3)]
    leader = GalleryItem(path=paths[0], mtime_ns=1, is_best=True)
    ranked = GalleryItem(path=paths[1], mtime_ns=2, rank=3)
    plain = GalleryItem(path=paths[2], mtime_ns=3)
    ov = _make_overlay(qtbot)
    _show(ov, leader, [leader, ranked, plain])
    by_path = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert by_path[str(paths[0])]._gallery_badge == "#1"
    assert by_path[str(paths[1])]._gallery_badge == "#3"
    assert getattr(by_path[str(paths[2])], "_gallery_badge", None) is None
    # Style shape mirrors visuals.py: (filled, bg, border, text_color).
    for key in (str(paths[0]), str(paths[1])):
        style = by_path[key]._gallery_badge_style
        assert isinstance(style, tuple) and len(style) == 4
        assert style[0] is True
    assert by_path[str(paths[0])]._gallery_badge_style[3] == QColor("#000000")
    assert by_path[str(paths[1])]._gallery_badge_style[3] == QColor("#000000")
    # Overlay pills, never the toolkit badge.
    assert by_path[str(paths[0])]._badge is None
    assert by_path[str(paths[1])]._badge is None
    ov.hide()


def test_viewing_thumb_has_visible_outline(qtbot, tmp_path):
    """Viewing thumb carries accent border WITH width (BorderLayer needs it)."""
    p1 = _real_png(tmp_path, "v.png")
    p2 = _real_png(tmp_path, "o.png")
    viewing = GalleryItem(path=p1, mtime_ns=1)
    other = GalleryItem(path=p2, mtime_ns=2)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, other])
    by_path = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert int(by_path[str(p1)].property("borderWidth") or 0) >= 2
    ov.hide()


def test_click_viewing_thumb_skips_full_repopulate(qtbot, tmp_path):
    """Clicking the already-viewing thumb must not run _populate (no blink)."""
    p1 = _real_png(tmp_path, "v.png")
    p2 = _real_png(tmp_path, "o.png")
    viewing = GalleryItem(path=p1, mtime_ns=1)
    other = GalleryItem(path=p2, mtime_ns=2)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, other])
    calls = []
    ov._populate = lambda: calls.append(1)  # type: ignore[method-assign]
    by_path = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    by_path[str(p1)].regionClicked.emit("thumb")
    QApplication.processEvents()
    assert calls == []
    assert ov._current_idx == 0
    ov.hide()


def test_walk_refresh_reuses_strip_widgets(qtbot):
    """Walk with unchanged series/triage/theme/scale refreshes in place.

    No widget is recreated (same container/button objects); the viewing
    outline moves to the new thumb and the old one clears its border.
    """
    mates = [_item(f"w{i}.png", rank=i) for i in (1, 2, 3)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    assert getattr(ov, "_strip_fingerprint", None)
    before_cont = {c.objectName(): c for c in ov._strip_buttons}
    before_btns = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert len(before_btns) == 3
    ov._walk(1)
    QApplication.processEvents()
    QApplication.processEvents()
    assert ov._current_idx == 1
    after_cont = {c.objectName(): c for c in ov._strip_buttons}
    after_btns = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert set(after_cont) == set(before_cont)
    assert set(after_btns) == set(before_btns)
    assert all(after_cont[k] is before_cont[k] for k in before_cont)
    assert all(after_btns[k] is before_btns[k] for k in before_btns)
    new_view = after_btns[str(mates[1].path)]
    old_view = after_btns[str(mates[0].path)]
    assert int(new_view.property("borderWidth") or 0) >= 2
    assert new_view.borderColor() is not None
    assert old_view.borderColor() is None
    assert old_view.property("borderWidth") is None
    ov.hide()


def test_rejected_flip_rebuilds_strip(qtbot):
    """Flipping rejected on an item changes the fingerprint → full rebuild."""
    mates = [_item(f"rj{i}.png", rank=i) for i in (1, 2)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    before = list(ov._strip_buttons)
    ov._series_items[1].rejected = True
    ov._rebuild_strip()
    QApplication.processEvents()
    after = list(ov._strip_buttons)
    assert len(after) == len(before) == 2
    assert all(a is not b for a, b in zip(after, before))
    by_path = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    dimmed = by_path[str(ov._series_items[1].path)]
    eff = dimmed.graphicsEffect()
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    assert isinstance(eff, QGraphicsOpacityEffect) and eff.opacity() == 0.4
    ov.hide()


def test_dark_flip_rebuilds_strip(qtbot, monkeypatch):
    """Theme flip changes the fingerprint → full rebuild (never stale colors)."""
    import tabs.image_gallery.ui.quick_look.bars as _bars

    mates = [_item(f"dk{i}.png", rank=i) for i in (1, 2)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    before = list(ov._strip_buttons)
    was_dark = bool(_bars._is_dark_theme())
    monkeypatch.setattr(_bars, "_is_dark_theme", lambda: (not was_dark))
    ov._rebuild_strip()
    QApplication.processEvents()
    after = list(ov._strip_buttons)
    assert len(after) == len(before) == 2
    assert all(a is not b for a, b in zip(after, before))
    ov.hide()


def test_metrics_revisit_same_item_preserves_rows(qtbot):
    """Same item/metrics/series/theme/scale → rows untouched (memo skip)."""
    a = _item("m0.png", rank=1, metrics={"ssim": 0.9})
    b = _item("m1.png", rank=2, metrics={"ssim": 0.8})
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    rows0 = list(ov._metric_rows)
    assert rows0
    assert getattr(ov, "_metrics_fingerprint", None)
    cur = ov._current_item
    ov._rebuild_metrics(cur, True, "FIDELITY MODE")
    QApplication.processEvents()
    rows1 = list(ov._metric_rows)
    assert len(rows1) == len(rows0)
    assert all(n is o for n, o in zip(rows1, rows0))
    ov.hide()


def test_metrics_changed_dict_rebuilds(qtbot):
    """Changed metrics dict on the same item → full metrics rebuild."""
    a = _item("mc0.png", rank=1, metrics={"ssim": 0.9})
    b = _item("mc1.png", rank=2, metrics={"ssim": 0.8})
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    rows0 = list(ov._metric_rows)
    cur = ov._current_item
    cur.metrics["ssim"] = 0.5
    ov._rebuild_metrics(cur, True, "FIDELITY MODE")
    QApplication.processEvents()
    rows1 = list(ov._metric_rows)
    assert len(rows1) == len(rows0)
    assert all(n is not o for n, o in zip(rows1, rows0))
    ov.hide()


def test_metrics_neighbor_rank_change_rebuilds(qtbot):
    """Triage rank change on a NEIGHBOR (ssim_subline input) → rebuild."""
    a = _item("mn0.png", rank=1, metrics={"ssim": 0.9})
    b = _item("mn1.png", rank=2, metrics={"ssim": 0.8})
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    rows0 = list(ov._metric_rows)
    cur = ov._current_item
    ov._rebuild_metrics(cur, True, "FIDELITY MODE")
    QApplication.processEvents()
    assert all(n is o for n, o in zip(list(ov._metric_rows), rows0))
    ov._series_items[1].rank = 7
    ov._rebuild_metrics(cur, True, "FIDELITY MODE")
    QApplication.processEvents()
    rows1 = list(ov._metric_rows)
    assert all(n is not o for n, o in zip(rows1, rows0))
    ov.hide()


def _row_texts(ov) -> list:
    """All label texts across the live metric rows, in layout order.

    Reads ``.text()`` off any descendant widget that has it (bars have no
    text) — no toolkit-internals dependency.
    """
    from PySide6.QtWidgets import QWidget as _W

    texts: list = []
    for row in list(getattr(ov, "_metric_rows", None) or []):
        try:
            kids = row.findChildren(_W)
        except Exception:
            continue
        for w in kids:
            try:
                t = w.text()
            except Exception:
                continue
            if isinstance(t, str) and t:
                texts.append(t)
    return texts


def test_metrics_walk_revisit_preserves_containers(qtbot):
    """Walk A→B→A: the A revisit swaps cached containers (zero recreation)."""
    a = _item("wmc0.png", rank=1, metrics={"ssim": 0.9})
    b = _item("wmc1.png", rank=2, metrics={"ssim": 0.8})
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    rows_a = list(ov._metric_rows)
    assert rows_a
    ov._walk(1)
    QApplication.processEvents()
    QApplication.processEvents()
    assert ov._current_idx == 1
    rows_b = list(ov._metric_rows)
    assert rows_b
    assert not any(n is o for n in rows_b for o in rows_a)
    ov._walk(-1)
    QApplication.processEvents()
    QApplication.processEvents()
    assert ov._current_idx == 0
    rows_a2 = list(ov._metric_rows)
    assert [id(w) for w in rows_a2] == [id(w) for w in rows_a]
    assert all(w.isVisible() for w in rows_a2)
    ov.hide()


def test_metrics_row_cache_lru_bound(qtbot):
    """Visit >8 distinct items → cached sets ≤ 8; evicted revisit rebuilds right."""
    mates = [_item(f"lru{i}.png", rank=i + 1, metrics={"ssim": 0.50 + i * 0.01}) for i in range(10)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    first_rows = list(ov._metric_rows)
    first_texts = _row_texts(ov)
    assert first_rows and first_texts
    assert any("0.50" in t for t in first_texts)
    for _ in range(9):
        ov._walk(1)
        QApplication.processEvents()
    assert ov._current_idx == 9
    cache = getattr(ov, "_metrics_row_cache", None)
    assert isinstance(cache, dict)
    assert len(cache) <= 8
    ov._walk(1)  # wraps 9 → 0: the evicted set rebuilds (miss path).
    QApplication.processEvents()
    QApplication.processEvents()
    assert ov._current_idx == 0
    assert _row_texts(ov) == first_texts  # right content, no neighbor rows.
    assert [id(w) for w in ov._metric_rows] != [id(w) for w in first_rows]
    assert len(getattr(ov, "_metrics_row_cache")) <= 8
    ov.hide()


def test_metrics_theme_flip_rebuilds(qtbot, monkeypatch):
    """Theme flip changes the fingerprint → full metrics rebuild (cache miss)."""
    import tabs.image_gallery.ui.quick_look.metrics as _metrics

    a = _item("thm0.png", rank=1, metrics={"ssim": 0.9})
    b = _item("thm1.png", rank=2, metrics={"ssim": 0.8})
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    rows0 = list(ov._metric_rows)
    assert rows0
    was_dark = bool(_metrics._is_dark_theme())
    monkeypatch.setattr(_metrics, "_is_dark_theme", lambda: (not was_dark))
    ov._rebuild_metrics(ov._current_item, True, "FIDELITY MODE")
    QApplication.processEvents()
    rows1 = list(ov._metric_rows)
    assert len(rows1) == len(rows0)
    assert all(n is not o for n, o in zip(rows1, rows0))
    ov.hide()


def test_walk_keeps_strip_visible(qtbot):
    """Rebuilt strip children must be shown: the first build is revealed by
    a later ancestor show(), but on walk the host is already visible while
    new containers stay hidden — excluded from layout hints, the host
    collapses to 0 and the strip "disappears". Verified failing pre-fix
    (host_h 0 after walk), passing post-fix."""
    mates = [_item(f"up{i}.png", rank=i) for i in (1, 2)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    QApplication.processEvents()
    assert ov._strip_host.height() > 0
    ov._walk(1)
    QApplication.processEvents()
    QApplication.processEvents()
    assert len(_strip_buttons(ov)) == 2
    assert ov._strip_host.height() > 0
    for b in _strip_buttons(ov):
        assert b.isVisible()
    ov.hide()


def test_walk_follows_current_thumb(qtbot):
    """Walking to an out-of-view thumb scrolls the strip to it.

    Nothing in the app ever scrolled the strip (OverlayScrollArea glides
    only the vertical bar; the strip overflows horizontally), so walks
    left the current thumb out of view. Verified failing pre-fix
    (hbar stays 0 after walking to the last of 8).
    """
    mates = [_item(f"fl{i}.png", rank=i) for i in range(1, 9)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    QApplication.processEvents()
    bar = ov._strip_scroll.horizontalScrollBar()
    assert bar.maximum() > bar.minimum(), "need overflow for a follow test"
    assert bar.value() == bar.minimum()
    for _ in range(7):
        ov._walk(1)
        QApplication.processEvents()
    assert ov._current_idx == 7
    assert bar.value() > bar.minimum(), "strip must follow to the last thumb"
    for _ in range(7):
        ov._walk(-1)
        QApplication.processEvents()
    assert ov._current_idx == 0
    assert bar.value() == bar.minimum(), "strip must follow back to the first thumb"
    ov.hide()


def test_strip_wheel_step_mapping():
    """Pure wheel→px mapping: x preferred, y fallback, pixel 1:1, empty None."""
    from types import SimpleNamespace

    from PySide6.QtCore import QPoint

    from tabs.image_gallery.ui.quick_look.strip import _strip_wheel_step

    assert _strip_wheel_step(SimpleNamespace(angleDelta=lambda: QPoint(120, 0), pixelDelta=lambda: QPoint(0, 0)), 76) == -76
    assert _strip_wheel_step(SimpleNamespace(angleDelta=lambda: QPoint(-120, 0), pixelDelta=lambda: QPoint(0, 0)), 76) == 76
    assert _strip_wheel_step(SimpleNamespace(angleDelta=lambda: QPoint(0, 120), pixelDelta=lambda: QPoint(0, 0)), 76) == -76
    assert _strip_wheel_step(SimpleNamespace(angleDelta=lambda: QPoint(0, -240), pixelDelta=lambda: QPoint(0, 0)), 76) == 152
    assert _strip_wheel_step(SimpleNamespace(angleDelta=lambda: QPoint(0, 0), pixelDelta=lambda: QPoint(0, 0)), 76) is None
    assert _strip_wheel_step(SimpleNamespace(angleDelta=lambda: QPoint(0, 0), pixelDelta=lambda: QPoint(0, -7)), 76) == 7
    assert _strip_wheel_step(SimpleNamespace(angleDelta=lambda: QPoint(0, 0), pixelDelta=lambda: QPoint(5, 9)), 76) == -5


def test_strip_wheel_consumes_only_when_moving(qtbot):
    """Wheel over the strip moves the h-bar; at edges it propagates (False)."""
    from types import SimpleNamespace

    from PySide6.QtCore import QPoint

    from tabs.image_gallery.ui.quick_look.strip import _strip_scroll_wheel

    mates = [_item(f"wh{i}.png", rank=i) for i in range(1, 9)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    QApplication.processEvents()
    bar = ov._strip_scroll.horizontalScrollBar()
    assert bar.maximum() > bar.minimum()
    assert bar.value() == bar.minimum()
    down = SimpleNamespace(angleDelta=lambda: QPoint(0, -120), pixelDelta=lambda: QPoint(0, 0))
    assert _strip_scroll_wheel(ov, down) is True
    assert bar.value() > bar.minimum()
    bar.setValue(bar.maximum())
    assert _strip_scroll_wheel(ov, down) is False, "at the edge the wheel must propagate outward"
    up = SimpleNamespace(angleDelta=lambda: QPoint(0, 120), pixelDelta=lambda: QPoint(0, 0))
    assert _strip_scroll_wheel(ov, up) is True
    ov.hide()

"""Quick look series-strip rework regression tests.

- Thumb pixmaps cover-crop to exactly 66×44 (``_thumb_pixmap`` w/h contract).
- ``regionClicked`` on a strip thumb switches the preview (clicked alone
  never fired: the thumb region id is ``"thumb"``, not ``"_main"``).
- Card-style badge contract: rejected → no pill, leader → ``#N`` like every
  ranked item (no BEST pill), ranked → ``#N`` (real pill button;
  a tie-break-pending item falls through to its rank, no ``…`` placeholder).
  Rank pills are plain Buttons — no shared-hover
  ButtonFamily anywhere (dropped): pills walk to their item on click
  with no hover sync.
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
    # Badges are computed once upstream (widget.set_triage); stamp here so the
    # strip renders the same item.badge the app would.
    try:
        from tabs.image_gallery.services.rank_badge import stamp_badges

        stamp_badges([m for cl in series for m in cl], source)
    except Exception:
        pass
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


def _rank_buttons(ov):
    from sli_ui_toolkit.widgets import Button

    return [b for b in ov._strip_host.findChildren(Button) if b.objectName().startswith("quicklook_rank_")]


def _rank_pills_by_path(ov):
    """Rank pill button per series path (None when the thumb has no pill)."""
    from sli_ui_toolkit.widgets import Button as _B

    out = {}
    for container in list(getattr(ov, "_strip_buttons", None) or []):
        thumb = next(
            (b for b in container.findChildren(_B) if b.objectName().startswith("quicklook_strip_")),
            None,
        )
        if thumb is None:
            continue
        pill = next(
            (b for b in container.findChildren(_B) if b.objectName().startswith("quicklook_rank_")),
            None,
        )
        out[str(thumb.property("gallery_path"))] = pill
    return out


def _pill_text(pill):
    try:
        for region in pill.regions():
            for row in getattr(region, "rows", None) or []:
                text = getattr(row, "text", "")
                if text:
                    return text
    except Exception:
        pass
    return ""


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
    """Rejected strip thumbs carry no rank pill (dim effect is the signal)."""
    p1 = _real_png(tmp_path, "v.png")
    p2 = _real_png(tmp_path, "r.png")
    viewing = GalleryItem(path=p1, mtime_ns=1)
    rejected = GalleryItem(path=p2, mtime_ns=2, rejected=True)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, rejected])
    pills = _rank_pills_by_path(ov)
    assert pills[str(p2)] is None
    # ...and no toolkit badge anywhere on the thumbs.
    for b in _strip_buttons(ov):
        assert b._badge is None
    ov.hide()


def test_leader_badge_is_rank_like_rest(qtbot, tmp_path):
    """Leader → #N like every ranked item (no BEST pill); ranked → #N as a
    real pill button under the shared-hover family."""
    from sli_ui_toolkit.widgets import ButtonFamily

    paths = [_real_png(tmp_path, f"s{i}.png") for i in range(3)]
    leader = GalleryItem(path=paths[0], mtime_ns=1, is_best=True)
    ranked = GalleryItem(path=paths[1], mtime_ns=2, rank=3)
    plain = GalleryItem(path=paths[2], mtime_ns=3)
    ov = _make_overlay(qtbot)
    _show(ov, leader, [leader, ranked, plain])
    pills = _rank_pills_by_path(ov)
    assert _pill_text(pills[str(paths[0])]) == "#1"
    assert _pill_text(pills[str(paths[1])]) == "#3"
    assert pills[str(paths[2])] is None
    # Thumbs + pills live in one shared-hover family, thumbs carry no paint.
    fam = getattr(ov, "_strip_family", None)
    assert isinstance(fam, ButtonFamily)
    assert fam.sharedHover() is True
    thumbs = [b for b in _strip_buttons(ov)]
    assert {id(b) for b in fam.buttons()} == {
        id(pills[str(paths[0])]),
        id(pills[str(paths[1])]),
        *[id(b) for b in thumbs],
    }
    for b in _strip_buttons(ov):
        assert b._badge is None
    # Opaque white fill (override layer) + 1px kind-color outline.
    for pill in (pills[str(paths[0])], pills[str(paths[1])]):
        bg = pill._override_bg_color
        assert bg is not None and bg.alpha() == 255
        assert (bg.red(), bg.green(), bg.blue()) == (255, 255, 255)
        assert pill.borderColor() is not None
        assert int(pill.property("borderWidth") or 0) >= 1
    ov.hide()


def test_rank_pill_compact_fits_label(qtbot, tmp_path):
    """Rank pills size to text + BADGE_H_PAD (shared with the grid card).

    Regression: the pill used the Button's 24px text hint (a 12px side gap
    each side) instead of the card's compact ``text + 12`` geometry, so it
    looked padded — and earlier clipped.
    """
    from sli_ui_toolkit.managers import scaled_px

    from tabs.image_gallery.services.rank_badge import BADGE_H_PAD, BADGE_MIN_WIDTH

    paths = [_real_png(tmp_path, f"w{i}.png") for i in range(3)]
    src = GalleryItem(path=paths[0], mtime_ns=1)
    ranked = GalleryItem(path=paths[1], mtime_ns=2, rank=2)
    ranked2 = GalleryItem(path=paths[2], mtime_ns=3, rank=3)
    ov = _make_overlay(qtbot)
    _show(ov, src, [src, ranked, ranked2], source=src.path)
    QApplication.processEvents()
    pills = _rank_pills_by_path(ov)
    seen = set()
    for path, pill in pills.items():
        assert pill is not None, path
        # The Button hint reserves 24px; the label's own width is that − 24.
        text_w = max(0, pill.sizeHint().width() - scaled_px(24))
        assert pill.width() >= text_w, (_pill_text(pill), pill.width(), text_w)
        assert pill.width() <= max(
            scaled_px(BADGE_MIN_WIDTH), text_w + scaled_px(BADGE_H_PAD)
        ), (_pill_text(pill), pill.width(), text_w)
        seen.add(_pill_text(pill))
    assert "SOURCE" in seen
    ov.hide()


def test_rank_pill_bottom_center_inside_thumb(qtbot, tmp_path):
    """Rank pill straddles the thumb's bottom edge (half out, centered)."""
    p1 = _real_png(tmp_path, "v.png")
    p2 = _real_png(tmp_path, "o.png")
    viewing = GalleryItem(path=p1, mtime_ns=1, rank=1)
    other = GalleryItem(path=p2, mtime_ns=2, rank=2)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, other])
    QApplication.processEvents()
    QApplication.processEvents()
    pills = _rank_pills_by_path(ov)
    thumbs = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert len(pills) == 2
    for path, pill in pills.items():
        assert pill is not None
        thumb = thumbs[path]
        tg, pg = thumb.geometry(), pill.geometry()
        # Horizontally centered on the thumb…
        assert pg.center().x() == tg.center().x()
        # …vertically centered on its bottom edge (half overhang).
        assert pg.center().y() == tg.bottom()
        assert pg.top() >= tg.top()
        assert pg.bottom() > tg.bottom()
    ov.hide()


def test_rank_pill_click_walks_preview(qtbot, tmp_path):
    """Clicking a rank pill walks the preview like clicking its thumb."""
    paths = [_real_png(tmp_path, f"c{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1, rank=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    assert ov._current_idx == 0
    pills = _rank_pills_by_path(ov)
    target = pills[str(paths[1])]
    assert target is not None
    target.clicked.emit()
    QApplication.processEvents()
    assert ov._current_item.path == paths[1]
    assert ov._current_idx == 1
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
    assert any("50%" in t for t in first_texts)  # SSIM 0.50 → Source match 50%
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
    (hbar stays 0 after walking to the last of 16).
    """
    mates = [_item(f"fl{i}.png", rank=i) for i in range(1, 17)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    QApplication.processEvents()
    bar = ov._strip_scroll.horizontalScrollBar()
    assert bar.maximum() > bar.minimum(), "need overflow for a follow test"
    assert bar.value() == bar.minimum()
    for _ in range(15):
        ov._walk(1)
        QApplication.processEvents()
    assert ov._current_idx == 15
    assert bar.value() > bar.minimum(), "strip must follow to the last thumb"
    for _ in range(15):
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

    mates = [_item(f"wh{i}.png", rank=i) for i in range(1, 17)]
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


def test_strip_row_spans_full_width_under_mid(qtbot):
    """Strip section lives in a full-width bottom row, not the sidebar."""
    from PySide6.QtWidgets import QWidget

    mates = [_item(f"rw{i}.png", rank=i) for i in (1, 2)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    row = ov.findChild(QWidget, "quicklook_strip_row")
    assert row is not None
    assert row.parentWidget() is ov._content
    # Filmstrip rides the row; no series text widgets exist anywhere.
    assert ov._strip_scroll.parentWidget() is row
    assert ov.findChild(QWidget, "quicklook_series_box") is None
    assert ov.findChild(QWidget, "quicklook_series_header") is None
    assert ov.findChild(QWidget, "quicklook_series_sub") is None
    assert getattr(ov, "_series_header", None) is None
    assert getattr(ov, "_series_sub", None) is None
    # …and nothing series-related stays in the right column layout.
    names = set()
    lay = ov._right_lay
    for i in range(lay.count()):
        w = lay.itemAt(i).widget()
        if w is not None:
            names.add(w.objectName())
    assert "quicklook_series_header" not in names
    assert "quicklook_strip_scroll" not in names
    assert "quicklook_series_box" not in names
    # Row spans the card: wider than the 296px sidebar column.
    assert row.width() > ov.findChild(QWidget, "quicklook_right_scroll").width()
    ov.hide()


def test_strip_hover_is_shared_both_directions(qtbot, tmp_path):
    """Shared family hover: thumb hover lights its pill, pill hover lights
    the thumb — no separate hover per control."""
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

    def _hovered(btn):
        try:
            regions = btn.regions()
        except Exception:
            regions = []
        try:
            for region in regions:
                if ButtonState.HOVERED in btn._controller.states(region.id):
                    return True
        except Exception:
            pass
        return False

    p1 = _real_png(tmp_path, "v.png")
    p2 = _real_png(tmp_path, "o.png")
    viewing = GalleryItem(path=p1, mtime_ns=1, rank=1)
    other = GalleryItem(path=p2, mtime_ns=2, rank=2)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, other])
    QApplication.processEvents()
    pills = _rank_pills_by_path(ov)
    thumbs = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    t0, q0 = thumbs[str(p1)], pills[str(p1)]
    t1, q1 = thumbs[str(p2)], pills[str(p2)]
    # Thumb hover reaches the pills.
    qtbot.mouseMove(t0, QPoint(33, 10))
    QApplication.processEvents()
    assert _hovered(t0)
    assert _hovered(q0)
    assert _hovered(q1)
    # Pill hover reaches back to the thumb.
    qtbot.mouseMove(q1, QPoint(17, 8))
    QApplication.processEvents()
    assert _hovered(t1)
    assert _hovered(q0)
    assert _hovered(q1)
    ov.hide()


def test_strip_row_hidden_for_single_item(qtbot):
    """Ungrouped single item: no lonely-thumb row, the filmstrip hides."""
    from PySide6.QtWidgets import QWidget

    a = _item("solo.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a])
    QApplication.processEvents()
    row = ov.findChild(QWidget, "quicklook_strip_row")
    assert row is not None
    assert row.isHidden()
    b = _item("b.png")
    _show(ov, a, [a, b])
    QApplication.processEvents()
    assert not row.isHidden()
    ov.hide()


def test_ungrouped_items_form_strip_group(qtbot):
    """Ungrouped items share one strip group: opening any of them lists
    every item outside multi-member clusters (folder order), with walks."""
    from types import SimpleNamespace

    from PySide6.QtWidgets import QWidget

    from tabs.image_gallery.models import GalleryItem, Mode
    from tabs.image_gallery.ui.quick_look import QuickLookOverlay

    def _show_full(overlay, item, series, items):
        owner = SimpleNamespace(
            state=SimpleNamespace(mode=Mode.FIDELITY, source_path=None, series=series, items=items)
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

    a = _item("a.png")
    b = _item("b.png")
    c = _item("c.png")
    d = _item("d.png")
    items = [a, b, c, d]
    ov = _make_overlay(qtbot)
    _show_full(ov, c, [[a, b]], items)
    QApplication.processEvents()
    assert [m.path for m in ov._series_items] == [c.path, d.path]
    assert not ov.findChild(QWidget, "quicklook_strip_row").isHidden()
    assert len(_strip_buttons(ov)) == 2
    # Multi-member cluster still wins for its own members.
    _show_full(ov, a, [[a, b]], items)
    QApplication.processEvents()
    assert [m.path for m in ov._series_items] == [a.path, b.path]
    # Singleton cluster joins the ungrouped pool, not a lonely row.
    _show_full(ov, c, [[c]], [a, b, c])
    QApplication.processEvents()
    assert [m.path for m in ov._series_items] == [a.path, b.path, c.path]
    ov.hide()


def test_strip_thumb_rightclick_opens_shared_menu(qtbot, tmp_path, monkeypatch):
    """Real right-click on a NON-viewing thumb pops the shared card menu.

    Same helper as the grid cards (ui/card.py); the target is the thumb's
    own item path, not the currently viewing one.
    """
    from PySide6.QtCore import Qt as _Qt

    import tabs.image_gallery.ui.card.context_menu as _menu_mod

    calls = []
    monkeypatch.setattr(
        _menu_mod,
        "popup_gallery_card_context_menu",
        lambda *a, **k: calls.append((a, k)),
    )
    paths = [_real_png(tmp_path, f"m{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    assert ov._current_idx == 0
    target = None
    for b in _strip_buttons(ov):
        if b.property("gallery_path") == str(paths[2]):
            target = b
            break
    assert target is not None
    qtbot.mouseClick(target, _Qt.MouseButton.RightButton)
    QApplication.processEvents()
    assert len(calls) == 1
    (args, _kwargs) = calls[0]
    assert Path(args[2]) == paths[2]
    ov.hide()


def test_strip_lasso_selects_dragged_thumbs(qtbot, tmp_path):
    """Drag across two thumbs selects both, keeps preview unmoved.

    Marquee selection is Quick Look's own: it writes the overlay's picked
    set only and never touches the owner/grid selection; the trailing
    click is swallowed so _current_idx does not walk.
    """
    from PySide6.QtCore import Qt as _Qt

    paths = [_real_png(tmp_path, f"s{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    assert ov._current_idx == 0
    # Seed a stray owner selection: a strip lasso must leave it alone.
    ov._owner.state.selected_paths = {"/seeded/keep.png"}
    thumbs = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert len(thumbs) == 3
    host = ov._strip_host

    def _drag_span():
        # Live container geometry, read fresh: the strip relayouts
        # asynchronously (pitch drifts between events), so span with a
        # margin instead of trusting pre-drag thumb centers.
        cs = list(ov._strip_buttons)
        g0, g1 = cs[0].geometry(), cs[1].geometry()
        mid = (g0.center().y() + g1.center().y()) // 2
        return (g0.left() - 30, mid), (g1.right() + 30, mid)

    from PySide6.QtCore import QPoint as _QP

    p0t, _ = _drag_span()
    p0 = _QP(*p0t)
    qtbot.mousePress(host, _Qt.MouseButton.LeftButton, pos=p0)
    _, p1t = _drag_span()
    p1 = _QP(*p1t)
    qtbot.mouseMove(host, p1)
    _, p2t = _drag_span()
    qtbot.mouseRelease(host, _Qt.MouseButton.LeftButton, pos=_QP(*p2t))
    QApplication.processEvents()
    assert ov._strip_selected_paths == {str(paths[0]), str(paths[1])}
    assert ov._current_idx == 0
    # The owner/grid selection is untouched by a strip lasso.
    assert ov._owner.state.selected_paths == {"/seeded/keep.png"}
    # Region-level CHECKED (setChecked needs a toggle capability), plus
    # the marker the overlay painter reads over the cover pixmap.
    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState as _BS

    def _checked(btn):
        try:
            return _BS.CHECKED in btn._controller.states("thumb")
        except Exception:
            return False

    assert _checked(thumbs[str(paths[0])])
    assert _checked(thumbs[str(paths[1])])
    assert not _checked(thumbs[str(paths[2])])
    assert bool(thumbs[str(paths[0])].property("strip_selected"))
    assert bool(thumbs[str(paths[1])].property("strip_selected"))
    assert not bool(thumbs[str(paths[2])].property("strip_selected"))
    ov.hide()


def test_strip_plain_click_still_walks(qtbot, tmp_path):
    """Press+release without drag is an ordinary click (lasso uninvolved)."""
    from PySide6.QtCore import Qt as _Qt

    paths = [_real_png(tmp_path, f"w{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    target = None
    for b in _strip_buttons(ov):
        if b.property("gallery_path") == str(paths[2]):
            target = b
            break
    assert target is not None
    qtbot.mouseClick(target, _Qt.MouseButton.LeftButton)
    qtbot.wait(450)
    QApplication.processEvents()
    assert ov._current_idx == 2
    assert ov._strip_selected_paths == set()
    ov.hide()


def test_strip_selection_does_not_mirror_grid(qtbot, tmp_path):
    """Quick Look selection is local: grid picks never seed the strip.

    Multi-selecting cards in the gallery grid and opening a strip must
    leave the strip clean — the grid and the QL strip no longer share
    selection in either direction.
    """
    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState as _BS
    from tabs.image_gallery.ui.quick_look.strip import rebuild_strip

    paths = [_real_png(tmp_path, f"g{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    ov._owner.state.selected_paths = {str(paths[0]), str(paths[2]), "/elsewhere/x.png"}
    ov._owner.state.selected_order = [str(paths[0]), str(paths[2])]
    rebuild_strip(ov)
    QApplication.processEvents()
    assert ov._strip_selected_paths == set()

    def _checked(btn):
        try:
            return _BS.CHECKED in btn._controller.states("thumb")
        except Exception:
            return False

    by_path = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    assert not _checked(by_path[str(paths[0])])
    assert not _checked(by_path[str(paths[1])])
    assert not _checked(by_path[str(paths[2])])
    assert not bool(by_path[str(paths[0])].property("strip_selected"))
    assert not bool(by_path[str(paths[2])].property("strip_selected"))
    ov.hide()


def test_strip_lasso_from_viewport_coords(qtbot, tmp_path):
    """Drag delivered to the scroll viewport selects (ancestor mapping).

    Viewport presses carry viewport coordinates; mapping them with
    widget.mapTo(host) is invalid (host is the viewport's child, not
    its parent — Qt warns 'parent must be in parent hierarchy' and the
    rect lands as garbage). Regression: full-width drags must select.
    """
    from PySide6.QtCore import Qt as _Qt

    paths = [_real_png(tmp_path, f"v{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    host = ov._strip_host
    viewport = ov._strip_scroll.viewport()
    thumbs = {b.property("gallery_path"): b for b in _strip_buttons(ov)}

    def _span_vp():
        # Viewport-space span with margin, read fresh (see host test).
        from PySide6.QtCore import QPoint as _QP

        cs = list(ov._strip_buttons)
        g0 = cs[0].mapTo(viewport, cs[0].rect().topLeft())
        g1 = cs[1].mapTo(viewport, cs[1].rect().bottomRight())
        mid = (g0.y() + g1.y()) // 2
        return _QP(g0.x() - 30, mid), _QP(g1.x() + 30, mid)

    p0, _ = _span_vp()
    qtbot.mousePress(viewport, _Qt.MouseButton.LeftButton, pos=p0)
    _, p1 = _span_vp()
    qtbot.mouseMove(viewport, p1)
    _, p2 = _span_vp()
    qtbot.mouseRelease(viewport, _Qt.MouseButton.LeftButton, pos=p2)
    QApplication.processEvents()
    assert ov._strip_selected_paths == {str(paths[0]), str(paths[1])}
    assert ov._current_idx == 0
    ov.hide()


def test_strip_plain_click_clears_selection(qtbot, tmp_path):
    """A plain strip click drops the lasso selection (local only).

    The release path with no marquee clears the overlay's picked set; the
    trailing button click is still swallowed once (lasso contract), the
    next click walks normally. The owner/grid selection is untouched.
    """
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtCore import QPoint as _QP

    paths = [_real_png(tmp_path, f"k{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    ov._owner.state.selected_paths = set()
    thumbs = {b.property("gallery_path"): b for b in _strip_buttons(ov)}
    host = ov._strip_host

    cs = list(ov._strip_buttons)
    g0, g1 = cs[0].geometry(), cs[1].geometry()
    mid = (g0.center().y() + g1.center().y()) // 2
    qtbot.mousePress(host, _Qt.MouseButton.LeftButton, pos=_QP(g0.left() - 30, mid))
    qtbot.mouseMove(host, _QP(g1.right() + 30, mid))
    qtbot.mouseRelease(host, _Qt.MouseButton.LeftButton, pos=_QP(g1.right() + 30, mid))
    QApplication.processEvents()
    assert ov._strip_selected_paths == {str(paths[0]), str(paths[1])}

    # Plain click on the viewing thumb: the pick is cleared on release;
    # the trailing click is swallowed (no walk) per the lasso contract.
    qtbot.mouseClick(thumbs[str(paths[0])], _Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert ov._strip_selected_paths == set()
    qtbot.wait(450)
    QApplication.processEvents()
    assert ov._current_idx == 0
    assert ov._owner.state.selected_paths == set()

    # The next plain click walks normally with the slate clean.
    qtbot.mouseClick(thumbs[str(paths[2])], _Qt.MouseButton.LeftButton)
    qtbot.wait(450)
    QApplication.processEvents()
    assert ov._current_idx == 2
    assert ov._strip_selected_paths == set()
    ov.hide()


def test_strip_selection_overlay_paints_marker(qtbot, tmp_path):
    """The selection marker is paint, not just controller state.

    Region-level CHECKED renders behind the cover pixmap, so covered
    thumbs need the explicit overlay marker: a selected thumb must change
    pixels (tint + border) while an unselected one leaves them alone.
    """
    from types import SimpleNamespace

    from PySide6.QtCore import QRectF as _QRF
    from PySide6.QtGui import QColor as _QC
    from PySide6.QtGui import QImage as _QImg
    from PySide6.QtGui import QPainter as _QPainter

    from tabs.image_gallery.ui.quick_look.strip import _strip_selection_overlay

    paths = [_real_png(tmp_path, f"o{i}.png") for i in range(2)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    sel, plain = _strip_buttons(ov)[0], _strip_buttons(ov)[1]
    sel.setProperty("strip_selected", True)
    plain.setProperty("strip_selected", False)

    def _painted(btn):
        img = _QImg(66, 44, _QImg.Format.Format_ARGB32)
        img.fill(_QC("#123456"))
        px = _QPainter(img)
        try:
            _strip_selection_overlay(
                px,
                SimpleNamespace(
                    widget=btn, rect=_QRF(0, 0, 66, 44), corner_radii=(6, 6, 6, 6)
                ),
                None,
            )
        finally:
            px.end()
        return img

    before, after_sel, after_plain = (
        _QC("#123456"),
        _painted(sel),
        _painted(plain),
    )
    assert after_sel.pixelColor(33, 22) != before
    assert after_plain.pixelColor(33, 22) == before
    ov.hide()

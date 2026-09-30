"""Wave-A3 coarse-direct regression: quicklook + gallery thumbs on the pyramid seam.

Identity, not presence: distinct sources bind their own bytes
(``payload(i) == content(i)``, never a neighbor's); missing/unbuilt sources
fail closed to placeholder/None; a feed remap (sort reorder) causes no
cross-binding in the controller thumb path.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QImage, QPixmap

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import ThumbnailStatus
from tabs.image_gallery.services import thumbnail_cache
from tabs.image_gallery.tests._gallery_dispatch_doubles import make_gallery_context
from tabs.image_gallery.tests.runtime.test_gallery_races import _WidgetStub
from tabs.image_gallery.ui.quick_look.insets import populate_crop, populate_source_inset
from tabs.image_gallery.ui.quick_look.preview import _pyramid_pixmap_for, populate_preview


def _solid(path: Path, rgb: tuple[int, int, int], size=(800, 600)) -> Path:
    Image.new("RGB", size, rgb).save(path, "PNG")
    return path


def _center_rgb(pixmap) -> tuple[int, int, int]:
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    return (c.red(), c.green(), c.blue())


def _redirect_cache(tmp_path, monkeypatch) -> Path:
    cache_dir = tmp_path / "cache"

    def _dir() -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    monkeypatch.setattr(thumbnail_cache, "thumbnail_cache_dir", _dir)
    return cache_dir


def test_pyramid_pixmap_binds_own_content(qtbot, tmp_path):
    """Distinct images sample distinct bytes — payload(i) == content(i)."""
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    blue = _solid(tmp_path / "blue.png", (0, 0, 255))

    pm_red = _pyramid_pixmap_for(red)
    pm_blue = _pyramid_pixmap_for(blue)

    assert pm_red is not None and not pm_red.isNull()
    assert pm_blue is not None and not pm_blue.isNull()
    assert _center_rgb(pm_red) == (255, 0, 0)
    assert _center_rgb(pm_blue) == (0, 0, 255)
    # Same source twice: identical bytes (stable binding, not noise).
    assert _center_rgb(_pyramid_pixmap_for(red)) == (255, 0, 0)


def test_pyramid_pixmap_missing_source_fails_closed(qtbot, tmp_path):
    """Unbuilt/invalid source → None, never a neighbor's content."""
    assert _pyramid_pixmap_for(tmp_path / "missing.png") is None
    garbage = tmp_path / "garbage.png"
    garbage.write_bytes(b"definitely not an image")
    assert _pyramid_pixmap_for(garbage) is None
    assert _pyramid_pixmap_for(tmp_path / "missing.png", center_third=True) is None


class _FakeCanvas:
    """Minimal canvas double: records set_source, tolerates reveal/fallback."""

    def __init__(self) -> None:
        self.store = None
        self.hidden = 0

    def set_source(self, store) -> None:
        self.store = store

    def clear_source(self) -> None:
        self.store = None

    def hide(self) -> None:
        self.hidden += 1


def test_populate_preview_missing_source_shows_placeholder(qtbot, tmp_path):
    """Quicklook gap path: no preview, never stale/wrong pixels."""
    overlay = SimpleNamespace(
        _preview_full=None,
    )
    item = SimpleNamespace(path=str(tmp_path / "missing.png"), thumbnail=None)
    populate_preview(overlay, item)  # must not raise
    # Gap contract: nothing stashed — never stale/wrong pixels.
    assert overlay._preview_full is None


def test_populate_preview_binds_own_pixels(qtbot, tmp_path):
    """End-to-end golden path: stashed preview holds this item's bytes."""
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    overlay = SimpleNamespace(
        _preview_full=None,
        _preview_canvas=_FakeCanvas(),
    )
    populate_preview(overlay, SimpleNamespace(path=str(red), thumbnail=None))
    assert overlay._preview_full is not None
    assert _center_rgb(overlay._preview_full) == (255, 0, 0)


def test_pyramid_center_third_binds_own_region(qtbot, tmp_path):
    """Crop inset samples the source's own center — not the full frame."""
    path = tmp_path / "target.png"
    base = Image.new("RGB", (900, 900), (255, 0, 0))
    base.paste(Image.new("RGB", (600, 600), (0, 0, 255)), (150, 150))
    base.save(path, "PNG")

    crop = _pyramid_pixmap_for(path, center_third=True, long_edge=512)
    assert crop is not None and not crop.isNull()
    img = crop.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    for x, y in ((w // 2, h // 2), (w // 4, h // 4), (3 * w // 4, 3 * h // 4)):
        c = img.pixelColor(x, y)
        assert (c.red(), c.green(), c.blue()) == (0, 0, 255)

    full = _pyramid_pixmap_for(path, long_edge=512)
    assert full is not None
    corner = full.toImage().pixelColor(4, 4)
    assert (corner.red(), corner.green(), corner.blue()) == (255, 0, 0)


def test_populate_crop_missing_source_leaves_gap(qtbot, tmp_path):
    """Crop inset with no decodable source draws the gap marker, not pixels."""
    regions: dict = {}

    class _Pix:
        def update_region(self, name, pixmap=None, text=None):
            regions[name] = (pixmap, text)

    class _Host:
        def setVisible(self, visible):
            regions["visible"] = visible

    overlay = SimpleNamespace(_crop_host=_Host(), _crop_pix=_Pix(), _preview_full=None)
    populate_crop(overlay, SimpleNamespace(path=str(tmp_path / "missing.png"), thumbnail=None))
    assert regions.get("visible") is True
    pixmap, text = regions.get("thumb", (None, None))
    assert pixmap is None and text == "—"


def test_populate_source_inset_missing_source_shows_gap(qtbot, tmp_path):
    """Source inset with no decodable source shows the gap marker."""
    regions: dict = {}

    class _Pix:
        def update_region(self, name, pixmap=None, text=None):
            regions[name] = (pixmap, text)

        def setToolTip(self, tip):
            pass

    class _Host:
        def setVisible(self, visible):
            regions["visible"] = visible

        def setToolTip(self, tip):
            pass

    class _Label:
        def setText(self, text):
            regions["caption"] = text

        def setToolTip(self, tip):
            pass

    missing = tmp_path / "missing.png"
    overlay = SimpleNamespace(
        _source_path=str(missing),
        _source_inset_host=_Host(),
        _source_inset_pix=_Pix(),
        _source_inset_label=_Label(),
        _owner=SimpleNamespace(state=SimpleNamespace(items=[])),
    )
    populate_source_inset(
        overlay, SimpleNamespace(path=str(tmp_path / "other.png")), is_fidelity=True
    )
    assert regions.get("visible") is True
    pixmap, text = regions.get("thumb", (None, None))
    assert pixmap is None and text == "—"


def test_thumbnail_render_distinct_and_remap_stable(tmp_path, monkeypatch, qtbot):
    """Gallery thumbs: distinct sources → distinct bytes; re-request is stable."""
    _redirect_cache(tmp_path, monkeypatch)
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    blue = _solid(tmp_path / "blue.png", (0, 0, 255))

    red_cache = thumbnail_cache.render_and_cache_thumbnail(red, 111)
    blue_cache = thumbnail_cache.render_and_cache_thumbnail(blue, 222)
    assert red_cache is not None and blue_cache is not None
    assert red_cache != blue_cache
    for cache_path, limit in ((red_cache, thumbnail_cache.THUMBNAIL_SIZE),):
        with Image.open(cache_path) as cached:
            assert cached.size[0] <= limit[0] and cached.size[1] <= limit[1]
    assert _center_rgb(QPixmap(str(red_cache))) == (255, 0, 0)
    assert _center_rgb(QPixmap(str(blue_cache))) == (0, 0, 255)

    # Missing source → None, never a neighbor's file.
    assert thumbnail_cache.render_and_cache_thumbnail(tmp_path / "gone.png", 333) is None

    # Remap analog at the render layer: re-request red after blue → own bytes.
    again = thumbnail_cache.render_and_cache_thumbnail(red, 111)
    assert again == red_cache
    assert _center_rgb(QPixmap(str(again))) == (255, 0, 0)


def _make_ctrl():
    widget = _WidgetStub()
    context, _store = make_gallery_context()
    ctrl = GalleryController(
        widget, thread_pool=QThreadPool.globalInstance(), context=context
    )
    ctrl._start_triage = lambda items, **kw: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl, widget


def test_feed_remap_no_cross_binding(tmp_path, monkeypatch, qtbot):
    """Sort/filter remap: late thumb delivery binds by path, never by index."""
    _redirect_cache(tmp_path, monkeypatch)
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    blue = _solid(tmp_path / "blue.png", (0, 0, 255))
    ctrl, _widget = _make_ctrl()
    ctrl.open_paths([red, blue])
    assert [it.path for it in ctrl.state.items] == [red, blue]
    gen = ctrl._folder_gen

    red_cache = thumbnail_cache.render_and_cache_thumbnail(red, 111)
    blue_cache = thumbnail_cache.render_and_cache_thumbnail(blue, 222)
    assert red_cache is not None and blue_cache is not None

    # Feed remap: sort order flips before any delivery lands.
    ctrl.state.items = list(reversed(ctrl.state.items))
    assert [it.path for it in ctrl.state.items] == [blue, red]

    # Deliver out of order (blue first) — each item must get its own bytes.
    ctrl._on_thumbnail_ready(blue, blue_cache, gen)
    ctrl._on_thumbnail_ready(red, red_cache, gen)
    by_path = {it.path: it for it in ctrl.state.items}
    assert by_path[red].thumbnail_status == ThumbnailStatus.LOADED
    assert by_path[blue].thumbnail_status == ThumbnailStatus.LOADED
    assert _center_rgb(by_path[red].thumbnail) == (255, 0, 0)
    assert _center_rgb(by_path[blue].thumbnail) == (0, 0, 255)

    # Missing/unbuilt delivery → ERROR placeholder, never stale pixels.
    ctrl._on_thumbnail_ready(red, None, gen)
    assert by_path[red].thumbnail_status == ThumbnailStatus.ERROR

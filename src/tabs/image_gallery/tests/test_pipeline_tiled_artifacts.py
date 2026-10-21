"""Stage-2 full-resolution artifact path (wave A3: proxy + tiled artifacts).

The gallery's Stage-2 worker (``run_proxy_stages_sync``) historically ran the
artifact catalog over a bounded proxy (longest edge <= 1024), which destroys
the 8x8 DCT block grid. ``full_res_artifacts=True`` runs the catalog tiled over
a full-resolution ``TiledPixelStore`` while fidelity/camera keep consuming the
bounded proxy.

Guarded here:
- a default (proxy) call misses blocking that the tiled call catches;
- per-item fail-open to the proxy catalog (missing/unreadable full-res store);
- fidelity + camera VALUES are unchanged by the flag (both from the proxy);
- every full-res store created (item + shared source) is closed;
- the default path's decode count is byte-for-byte unchanged.

Pure PIL/numpy (+ the tile store); no torch, no Qt.

P9b: the engine is the ONLY path, so there is no "engine mode" any more — the
tiled catalog is owned by the engine (the proxy only calls it as the retained
fallback when the artifact records are unusable). The catalog/lifecycle/decode
invariants are asserted on that single path; the record↔entry equivalence for
the tiled catalog is covered by ``test_analysis_equivalence.py``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from tabs.image_gallery.services.artifacts import (  # noqa: E402
    Artifact,
    Severity,
)


def _blocky(width: int = 1920, height: int = 1080, offset: int = 24) -> Image.Image:
    """8x8 DCT-like blocks (same construction as test_artifact_tiles)."""
    x = np.arange(width)
    ramp = x % 8
    bx = x // 8
    by = np.arange(height) // 8
    dc = ((bx[None, :] + by[:, None]) % 2) * offset
    base = np.clip(ramp[None, :] + dc, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([base, base, base]), "RGB")


def _paint(path: Path, kind: str, size: tuple[int, int] = (640, 480)) -> Path:
    width, height = size
    if kind == "flat":
        img = Image.new("RGB", (width, height), (128, 128, 128))
    elif kind == "checker":
        from PIL import ImageDraw

        img = Image.new("RGB", (width, height), (128, 128, 128))
        draw = ImageDraw.Draw(img)
        for y in range(0, height, 12):
            for x in range(0, width, 12):
                if (x + y) % 24 == 0:
                    draw.rectangle([x, y, x + 11, y + 11], fill=(255, 255, 255))
    elif kind == "noisy":
        rng = np.random.default_rng(3)
        arr = np.clip(rng.normal(128, 25, (height, width, 3)), 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")
    else:  # pragma: no cover
        raise AssertionError(kind)
    img.save(path)
    return path


def _save_blocky(path: Path, width: int = 1920, height: int = 1080) -> Path:
    _blocky(width, height).save(path)
    return path


class _OpenSpy:
    """Counts ``PIL.Image.open`` calls per resolved path."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self._patcher = None

    def start(self):
        from unittest.mock import patch

        import PIL.Image

        real = PIL.Image.open

        def _counted(target, *a, **k):
            try:
                key = (
                    str(Path(target).resolve())
                    if isinstance(target, (str, Path))
                    else "<other>"
                )
            except Exception:
                key = "<other>"
            self.counts[key] = self.counts.get(key, 0) + 1
            return real(target, *a, **k)

        self._patcher = patch.object(PIL.Image, "open", _counted)
        self._patcher.start()
        return self

    def stop(self):
        if self._patcher is not None:
            self._patcher.stop()
            self._patcher = None

    def opens_for(self, path: Path) -> int:
        try:
            return self.counts.get(str(Path(path).resolve()), 0)
        except Exception:
            return 0


def test_tiled_catches_blocking_proxy_misses(tmp_path: Path) -> None:
    """Red-before/green-after: proxy misses the block grid, tiled catches it."""
    from tabs.image_gallery.services.proxy import (
        clear_proxy_cache,
        run_proxy_stages_sync,
    )

    item = _save_blocky(tmp_path / "blocky.png")
    items = [SimpleNamespace(path=item)]

    clear_proxy_cache()
    proxy_out = run_proxy_stages_sync(items, None, full_res_artifacts=False)
    assert proxy_out[str(item)]["artifacts"][Artifact.BLOCKING] == Severity.CLEAN

    clear_proxy_cache()
    tiled_out = run_proxy_stages_sync(items, None, full_res_artifacts=True)
    assert tiled_out[str(item)]["artifacts"][Artifact.BLOCKING] != Severity.CLEAN


def test_tiled_anchored_source_still_catches(tmp_path: Path) -> None:
    """A readable source does not mask the tiled blocking catch."""
    from tabs.image_gallery.services.proxy import (
        clear_proxy_cache,
        run_proxy_stages_sync,
    )

    source = _paint(tmp_path / "source.png", "flat", size=(1920, 1080))
    item = _save_blocky(tmp_path / "blocky.png")
    items = [SimpleNamespace(path=item)]

    clear_proxy_cache()
    out = run_proxy_stages_sync(items, source, full_res_artifacts=True)
    assert out[str(item)]["artifacts"][Artifact.BLOCKING] != Severity.CLEAN


def test_fail_open_missing_item_keeps_batch(tmp_path: Path) -> None:
    """A missing item path must not raise or poison sibling tiled results."""
    from tabs.image_gallery.services.proxy import (
        clear_proxy_cache,
        run_proxy_stages_sync,
    )

    missing = tmp_path / "does_not_exist.png"
    good = _save_blocky(tmp_path / "good.png")
    items = [SimpleNamespace(path=missing), SimpleNamespace(path=good)]

    clear_proxy_cache()
    out = run_proxy_stages_sync(items, None, full_res_artifacts=True)
    # Unreadable proxy -> fail-closed empty entry, path-keyed, no exception.
    assert out[str(missing)] == {}
    # The healthy sibling still gets its tiled result.
    assert out[str(good)]["artifacts"][Artifact.BLOCKING] != Severity.CLEAN


def test_fail_open_to_proxy_when_store_raises(tmp_path: Path, monkeypatch) -> None:
    """A full-res store failure falls back to the proxy catalog, never raises."""
    from engine.store.tiled_pixel_store import TiledPixelStore
    from tabs.image_gallery.services.proxy import (
        clear_proxy_cache,
        run_proxy_stages_sync,
    )

    source = _paint(tmp_path / "source.png", "flat")
    item = _paint(tmp_path / "item.png", "checker")
    items = [SimpleNamespace(path=item)]

    clear_proxy_cache()
    expected = run_proxy_stages_sync(items, source, full_res_artifacts=False)[str(item)]

    def _boom(cls, *a, **k):  # pragma: no cover - exercised by injection
        raise OSError("synthetic decode failure")

    monkeypatch.setattr(TiledPixelStore, "from_path", classmethod(_boom))
    out = run_proxy_stages_sync(items, source, full_res_artifacts=True)
    assert out[str(item)]["artifacts"] == expected["artifacts"]


def test_fidelity_and_camera_unchanged_with_source(tmp_path: Path) -> None:
    """Fidelity/camera keep the proxy inputs; values match the default call."""
    from tabs.image_gallery.services.proxy import (
        clear_proxy_cache,
        run_proxy_stages_sync,
    )

    source = _paint(tmp_path / "source.png", "flat")
    item = _paint(tmp_path / "item.png", "noisy")
    items = [SimpleNamespace(path=item)]

    clear_proxy_cache()
    proxy_out = run_proxy_stages_sync(
        items, source, include_camera=True, full_res_artifacts=False
    )
    tiled_out = run_proxy_stages_sync(
        items, source, include_camera=True, full_res_artifacts=True
    )
    entry_proxy = proxy_out[str(item)]
    entry_tiled = tiled_out[str(item)]
    assert "fidelity" in entry_proxy and "fidelity" in entry_tiled
    assert entry_tiled["fidelity"] == entry_proxy["fidelity"]
    assert "camera" in entry_proxy and "camera" in entry_tiled
    assert entry_tiled["camera"] == entry_proxy["camera"]


def test_all_full_res_stores_closed(tmp_path: Path, monkeypatch) -> None:
    """Every store created (item + shared source) is closed after the call.

    The engine opens the item store itself (W14) and the proxy opens the shared
    source store — neither may leak it.
    """
    from engine.store.tiled_pixel_store import TiledPixelStore
    from tabs.image_gallery.services.proxy import (
        clear_proxy_cache,
        run_proxy_stages_sync,
    )

    source = _paint(tmp_path / "source.png", "flat")
    item = _save_blocky(tmp_path / "item.png", width=600, height=400)
    items = [SimpleNamespace(path=item)]

    created: list = []
    real = TiledPixelStore.from_path

    def _record(path, *a, **k):
        store = real(path, *a, **k)
        created.append(store)
        return store

    monkeypatch.setattr(TiledPixelStore, "from_path", staticmethod(_record))
    clear_proxy_cache()
    run_proxy_stages_sync(items, source, full_res_artifacts=True)

    assert len(created) >= 2, "expected a shared source store + one item store"
    assert all(store.is_open is False for store in created), [
        store.path for store in created
    ]


def test_default_path_decode_count_unchanged(tmp_path: Path) -> None:
    """full_res_artifacts=False keeps exactly one decode per item + source.

    The engine consumes the shared proxies and opens no files of its own in the
    bounded path, so the engine path adds no decode.
    """
    from tabs.image_gallery.services.proxy import (
        clear_proxy_cache,
        run_proxy_stages_sync,
    )

    source = _paint(tmp_path / "source.png", "flat")
    item = _paint(tmp_path / "item.png", "checker")
    items = [SimpleNamespace(path=item)]

    clear_proxy_cache()
    spy = _OpenSpy().start()
    try:
        out = run_proxy_stages_sync(
            items, source, include_camera=True, full_res_artifacts=False
        )
    finally:
        spy.stop()
    assert str(item) in out
    assert spy.opens_for(item) == 1
    assert spy.opens_for(source) == 1

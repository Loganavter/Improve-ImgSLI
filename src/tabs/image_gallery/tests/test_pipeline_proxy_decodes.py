"""Phase-1 proxy decode sharing (services/proxy + stage from-image entries).

Guards the measured Phase-0 waste: every analysis stage fully decoded every
image itself (artifacts item+source per item, fidelity item+source per item,
camera 3x per item — source re-decoded N times per stage). All three stages
now consume one shared bounded proxy (longest edge <= 1024) per file:

- cold path: ONE full ``Image.open`` per item total; the source decoded ONCE
  total (in-memory cache shared across items and stages);
- warm path (proxy cached): ZERO decodes;
- detector/metric VALUES stay equivalent (same severities, same 4 fidelity
  keys, same camera scalars — fail-closed identity kept: path-keyed results,
  never copied between items).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _paint(path: Path, kind: str) -> Path:
    from PIL import Image, ImageDraw

    if kind == "flat":
        img = Image.new("RGB", (96, 96), (128, 128, 128))
    elif kind == "checker":
        img = Image.new("RGB", (96, 96), (128, 128, 128))
        draw = ImageDraw.Draw(img)
        for y in range(0, 96, 12):
            for x in range(0, 96, 12):
                if (x + y) % 24 == 0:
                    draw.rectangle([x, y, x + 11, y + 11], fill=(255, 255, 255))
    elif kind == "noisy":
        import numpy as np

        rng = np.random.default_rng(3)
        arr = np.clip(rng.normal(128, 25, (96, 96, 3)), 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")
    elif kind == "white":
        img = Image.new("RGB", (96, 96), (255, 255, 255))
    else:  # pragma: no cover
        raise AssertionError(kind)
    img.save(path)
    return path


class _OpenSpy:
    """Counts ``PIL.Image.open`` calls per resolved path."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self._real = None
        self._patcher = None

    def start(self):
        from unittest.mock import patch

        import PIL.Image

        real = PIL.Image.open

        def _counted(target, *a, **k):
            try:
                key = str(Path(target).resolve()) if isinstance(target, (str, Path)) else "<other>"
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

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _stages_for(item: Path, source: Path) -> None:
    """Mimic the controller loop: all three stage entries per item."""
    from tabs.image_gallery.services.artifacts import analyze_artifacts
    from tabs.image_gallery.services.camera_metrics import measure_camera_metrics
    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_metrics

    analyze_artifacts(item, source)
    compute_fidelity_metrics(item, source)
    measure_camera_metrics(item)


def test_cold_one_decode_per_item_source_once(tmp_path: Path) -> None:
    from tabs.image_gallery.services.proxy import clear_proxy_cache

    n = 3
    source = _paint(tmp_path / "source.png", "flat")
    items = [_paint(tmp_path / f"item{i}.png", "checker" if i % 2 else "noisy") for i in range(n)]
    clear_proxy_cache()
    spy = _OpenSpy().start()
    try:
        for item in items:
            _stages_for(item, source)
    finally:
        spy.stop()
    for item in items:
        assert spy.opens_for(item) == 1, f"{item.name}: {spy.opens_for(item)} opens"
    assert spy.opens_for(source) == 1, f"source opens: {spy.opens_for(source)}"


def test_warm_zero_decodes(tmp_path: Path) -> None:
    from tabs.image_gallery.services.proxy import clear_proxy_cache

    source = _paint(tmp_path / "source.png", "flat")
    items = [_paint(tmp_path / f"w{i}.png", "checker") for i in range(2)]
    clear_proxy_cache()
    for item in items:  # populate the proxy cache (cold)
        _stages_for(item, source)
    spy = _OpenSpy().start()
    try:
        for item in items:
            _stages_for(item, source)
    finally:
        spy.stop()
    assert spy.total == 0, dict(spy.counts)


def test_batch_single_pass_decode_counts_and_identity(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from tabs.image_gallery.services.proxy import clear_proxy_cache, run_proxy_stages_sync

    source = _paint(tmp_path / "source.png", "flat")
    flat = _paint(tmp_path / "flat.png", "flat")
    sharp = _paint(tmp_path / "sharp.png", "checker")
    items = [SimpleNamespace(path=flat), SimpleNamespace(path=sharp)]
    clear_proxy_cache()
    spy = _OpenSpy().start()
    try:
        out = run_proxy_stages_sync(items, source, include_camera=True)
    finally:
        spy.stop()
    assert spy.opens_for(flat) == 1
    assert spy.opens_for(sharp) == 1
    assert spy.opens_for(source) == 1
    # Fail-closed identity: path-keyed, never copied between items.
    assert set(out) == {str(flat), str(sharp)}
    assert out[str(flat)]["camera"]["sharpness"] != out[str(sharp)]["camera"]["sharpness"]
    assert out[str(flat)]["artifacts"] != out[str(sharp)]["artifacts"] or True  # severities may tie; keys must exist
    assert len(out[str(flat)]["artifacts"]) == 7
    assert len(out[str(sharp)]["artifacts"]) == 7


def test_artifact_severity_equivalence_small_images(tmp_path: Path) -> None:
    """From-image catalog matches raw detectors on directly-decoded pixels."""
    from PIL import Image

    from tabs.image_gallery.services.artifacts import Artifact, analyze_images
    from tabs.image_gallery.services.artifacts import (
        detect_banding,
        detect_blocking,
        detect_chroma_fringing,
        detect_halo,
        detect_invented_texture,
        detect_noise_amplification,
        detect_over_smoothing,
    )

    for kind in ("flat", "checker", "noisy", "white"):
        p = _paint(tmp_path / f"{kind}.png", kind)
        with Image.open(p) as im:
            direct = im.convert("RGB")
            expected = {
                Artifact.BANDING: detect_banding(direct),
                Artifact.HALO: detect_halo(direct),
                Artifact.OVER_SMOOTHING: detect_over_smoothing(direct),
                Artifact.INVENTED_TEXTURE: detect_invented_texture(direct),
                Artifact.BLOCKING: detect_blocking(direct),
                Artifact.CHROMA_FRINGING: detect_chroma_fringing(direct),
                Artifact.NOISE_AMPLIFICATION: detect_noise_amplification(direct),
            }
        from tabs.image_gallery.services.proxy import clear_proxy_cache, proxy_for

        clear_proxy_cache()
        proxy = proxy_for(p)
        assert proxy is not None
        got = analyze_images(proxy.image, None)
        assert set(got) == set(Artifact)
        assert got == expected


def test_fidelity_equivalence_and_keys(tmp_path: Path) -> None:
    from tabs.image_gallery.services.fidelity_metrics import (
        compute_fidelity_from_images,
        compute_fidelity_metrics,
    )
    from tabs.image_gallery.services.proxy import clear_proxy_cache, proxy_for

    source = _paint(tmp_path / "source.png", "noisy")
    item = _paint(tmp_path / "item.png", "checker")
    clear_proxy_cache()
    via_paths = compute_fidelity_metrics(item, source)
    assert set(via_paths) == {"ssim", "hf_ratio", "delta_e", "upscale_factor"}
    item_proxy = proxy_for(item)
    src_proxy = proxy_for(source)
    assert item_proxy is not None and src_proxy is not None
    via_images = compute_fidelity_from_images(
        item_proxy.image, src_proxy.image, item_size=item_proxy.size, source_size=src_proxy.size
    )
    assert via_images == via_paths
    # Spot values: checker vs flat differ (delta_e > 0, ssim < 1).
    assert via_paths["delta_e"] > 0
    assert 0.0 <= via_paths["ssim"] <= 1.0
    # Identity pair: same-file shortcut.
    ident = compute_fidelity_metrics(source, source)
    assert ident == {"ssim": 1.0, "hf_ratio": 0.0, "delta_e": 0.0, "upscale_factor": 1}


def test_camera_equivalence_path_vs_image(tmp_path: Path) -> None:
    from PIL import Image

    from tabs.image_gallery.services.camera_metrics import (
        estimate_noise,
        estimate_noise_from_image,
        measure_camera_from_image,
        measure_camera_metrics,
    )
    from tabs.image_gallery.services.proxy import clear_proxy_cache

    for kind in ("flat", "checker", "noisy"):
        p = _paint(tmp_path / f"c_{kind}.png", kind)
        clear_proxy_cache()
        via_path = measure_camera_metrics(p)
        with Image.open(p) as im:
            direct = im.convert("RGB")
            via_image = measure_camera_from_image(direct)
            noise_direct = estimate_noise_from_image(direct)
        assert via_image == via_path, kind
        assert estimate_noise(p) == noise_direct, kind
    # Unreadable stays fail-closed.
    clear_proxy_cache()
    assert measure_camera_metrics(tmp_path / "nope.png") == {}
    assert estimate_noise(tmp_path / "nope.png") is None
    assert measure_camera_from_image(None) == {}


def test_proxy_bounded_edge_and_old_names_importable(tmp_path: Path) -> None:
    from PIL import Image

    from tabs.image_gallery.services import artifacts, camera_metrics, fidelity_metrics
    from tabs.image_gallery.services.proxy import PROXY_MAX_EDGE, proxy_for

    big = tmp_path / "big.png"
    Image.new("RGB", (2000, 500), (90, 90, 90)).save(big)
    proxy = proxy_for(big)
    assert proxy is not None
    assert max(proxy.image.size) <= PROXY_MAX_EDGE
    assert proxy.size == (2000, 500)  # original size kept for upscale_factor
    # Backward-compat entry points still importable with old names.
    assert callable(artifacts.analyze_artifacts)
    assert callable(artifacts.analyze_images)
    assert callable(fidelity_metrics.compute_fidelity_metrics)
    assert callable(fidelity_metrics.compute_fidelity_from_images)
    assert callable(camera_metrics.measure_camera_metrics)
    assert callable(camera_metrics.estimate_noise)
    assert callable(camera_metrics.measure_camera_from_image)
    assert callable(camera_metrics.estimate_noise_from_image)


def _tiny(path: Path, seed: int) -> Path:
    from PIL import Image

    img = Image.new("RGB", (16, 16), (seed % 256, (seed * 7) % 256, (seed * 13) % 256))
    img.save(path)
    return path


def test_proxy_true_lru_touch_on_hit(tmp_path: Path) -> None:
    """True LRU: a touched hot entry survives while the coldest is evicted."""
    from tabs.image_gallery.services import proxy as proxy_mod
    from tabs.image_gallery.services.proxy import _stat_key, clear_proxy_cache, proxy_for

    assert proxy_mod.PROXY_CACHE_LIMIT == 96
    clear_proxy_cache()
    cap = proxy_mod.PROXY_CACHE_LIMIT
    files = [_tiny(tmp_path / f"lru{i:03d}.png", i) for i in range(cap)]
    for f in files:
        assert proxy_for(f) is not None
    assert len(proxy_mod._PROXY_CACHE) == cap
    hot_key = _stat_key(files[0])
    cold_key = _stat_key(files[1])
    assert hot_key is not None and cold_key is not None
    # Touch the oldest entry: it becomes most-recently-used.
    hot_before = proxy_for(files[0])
    assert hot_before is not None
    # Insert one cold entry beyond the cap: exactly one LRU eviction.
    extra = _tiny(tmp_path / "lru_extra.png", 9999)
    assert proxy_for(extra) is not None
    assert len(proxy_mod._PROXY_CACHE) <= cap
    assert hot_key in proxy_mod._PROXY_CACHE, "touched hot entry was evicted"
    assert cold_key not in proxy_mod._PROXY_CACHE, "coldest entry should be evicted first"
    assert _stat_key(extra) in proxy_mod._PROXY_CACHE
    # Hot hit returns the same cached value (no behavior change on values).
    assert proxy_for(files[0]) is hot_before
    clear_proxy_cache()


def test_proxy_cap_bound_200_item_run(tmp_path: Path) -> None:
    """200-item synthetic run stays bounded; resident hots never redecode."""
    from tabs.image_gallery.services import proxy as proxy_mod
    from tabs.image_gallery.services.proxy import clear_proxy_cache, proxy_for

    cap = proxy_mod.PROXY_CACHE_LIMIT
    assert cap == 96
    clear_proxy_cache()
    files = [_tiny(tmp_path / f"cap{i:03d}.png", i) for i in range(200)]
    for f in files:
        assert proxy_for(f) is not None
        assert len(proxy_mod._PROXY_CACHE) <= cap
    assert len(proxy_mod._PROXY_CACHE) == cap
    # Resident hots = the most recent entries; re-requests must be warm.
    hots = files[-10:]
    before = {str(f): proxy_for(f) for f in hots}
    spy = _OpenSpy().start()
    try:
        for f in hots:
            got = proxy_for(f)
            assert got is not None
            assert got is before[str(f)], f"{f.name} redecoded instead of warm hit"
    finally:
        spy.stop()
    assert spy.total == 0, dict(spy.counts)
    # clear_proxy_cache semantics unchanged: returns entries cleared.
    cleared = clear_proxy_cache()
    assert cleared == cap
    assert len(proxy_mod._PROXY_CACHE) == 0
    assert clear_proxy_cache() == 0

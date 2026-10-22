"""Scroll contention: the per-card VLM payload is CPU the scroll has to wait for.

Owner measurement 2026-10-22 (36-image series, 40 wheel notches): 6.6 s idle vs
**21.4 s while an analysis runs**, GUI-loop gaps 288-514 ms. PR #574 removed the
paint half (activity-pulse pill rect, cached scaled cover), so what is left is
CPU contention on the dedicated gallery pool:

* ``_run_ai_for_visible`` (``use_cases/ai_analysis.py:377``) queues up to
  ``_AI_VISIBLE_CAP`` = 12 cards, each with ``sample_count`` = 3 draws;
* every draw built a payload from the FULL-RESOLUTION file — ``read_bytes`` →
  ``base64.b64encode`` → ``json.dumps`` (two multi-MB copies per draw,
  ``services/ai_client/request.py`` + ``transport.py:178``), three times per
  card, with no bound on how many builders run at once;
* the pool that must also land the scroll's visible thumbnails has 4-8 threads
  (``use_cases/scheduler.py:39-60``), so all of them can sit inside an encode
  while a wheel notch waits for a free thread — priority cannot help a thread
  that does not exist.

The setting that already bounds VLM uploads (``vlm_max_edge_px``, default
``decode_policy.VLM_DEFAULT_MAX_EDGE_PX`` = 1024) reached only the tie-break and
the profile probe; the per-card path sent the original bytes (defect B2 in the
``request`` module docstring). These tests pin the three seams that were
missing: the per-card ceiling, the encode gate, and a Stage-2 chunk that can
stop when the folder generation changes.

Red-before: ``encode_wire_image`` / ``wire_encode_gate_stats`` /
``run_proxy_stages_sync(cancel=...)`` did not exist, and the per-card payload
carried the full-resolution PNG.
"""

from __future__ import annotations

import base64
import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image


def _big_png(path: Path, size=(2400, 1800)) -> Path:
    """An incompressible oversized PNG (large file, honest payload ratio).

    Deliberately NOT ``Image.effect_noise``: that consumes Pillow's global noise
    RNG, and ``tests/test_series_override.py`` builds its "these two noise images
    must not cluster" pair from the same sequence — a served-in-order suite
    failure that is not a product bug (measured 2026-10-22: ``cluster_items``
    clusters any pair whose HSV embedding distance is ``<= 0.25``, and two gray
    noise images sit right at that line depending on the RNG state).
    ``random.Random(seed)`` keeps this fixture deterministic and side-effect free.
    """
    import random

    w, h = size
    data = random.Random(7).randbytes(w * h * 3)
    Image.frombytes("RGB", (w, h), data).save(path, format="PNG")
    return path


# -- 1. the per-card payload ceiling ---------------------------------------


def test_the_per_card_payload_is_capped_and_smaller_than_the_source(
    tmp_path, monkeypatch
) -> None:
    """A 2400-px card ships a <=1024-edge JPEG, not the 13 MB original."""
    from tabs.image_gallery.services import vlm
    from tabs.image_gallery.services.ai_client import request

    monkeypatch.setattr(vlm, "get_vlm_max_edge", lambda: 1024)
    request.reset_wire_encode_gate()
    path = _big_png(tmp_path / "card.png")
    source_bytes = path.stat().st_size

    payload = request.build_request(path, model="m")
    url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,"), url[:40]
    wire = base64.b64decode(url.split(";base64,", 1)[1])
    with Image.open(io.BytesIO(wire)) as im:
        assert max(im.size) == 1024, im.size
    assert len(wire) * 5 < source_bytes, (len(wire), source_bytes)


def test_the_wire_edge_follows_the_user_setting(tmp_path, monkeypatch) -> None:
    """The setting is the ceiling: 768 means 768, and the payload gets smaller."""
    from tabs.image_gallery.services import vlm
    from tabs.image_gallery.services.ai_client import request

    monkeypatch.setattr(vlm, "get_vlm_max_edge", lambda: 768)
    path = _big_png(tmp_path / "card.png", size=(1600, 1200))

    wire = request.encode_wire_path(path)

    assert (wire.mime, wire.edge) == ("jpeg", 768)
    assert wire.wire_bytes * 4 < wire.source_bytes


def test_the_wire_edge_actually_used_reaches_the_trace(tmp_path, monkeypatch) -> None:
    """The log names the edge/mime the model received (no silent cap)."""
    from tabs.image_gallery.services import vlm
    from tabs.image_gallery.services.ai_client import request

    monkeypatch.setattr(vlm, "get_vlm_max_edge", lambda: 768)
    lines: list[str] = []
    monkeypatch.setattr(
        request, "_ai_debug", lambda fmt, *args, **kwargs: lines.append(fmt % args)
    )
    path = _big_png(tmp_path / "card.png", size=(1600, 1200))

    request.encode_wire_path(path)

    assert any("wire image" in line and "edge=768" in line for line in lines), lines


def test_the_k_draws_encode_the_wire_image_once(tmp_path, monkeypatch) -> None:
    """k=3 is three POSTs of ONE wire copy, not three full encodes.

    The wire image does not depend on the draw (only the seed does), so building
    it per draw multiplied the GIL-bound work by ``sample_count``.
    """
    from tabs.image_gallery.services import ai_client
    from tabs.image_gallery.services.ai_client import request

    path = _big_png(tmp_path / "card.png", size=(1600, 1200))
    calls = {"encode": 0, "post": 0}
    real_encode = request.encode_wire_image

    def _counting_encode(*args, **kwargs):
        calls["encode"] += 1
        return real_encode(*args, **kwargs)

    def _fake_post(*args, **kwargs):
        calls["post"] += 1
        return {}

    monkeypatch.setattr(request, "encode_wire_image", _counting_encode)
    monkeypatch.setattr(ai_client, "call_sync", _fake_post)
    monkeypatch.setattr(ai_client, "parse_response", lambda *a, **k: "read")
    monkeypatch.setattr(ai_client, "merge_samples", lambda results: results[-1])

    read = ai_client.analyze_image_sync(
        path,
        base_url="https://openrouter.ai/api/v1",
        api_key="key",
        model="model",
        samples=3,
    )

    assert read == "read"
    assert calls["post"] == 3, calls
    assert calls["encode"] == 1, calls


def test_a_rotated_photo_is_sent_upright(tmp_path, monkeypatch) -> None:
    """Downscaling must not drop the EXIF orientation (the model saw it before)."""
    from tabs.image_gallery.services import vlm
    from tabs.image_gallery.services.ai_client import request

    monkeypatch.setattr(vlm, "get_vlm_max_edge", lambda: 256)
    portrait = Image.frombytes(
        "RGB", (2000, 1500), __import__("random").Random(3).randbytes(2000 * 1500 * 3)
    )
    exif = Image.Exif()
    exif[274] = 6  # orientation: rotate 90 CW (a landscape file shown as portrait)
    path = tmp_path / "rotated.jpg"
    portrait.save(path, format="JPEG", exif=exif)

    wire = request.encode_wire_path(path)

    with Image.open(io.BytesIO(base64.b64decode(wire.data_b64))) as sent:
        width, height = sent.size
    assert wire.mime == "jpeg"
    assert max(width, height) == 256, (width, height)
    assert height > width, f"the EXIF rotation was dropped: {width}x{height}"


# -- 2. the encode gate ----------------------------------------------------


def test_the_encode_gate_bounds_concurrent_payload_builders(monkeypatch) -> None:
    """With N slots, N builders run at once — never more (12 cards x k draws)."""
    from tabs.image_gallery.services.ai_client import request

    monkeypatch.setenv(request.WIRE_ENCODE_SLOTS_ENV, "1")
    request.reset_wire_encode_gate()
    observed: list[int] = []

    def _slow_reencode(raw, mime, cap, prefer_jpeg):
        observed.append(request.wire_encode_gate_stats()["active"])
        time.sleep(0.03)
        return (b"small", "jpeg", int(cap))

    monkeypatch.setattr(request, "_reencode_within_edge", _slow_reencode)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _: request.encode_wire_image(b"raw" * 100, "png", max_edge=64),
                range(4),
            )
        )

    stats = request.wire_encode_gate_stats()
    assert stats["slots"] == 1, stats
    assert stats["peak"] == 1, stats
    assert observed and max(observed) == 1, observed


def test_the_encode_gate_is_configurable(monkeypatch) -> None:
    """The slot count is an env knob (tests / a machine with more cores)."""
    from tabs.image_gallery.services.ai_client import request

    monkeypatch.setenv(request.WIRE_ENCODE_SLOTS_ENV, "3")
    request.reset_wire_encode_gate()
    assert request.wire_encode_gate_stats()["slots"] == 3
    monkeypatch.setenv(request.WIRE_ENCODE_SLOTS_ENV, "not-a-number")
    request.reset_wire_encode_gate()
    assert request.wire_encode_gate_stats()["slots"] == request.DEFAULT_WIRE_ENCODE_SLOTS
    request.reset_wire_encode_gate()


# -- 3. the preemptible Stage-2 chunk -------------------------------------


def _fake_proxy_layer(monkeypatch):
    """Stub the detector layer so a 50-item chunk runs without real pixels."""
    from tabs.image_gallery.services import analysis_bridge, artifacts, proxy

    class _FakeProxy:
        image = object()

    monkeypatch.setattr(proxy, "proxy_for", lambda path: _FakeProxy() if path else None)
    monkeypatch.setattr(analysis_bridge, "engine_records", lambda *a, **k: None)
    monkeypatch.setattr(
        analysis_bridge, "stage_dicts_from_records", lambda *a, **k: {}
    )
    monkeypatch.setattr(artifacts, "analyze_images", lambda *a, **k: {})
    return proxy


def test_a_stage2_chunk_stops_early_on_a_generation_bump(monkeypatch) -> None:
    """A cancelled folder must not finish its 50-item pass."""
    proxy = _fake_proxy_layer(monkeypatch)
    items = [SimpleNamespace(path=Path(f"/gallery/{i:03d}.png")) for i in range(50)]
    checks = {"yields": 0}

    def _cancel() -> bool:
        checks["yields"] += 1  # one call per yield boundary of the pass
        return checks["yields"] > 1  # the user opened another folder mid-pass

    out = proxy.run_proxy_stages_sync(items, None, cancel=_cancel)

    assert checks["yields"] >= 2, "the pass never yielded to the scheduler"
    assert 0 < len(out) < 50, f"the cancelled pass produced {len(out)}/50 items"


def test_a_stage2_chunk_yields_the_gil_between_items(monkeypatch) -> None:
    """A live pass gives the pool a slice every few items, and ends when done."""
    proxy = _fake_proxy_layer(monkeypatch)
    items = [SimpleNamespace(path=Path(f"/gallery/{i:03d}.png")) for i in range(10)]
    yields: list[int] = []
    sleeps = []
    real_sleep = proxy.time.sleep

    def _count_sleep(seconds) -> None:
        sleeps.append(seconds)
        real_sleep(seconds)

    monkeypatch.setattr(proxy.time, "sleep", _count_sleep)

    def _cancel() -> bool:
        yields.append(1)  # one call per yield boundary
        return False

    out = proxy.run_proxy_stages_sync(items, None, cancel=_cancel)

    assert len(out) == 10
    assert len(yields) >= 2, yields
    assert sleeps and set(sleeps) == {0}, sleeps


def test_the_proxy_scheduler_hands_each_chunk_a_generation_cancel(monkeypatch) -> None:
    """The scheduler (not the worker) owns the generation check it passes in."""
    from tabs.image_gallery.use_cases import proxy_pass

    started: list = []

    class _Signal:
        def __init__(self) -> None:
            self.slots: list = []

        def connect(self, fn) -> None:
            self.slots.append(fn)

    class _Signals:
        def __init__(self) -> None:
            self.result = _Signal()
            self.error = _Signal()

    class _Worker:
        def __init__(self, fn, *args, **kwargs) -> None:
            self.fn = fn
            self.args = args
            self.kwargs = kwargs
            self.signals = _Signals()
            started.append(self)

    class _Owner:
        _folder_gen = 7
        _proxy_done = 0
        _proxy_total = 0
        state = SimpleNamespace(mode=None)

        def _tracked(self, fn):
            return fn

        def _pool_start(self, worker, priority) -> None:
            return None

        def _is_current_folder_gen(self, gen) -> bool:
            return int(gen) == int(self._folder_gen)

        def _on_proxy_batch_ready(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr(proxy_pass, "GenericWorker", _Worker)
    owner = _Owner()
    items = [SimpleNamespace(path=Path(f"/gallery/{i:03d}.png")) for i in range(60)]

    proxy_pass._schedule_proxy(owner, items, 2, None, 7)

    assert len(started) == 2, "60 items must still be two 50-item chunks"
    cancel = started[0].args[-1]
    assert callable(cancel), started[0].args
    assert cancel() is False
    owner._folder_gen = 8
    assert cancel() is True


# -- 4. the settle-time hydrate -------------------------------------------


def test_the_settle_hydrate_is_time_sliced(monkeypatch, qtbot) -> None:
    """The settle hydrate runs in bounded batches, never one long GUI stall.

    Ordering is preserved because ``analyze()`` is cache-first
    (``use_cases/ai_analyze.py:183``): an item this pass leaves behind is filled
    by that HIT before any request is built.
    """
    from tabs.image_gallery.services import ai_cache
    from tabs.image_gallery.use_cases import ai_analysis

    hydrated: list = []

    def _fake_hydrate_item(item, identity) -> bool:
        time.sleep(0.005)
        if getattr(item, "analysis", None) is not None:
            return True
        item.analysis = "cached"
        hydrated.append(item)
        return True

    monkeypatch.setattr(ai_cache, "hydrate_item", _fake_hydrate_item)
    monkeypatch.setattr(ai_analysis, "analysis_identity_for", lambda owner, ctx=None: {})

    class _Widget:
        def __init__(self) -> None:
            self.refreshed: list = []

        def refresh_cards(self, items) -> None:
            self.refreshed.append(list(items))

        def refresh_card(self, item) -> None:
            self.refreshed.append([item])

    owner = SimpleNamespace(
        _folder_gen=3,
        widget=_Widget(),
        _refresh_open_quick_look=lambda: None,
    )
    items = [SimpleNamespace(path=Path(f"/g/{i}.png"), analysis=None) for i in range(12)]

    filled = ai_analysis._hydrate_ai_cache(owner, items, budget_ms=6)

    assert filled < len(items), (
        "the hydrate ran the whole 12-item pass in one GUI batch "
        f"(filled={filled}); it has no time budget"
    )
    qtbot.waitUntil(lambda: len(hydrated) == len(items), timeout=2000)
    assert len(hydrated) == len(items)

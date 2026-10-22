"""A known folder must not re-run the local Stage-2 detector on reopen.

The owner's promise "a known image is never re-decoded and re-detected on
reopen" held for the AI/Jev scorecards but not for the LOCAL pass, which lived
only in memory: every reopen re-decoded and re-ran the artifact catalog,
localization and camera/fidelity detectors for every known image.

Falsification story (this file FAILS on the pre-change tree):

* the triage tail started the proxy pass for the WHOLE pool unconditionally —
  its only skip gate is ``_analysis_fingerprint``, an in-memory memo whose
  presence flags are empty after a restart — so ``detectors["detector"]`` counts
  one run per image on the reopen (asserted ``== 0``);
* ``services/metrics_cache`` does not exist on that tree, so the corruption /
  version-bump tests fail on import (no store to degrade to a MISS).

The detector is counted at its entry point (``analysis_bridge.engine_records``)
and decodes at ``proxy._build_proxy`` — never a timing assertion. Dots are read
through ``use_cases.quality`` (the card's own rule) and ranks through the pure
``rank_fusion.rank_series`` (what ``_apply_fusion_ranks`` writes), so "the same
dots/ranks as a cold run" is compared number-for-number.

What is stubbed: the scheduler (``_start_proxy_analysis`` runs the real
``run_proxy_stages_sync`` synchronously) and the settle's AI/Jev tails, which
have their own tests (``test_local_done_ordering.py``). The gate, the delivery,
the store and the apply tails are the real ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tabs.image_gallery.models import ActivityPhase, GalleryItem, Mode
from tabs.image_gallery.services import metrics_cache, proxy
from tabs.image_gallery.services.activity import activity_of
from tabs.image_gallery.services.rank_fusion import rank_series
from tabs.image_gallery.use_cases import local_metrics, proxy_pass, quality, triage_run


# -- fixtures ---------------------------------------------------------------


def _write_png(path: Path, seed: int) -> Path:
    """A small image with 8px blocks + a colour step, so detectors answer."""
    image = Image.new("RGB", (96, 64), (140, 60, 40))
    pixels = image.load()
    for x in range(0, 96, 8):
        for y in range(0, 64, 8):
            pixels[x, y] = ((seed * 37 + x) % 256, (seed * 11 + y) % 256, seed * 5 % 256)
    image.save(path)
    return path


def _items(paths) -> list[GalleryItem]:
    """Fresh pool objects, exactly what a reopen rebuilds from a scan."""
    return [
        GalleryItem(path=Path(p), mtime_ns=Path(p).stat().st_mtime_ns) for p in paths
    ]


@pytest.fixture
def gallery(tmp_path, monkeypatch):
    """Hermetic cache root + reset store/proxy process state."""
    monkeypatch.setenv("IMGSLI_PROJECT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(metrics_cache, "_version_checked", False, raising=False)
    monkeypatch.setattr(metrics_cache, "_invalidated", 0, raising=False)
    proxy.clear_proxy_cache()
    monkeypatch.setattr(triage_run, "_run_ai_on_settle", lambda owner: None)
    monkeypatch.setattr(triage_run, "_run_jev_on_settle", lambda owner: None)
    paths = [_write_png(tmp_path / f"shot_{i}.png", i) for i in range(2)]
    yield paths
    proxy.clear_proxy_cache()


@pytest.fixture
def detectors(monkeypatch):
    """Count the detector entry point and the decode entry point."""
    from tabs.image_gallery.services import analysis_bridge

    calls = {"detector": 0, "decode": 0}
    real_records = analysis_bridge.engine_records
    real_build = proxy._build_proxy

    def _records(*args, **kwargs):
        calls["detector"] += 1
        return real_records(*args, **kwargs)

    def _build(*args, **kwargs):
        calls["decode"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr(analysis_bridge, "engine_records", _records)
    monkeypatch.setattr(proxy, "_build_proxy", _build)
    return calls


class _Widget:
    """The card surface the apply tails repaint through."""

    def __init__(self) -> None:
        self.refreshed: list = []

    def set_triage(self, *args, **kwargs) -> None:  # noqa: D401 - surface seam
        return None

    def set_triage_done(self, *args, **kwargs) -> None:
        return None

    def refresh_cards(self, items) -> None:
        self.refreshed.append(list(items))

    def refresh_card(self, item) -> None:
        self.refreshed.append([item])


class _Owner:
    """Minimal controller double: exactly the seams ``_apply_triage_result`` uses."""

    def __init__(self, items, mode=Mode.FIDELITY) -> None:
        self.state = SimpleNamespace(
            items=list(items),
            mode=mode,
            series=[],
            metric_profile=None,
            source_path=None,
        )
        self.widget = _Widget()
        self._last_analysis_fingerprint = None
        self._folder_gen = 1
        self._proxy_done = 0
        self._proxy_total = 0
        #: One entry per proxy batch actually started (a skip means no entry).
        self.proxy_batches: list = []

    # -- the frozen scheduler seam, synchronous for the test -----------------
    def _start_proxy_analysis(self, items, source_path, mode, *, on_done=None) -> None:
        """The REAL triage seam: it decides the lanes, then calls ``schedule``."""
        return proxy_pass._start_proxy_analysis(
            self, list(items), source_path, mode, on_done=on_done
        )

    def schedule(
        self,
        items,
        priority,
        *,
        op="thumb",
        source=None,
        gen=None,
        wanted=None,
        include_camera=None,
        full_res_artifacts=False,
        on_done=None,
    ) -> int:
        """Stand-in for the chunked worker pool: run the chunk inline.

        It forwards exactly the arguments ``_schedule_proxy`` forwards to the
        delivery (the identity inputs the store needs), so the persistence path
        is exercised, not re-implemented.
        """
        if op != "proxy":
            return 0
        from tabs.image_gallery.services.proxy import run_proxy_stages_sync

        batch = list(items)
        self.proxy_batches.append(len(batch))
        result = run_proxy_stages_sync(
            batch,
            source,
            include_camera=bool(include_camera),
            full_res_artifacts=bool(full_res_artifacts),
        )
        proxy_pass._on_proxy_batch_ready(
            self,
            result,
            gen,
            wanted,
            source=source,
            include_camera=include_camera,
            full_res_artifacts=bool(full_res_artifacts),
        )
        if on_done is not None:
            on_done()
        return 1

    # -- the apply tails are the REAL ones (no second apply rule) ------------
    def _apply_artifact_map(self, result, maps=None) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2

        metrics_stage2._apply_artifact_map(self, result, maps)

    def _apply_fidelity_map(self, result) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2

        metrics_stage2._apply_fidelity_map(self, result)

    def _apply_camera_map(self, result) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2

        metrics_stage2._apply_camera_map(self, result)

    def _refresh_changed_metrics(self, changed, tag) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2

        metrics_stage2._refresh_changed_metrics(self, changed, tag)

    # -- settle seams -------------------------------------------------------
    def _is_current_folder_gen(self, gen) -> bool:
        return True

    def _trim_proxy_cache(self) -> int:
        return 0

    def _mark_local_pass(self, items, phase) -> None:
        triage_run._mark_local_pass(self, items, phase)

    def refresh_metric_profile(self):
        return None

    def _hydrate_ai_cache(self, items) -> int:
        return 0

    def _run_profile_select_on_settle(self) -> None:
        return None

    def _apply_fusion_ranks(self, series, *, mode=None) -> None:
        """Ranks are asserted through the pure ``rank_series`` in this file."""
        return None

    def run_tie_break_if_needed(self, series) -> None:
        return None


@pytest.fixture
def isolated_disk_caches(tmp_path, monkeypatch):
    """Point the OTHER disk caches at tmp: the reset clears them too."""
    from tabs.image_gallery.services import ai_cache, profile_cache

    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: ai_dir)
    pins = tmp_path / "pins"
    pins.mkdir()
    monkeypatch.setattr(profile_cache, "_default_cache", profile_cache.ProfileCache(pins))
    return ai_dir, pins


def _open(owner) -> None:
    """The reopen path: the triage tail decides what Stage-2 must still compute."""
    proxy_pass._apply_triage_result(owner, [], None, owner.state.mode)


def _entry_files() -> list:
    """Persisted entries (the version marker is not one)."""
    return [
        path
        for path in sorted(Path(metrics_cache.metrics_cache_dir()).glob("*.json"))
        if path.name != "version.json"
    ]


# -- the gate ---------------------------------------------------------------


def test_a_known_folder_reopen_runs_no_detector(gallery, detectors) -> None:
    """Cold: one detector pass per image. Reopen: ZERO, and zero decodes."""
    cold = _Owner(_items(gallery))
    _open(cold)

    assert detectors["detector"] == len(gallery), "the cold run must measure each image"
    assert cold.proxy_batches == [len(gallery)]
    assert _entry_files(), "the delivery must persist what it measured"
    assert all(quality.severities(item) for item in cold.state.items)

    warm = _Owner(_items(gallery))
    detectors["detector"] = 0
    detectors["decode"] = 0
    _open(warm)

    assert detectors["detector"] == 0, "a known folder must not re-run the local detector"
    assert detectors["decode"] == 0, "a known folder must not re-decode the image"
    assert warm.proxy_batches == [], "no Stage-2 batch may start for a known folder"
    # The badge must not stay stuck: the pass never started, so the tail settles
    # immediately (same contract as the "analyses unchanged" branch).
    assert all(activity_of(item)[0] == ActivityPhase.DONE.value for item in warm.state.items)

    # A second tail in the same run (regroup / tab return) stays free as well.
    detectors["detector"] = 0
    _open(warm)
    assert detectors["detector"] == 0


def test_the_reopen_shows_the_same_dots_ranks_and_records(gallery, detectors) -> None:
    cold = _Owner(_items(gallery))
    _open(cold)
    warm = _Owner(_items(gallery))
    _open(warm)

    cold_dots = [quality.severities(item) for item in cold.state.items]
    warm_dots = [quality.severities(item) for item in warm.state.items]
    assert cold_dots == warm_dots, "the card dots must match a cold run"
    assert all(cold_dots), "a cold run must actually produce dots (else parity is vacuous)"

    cold_ranks = rank_series(cold.state.items, mode=Mode.FIDELITY)
    warm_ranks = rank_series(warm.state.items, mode=Mode.FIDELITY)
    assert cold_ranks, "the fusion must derive ranks (else parity is vacuous)"
    assert cold_ranks == warm_ranks, "the fused ranks must match a cold run"

    cold_records = [tuple(rec.axis for rec in item.analysis_records) for item in cold.state.items]
    warm_records = [tuple(rec.axis for rec in item.analysis_records) for item in warm.state.items]
    assert all(cold_records)
    assert cold_records == warm_records, "the read path must see the same engine records"
    assert [dict(item.metrics) for item in cold.state.items] == [
        dict(item.metrics) for item in warm.state.items
    ]


def test_a_fidelity_entry_is_not_served_in_camera_mode(gallery, detectors) -> None:
    """``mode`` is part of the identity: the camera lane is a different pass."""
    _open(_Owner(_items(gallery), mode=Mode.FIDELITY))

    camera = _Owner(_items(gallery), mode=Mode.CAMERA)
    detectors["detector"] = 0
    _open(camera)

    assert detectors["detector"] == len(gallery), "another mode must re-measure"


def test_a_partially_known_pool_only_measures_the_misses(gallery, detectors) -> None:
    """One known + one new image: the pass runs for the new one alone."""
    cold = _Owner(_items(gallery[:1]))
    _open(cold)
    assert detectors["detector"] == 1

    mixed = _Owner(_items(gallery))
    detectors["detector"] = 0
    _open(mixed)

    assert detectors["detector"] == 1, "only the unknown image may be measured"
    assert mixed.proxy_batches == [1]


# -- fail-closed identity / corruption --------------------------------------


def test_a_corrupt_entry_is_a_miss_and_the_numbers_are_recomputed(gallery, detectors) -> None:
    cold = _Owner(_items(gallery))
    _open(cold)
    assert len(_entry_files()) == len(gallery), "a cold run must leave an entry per image"
    cold_dots = [quality.severities(item) for item in cold.state.items]
    for entry in _entry_files():
        entry.write_text("{ this is not json", encoding="utf-8")

    warm = _Owner(_items(gallery))
    detectors["detector"] = 0
    _open(warm)

    assert detectors["detector"] == len(gallery), "a corrupt entry must not be served"
    assert [quality.severities(item) for item in warm.state.items] == cold_dots


def test_a_hand_edited_severity_is_a_miss_not_a_clean_card(gallery, detectors) -> None:
    """The severity whitelist: an unknown value must not degrade to ``clean``."""
    cold = _Owner(_items(gallery))
    _open(cold)
    cold_dots = [quality.severities(item) for item in cold.state.items]
    tampered = False
    for entry in _entry_files():
        data = json.loads(entry.read_text(encoding="utf-8"))
        artifacts = data["entry"].get("artifacts") or {}
        if artifacts:
            name = sorted(artifacts)[0]
            artifacts[name] = "definitely-not-a-severity"
            tampered = True
            entry.write_text(json.dumps(data), encoding="utf-8")
    assert tampered, "the fixture must produce at least one artifact severity"

    warm = _Owner(_items(gallery))
    detectors["detector"] = 0
    _open(warm)

    assert detectors["detector"] >= 1, "a tampered entry must be a miss"
    assert [quality.severities(item) for item in warm.state.items] == cold_dots


def test_an_edited_image_is_a_miss(gallery, detectors) -> None:
    """Identity mismatch (mtime/size) never outranks the fresh file."""
    cold = _Owner(_items(gallery))
    _open(cold)
    assert len(_entry_files()) == len(gallery)

    _write_png(Path(gallery[0]), 7)  # different bytes → different size/mtime
    warm = _Owner(_items(gallery))
    detectors["detector"] = 0
    _open(warm)

    assert detectors["detector"] == 1, "only the edited image may be re-measured"
    assert warm.proxy_batches == [1]


def test_a_pipeline_version_bump_invalidates_once_and_says_so(
    gallery, detectors, monkeypatch, caplog
) -> None:
    """A detector-math bump drops every entry once, loudly, then re-measures."""
    cold = _Owner(_items(gallery))
    _open(cold)
    assert len(_entry_files()) == len(gallery)

    monkeypatch.setattr(metrics_cache, "pipeline_version", lambda: "bumped@99")
    monkeypatch.setattr(metrics_cache, "_version_checked", False, raising=False)
    warm_items = _items(gallery)
    warm = _Owner(warm_items)
    detectors["detector"] = 0
    with caplog.at_level("WARNING", logger="ImproveImgSLI"):
        _open(warm)

    assert detectors["detector"] == len(gallery), "a version bump must invalidate every entry"
    assert any(
        "local-metrics cache invalidated" in record.getMessage() for record in caplog.records
    ), "the invalidation must be announced"


def test_the_reset_drops_the_persisted_local_result(
    gallery, detectors, isolated_disk_caches
) -> None:
    """ "Reset metrics cache" must not hydrate the numbers back on the next pass."""
    from tabs.image_gallery.use_cases import cache_reset

    cold = _Owner(_items(gallery))
    _open(cold)
    assert len(_entry_files()) == len(gallery)

    cache_reset.clear_metrics_caches(cold)
    assert _entry_files() == [], "the reset must drop the persisted local result"

    reopen = _Owner(_items(gallery))
    detectors["detector"] = 0
    _open(reopen)
    assert detectors["detector"] == len(gallery), "a reset folder must recompute"


# -- the delivery seam ------------------------------------------------------


def test_the_delivery_persists_what_the_pass_produced(gallery) -> None:
    """``_on_proxy_batch_ready`` writes the entry the worker returned."""
    from engine.analysis.contracts import AxisValue

    item = _items(gallery[:1])[0]
    owner = _Owner([item])
    record = AxisValue(axis="sharpness", value=71.0, producer="local", raw=120.0)
    proxy_pass._on_proxy_batch_ready(
        owner,
        {
            str(item.path): {
                "artifacts": {"banding": "flagged"},
                "artifact_maps": {"banding": [[0.0, 1.0]]},
                "fidelity": {"ssim": 0.9, "hf_ratio": 0.1, "delta_e": 2.0, "upscale_factor": 1},
                "camera": {"sharpness": 71.0},
                "analysis": (record,),
            }
        },
        owner._folder_gen,
        {"artifacts", "fidelity", "camera"},
        source=None,
        include_camera=False,
        full_res_artifacts=True,
    )

    identity = local_metrics.identity_for(
        item, None, Mode.FIDELITY, full_res_artifacts=True
    )
    stored = metrics_cache.load_local_metrics(identity)
    assert stored is not None
    assert stored.entry["artifacts"] == {"banding": "flagged"}
    assert stored.entry["fidelity"]["ssim"] == 0.9
    assert stored.entry["camera"] == {"sharpness": 71.0}
    assert [rec.axis for rec in stored.analysis_records] == ["sharpness"]
    assert stored.analysis_records[0].raw == 120.0


def test_an_incomplete_run_is_not_persisted(gallery) -> None:
    """A requested lane the entry does not carry is a hole, not a clean result."""
    item = _items(gallery[:1])[0]
    owner = _Owner([item])
    proxy_pass._on_proxy_batch_ready(
        owner,
        {str(item.path): {"artifacts": {"banding": "clean"}}},
        owner._folder_gen,
        {"artifacts", "fidelity", "camera"},
        source=None,
        include_camera=False,
        full_res_artifacts=True,
    )
    assert _entry_files() == [], "an entry missing a requested lane must not be cached"

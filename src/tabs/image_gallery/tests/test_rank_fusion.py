"""R0 — deterministic rank fusion over MEASURED axes (rank-backends plan).

Falsification story (what each test would catch):

- permutation invariance: a sort key that falls back to arrival order;
- excluding-axis proof: fusing ``typicality`` (the old centroid rank) back in;
- unmeasured-last / ``None``: defaulting a missing axis to 0/100 instead of
  excluding it, or fabricating a score for an unmeasured item;
- cross-process determinism: a rank that depends on dict/hash/arrival order.

Pure-python ``SimpleNamespace`` fakes only — no Qt, no torch, no PIL.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem, GalleryState, Mode
from tabs.image_gallery.services import rank_fusion
from tabs.image_gallery.services.rank_fusion import (
    RANK_EXCLUDED_AXES,
    RANK_FUSION_VERSION,
    item_quality,
    measured_axes_for,
    rank_series,
)

TYPICALITY_KEY = "embedding_dist_to_centroid"


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


#: A: best measured (ssim+noise), but the *worst* centroid distance.
#: B: mid measured, best centroid distance.
#: C: a centroid distance only — nothing measured.
def _series() -> list[SimpleNamespace]:
    return [
        _item("a.png", ssim=0.90, noise=0.10, **{TYPICALITY_KEY: 0.90}),
        _item("b.png", ssim=0.50, noise=0.50, **{TYPICALITY_KEY: 0.01}),
        _item("c.png", **{TYPICALITY_KEY: 0.20}),
    ]


# --------------------------------------------------------------------------
# axis applicability comes from the registry, not a second list
# --------------------------------------------------------------------------


def test_measured_axes_never_include_excluded_or_non_measured():
    assert "typicality" in RANK_EXCLUDED_AXES
    for mode in ("fidelity", "camera", "batch_synthetic"):
        axes = measured_axes_for(mode)
        assert "typicality" not in axes, mode
        assert len(set(axes)) == len(axes)


def test_axis_applicability_is_mode_scoped_by_tag():
    fidelity = set(measured_axes_for("fidelity"))
    camera = set(measured_axes_for("camera"))
    batch = set(measured_axes_for(Mode.BATCH_SYNTHETIC))

    # Source-relative axes need a hub → fidelity only.
    assert {"ssim", "lpips", "dists", "color_accuracy"} <= fidelity
    assert not ({"ssim", "lpips"} & camera)
    assert not ({"ssim", "lpips"} & batch)
    # BRISQUE is the photographic (camera) no-reference axis.
    assert "brisque" in camera
    assert "brisque" not in fidelity
    assert "brisque" not in batch
    # Absolute local detectors apply to every mode.
    assert {"sharpness", "noise", "exposure"} <= (fidelity & camera & batch)


# --------------------------------------------------------------------------
# requirement: permutation invariance
# --------------------------------------------------------------------------


def test_rank_series_is_permutation_invariant():
    base = rank_series(_series(), mode="fidelity")

    rng = random.Random(20261015)
    for _ in range(8):
        items = _series()
        rng.shuffle(items)
        assert rank_series(items, mode="fidelity") == base


def test_rank_series_orders_by_quality_not_arrival_or_path():
    got = rank_series(_series(), mode="fidelity")
    # b.png is alphabetically first but a.png measures better → a is rank 1.
    assert got == {"/gallery/a.png": 1, "/gallery/b.png": 2, "/gallery/c.png": 3}


# --------------------------------------------------------------------------
# requirement: excluding-axis proof (drop typicality from every item)
# --------------------------------------------------------------------------


def test_removing_typicality_metric_changes_no_rank():
    with_typicality = _series()
    without = _series()
    for item in without:
        item.metrics.pop(TYPICALITY_KEY, None)

    assert rank_series(with_typicality, mode="fidelity") == rank_series(without, mode="fidelity")
    # Sanity: item B actually had the best centroid distance, so a fusion that
    # counted typicality would have promoted it — the exclusion is load-bearing.
    assert without[1].metrics.get(TYPICALITY_KEY) is None


# --------------------------------------------------------------------------
# requirement: unmeasured item ranks last and reports None
# --------------------------------------------------------------------------


def test_unmeasured_item_reports_none_and_ranks_last():
    items = _series()
    unmeasured = items[2]
    assert item_quality(unmeasured, mode="fidelity") is None
    ranks = rank_series(items, mode="fidelity")
    assert ranks["/gallery/c.png"] == 3
    assert all(ranks[f"/gallery/{n}.png"] < 3 for n in "ab")


def test_missing_axis_is_excluded_not_scored_zero():
    # One measured axis at 10/100; the missing second axis must not pull the
    # mean toward 0 (which would be fabricating a measurement).
    item = _item("only.png", ssim=0.10)
    assert item_quality(item, mode="fidelity") == 10.0
    assert item_quality(_item("empty.png"), mode="fidelity") is None


def test_quality_is_mean_of_all_applicable_axes():
    item = _item("m.png", ssim=0.90, noise=0.10)  # 90 and 90
    assert item_quality(item, mode="fidelity") == 90.0
    item2 = _item("m2.png", ssim=0.90, noise=0.50)  # 90 and 50
    assert item_quality(item2, mode="fidelity") == 70.0


# --------------------------------------------------------------------------
# requirement: worst-axis cap (v2) — one catastrophic axis is not averaged away
# --------------------------------------------------------------------------


def test_worst_axis_caps_the_aggregate():
    # ssim→100, noise→100, but delta_e=10 → color_accuracy 0. The uncapped mean
    # is ~66.7; the weakest axis (0) caps the aggregate to the slack.
    item = _item("capped.png", ssim=1.0, noise=0.0, delta_e=10)
    assert item_quality(item, mode="fidelity") == rank_fusion.RANK_WORST_AXIS_SLACK


def test_worst_axis_cap_can_flip_a_rank_vs_the_plain_mean():
    balanced = _item("balanced.png", ssim=0.60, noise=0.40)  # 60, 60 → mean 60
    spiky = _item("spiky.png", ssim=1.0, noise=0.0, delta_e=10)  # 100,100,0
    ranks = rank_series([balanced, spiky], mode="fidelity")
    # The uncapped mean would promote spiky (66.7 > 60); the cap demotes it.
    assert ranks["/gallery/balanced.png"] == 1
    assert ranks["/gallery/spiky.png"] == 2


# --------------------------------------------------------------------------
# requirement: determinism across runs (in-process + subprocess)
# --------------------------------------------------------------------------


def test_rank_series_deterministic_across_calls():
    assert rank_series(_series(), mode="fidelity") == rank_series(_series(), mode="fidelity")


_SUBPROCESS_SCRIPT = """
import json
from pathlib import Path
from types import SimpleNamespace
from tabs.image_gallery.services.rank_fusion import item_quality, rank_series

def it(name, **m):
    return SimpleNamespace(path=Path("/gallery/" + name), metrics=dict(m))

items = [
    it("a.png", ssim=0.90, noise=0.10, embedding_dist_to_centroid=0.90),
    it("b.png", ssim=0.50, noise=0.50, embedding_dist_to_centroid=0.01),
    it("c.png", embedding_dist_to_centroid=0.20),
]
print(json.dumps({
    "ranks": rank_series(items, mode="fidelity"),
    "quality": [item_quality(i, mode="fidelity") for i in items],
}, sort_keys=True))
"""


def test_rank_series_deterministic_across_processes():
    expected = {
        "ranks": rank_series(_series(), mode="fidelity"),
        "quality": [item_quality(i, mode="fidelity") for i in _series()],
    }
    src_root = Path(rank_fusion.__file__).resolve().parents[3]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["ranks"] == expected["ranks"]
    assert got["quality"] == expected["quality"]


# --------------------------------------------------------------------------
# model surface (R0 adds fields only; defaults preserved)
# --------------------------------------------------------------------------


def test_new_fields_have_safe_defaults():
    assert GalleryItem(Path("/gallery/x.png"), 0).rank_source is None
    assert GalleryState().rank_domain == "algorithms"
    assert GalleryState().judgment_domain == "algorithms"
    assert RANK_FUSION_VERSION == 2

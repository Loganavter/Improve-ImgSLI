"""Optional learned quality metrics (LPIPS/DISTS) — graceful absence + specs.

The backend (torch + piq) is optional: without it every entry point returns an
empty result and the fidelity report is unchanged. These tests pin that
contract and the metric-score mapping; the compute path is exercised by the
backend itself, not here.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")


def _img(color=(100, 100, 100), size=(32, 32)):
    from PIL import Image

    return Image.new("RGB", size, color)


def test_unavailable_backend_returns_empty(monkeypatch) -> None:
    from tabs.image_gallery.services import quality_models as qm

    monkeypatch.setattr(qm, "_models", False)
    assert qm.available() is False
    assert qm.pair_metrics(_img(), _img()) == {}


def test_pair_metrics_none_images(monkeypatch) -> None:
    from tabs.image_gallery.services import quality_models as qm

    monkeypatch.setattr(qm, "_models", False)
    assert qm.pair_metrics(None, None) == {}


def test_nr_metrics_unavailable_returns_empty(monkeypatch) -> None:
    from tabs.image_gallery.services import quality_models as qm

    monkeypatch.setattr(qm, "_models", False)
    assert qm.nr_metrics(_img()) == {}


def test_learned_metric_specs_map_lower_is_better() -> None:
    from tabs.image_gallery.services import metric_scores as ms

    # (id, best-value, worst-value) — BRISQUE can be negative, so its range is
    # [-20, 60], not [0, cap].
    for mid, lo, hi in (("lpips", 0.0, 0.8), ("dists", 0.0, 0.6), ("brisque", -20.0, 60.0)):
        spec = ms.spec_for(mid)
        assert spec is not None and spec.label
        assert ms.score_for(spec, lo) == 100
        assert ms.score_for(spec, hi) == 0
        assert ms.score_for(spec, lo) > ms.score_for(spec, (lo + hi) / 2) > ms.score_for(spec, hi)


def test_fidelity_without_backend_has_no_learned_keys(monkeypatch) -> None:
    from tabs.image_gallery.services import quality_models as qm

    monkeypatch.setattr(qm, "_models", False)
    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_from_images

    out = compute_fidelity_from_images(_img((100, 100, 100)), _img((110, 90, 100)))
    assert "lpips" not in out and "dists" not in out
    assert "ssim" in out  # the shallow baseline still measures

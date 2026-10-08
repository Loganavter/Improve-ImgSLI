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


def _img_from(arr):
    from PIL import Image

    return Image.fromarray(arr, "RGB")


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


def test_content_gate_photographic_vs_illustrative() -> None:
    """Cartoon/flat blocks are non-photographic; continuous tone is photo."""
    import numpy as np

    from tabs.image_gallery.services.quality_models import is_photographic

    a = np.zeros((128, 128, 3), np.uint8)
    a[:, :] = (30, 60, 180)
    a[20:108, 30:98] = (220, 180, 40)
    assert is_photographic(_img_from(a)) is False

    rng = np.random.default_rng(0)
    noise = np.clip(rng.normal(128, 40, (128, 128, 3)), 0, 255).astype(np.uint8)
    assert is_photographic(_img_from(noise)) is True


def test_nr_metrics_gated_by_content(monkeypatch) -> None:
    """BRISQUE is not produced for illustrative content (out of domain)."""
    import numpy as np

    from tabs.image_gallery.services import quality_models as qm

    monkeypatch.setattr(qm, "_models", {"brisque": lambda t, data_range: None})
    a = np.zeros((128, 128, 3), np.uint8)
    a[:, :] = (30, 60, 180)
    a[20:108, 30:98] = (220, 180, 40)
    assert qm.nr_metrics(_img_from(a)) == {}


def test_learned_metric_specs_map_lower_is_better() -> None:
    from tabs.image_gallery.services import metric_scores as ms

    # (id, best-value, worst-value) — BRISQUE can be negative, so its range is
    # [-20, 60], not [0, cap].
    for mid, lo, hi in (
        ("lpips", 0.0, 0.8),
        ("dists", 0.0, 0.6),
        ("brisque", -20.0, 60.0),
        ("clipping_delta", 0.0, 5.0),
    ):
        spec = ms.spec_for(mid)
        assert spec is not None and spec.label
        assert ms.score_for(spec, lo) == 100
        assert ms.score_for(spec, hi) == 0
        assert ms.score_for(spec, lo) > ms.score_for(spec, (lo + hi) / 2) > ms.score_for(spec, hi)


def test_artifact_mild_note_reads_as_possible() -> None:
    """SalArt-VQA ladder: clean=abstain, mild=possible, flagged=committed."""
    from tabs.image_gallery.services.metric_scores import fallback_note as fb

    assert fb("halo", 100) == "clean edges"  # abstain — no claim
    assert fb("halo", 50) == "possible halo"  # uncertain
    assert fb("halo", 15) == "strong halo"  # committed
    assert fb("banding", 50) == "possible banding"
    assert fb("chroma_fringing", 50) == "possible fringing"


def test_clipping_delta_is_source_relative() -> None:
    """Clipping is measured as a delta vs the source, not absolute."""
    import numpy as np

    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_from_images

    src = np.full((64, 64, 3), 128, np.uint8)
    item = src.copy()
    item[:32, :] = 255  # top half blown to highlight
    out = compute_fidelity_from_images(_img_from(item), _img_from(src))
    assert out["clipping_delta"] > 40  # ~half the pixels newly clipped
    same = compute_fidelity_from_images(_img_from(src), _img_from(src))
    assert abs(same["clipping_delta"]) < 1e-6


def test_fidelity_without_backend_has_no_learned_keys(monkeypatch) -> None:
    from tabs.image_gallery.services import quality_models as qm

    monkeypatch.setattr(qm, "_models", False)
    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_from_images

    out = compute_fidelity_from_images(_img((100, 100, 100)), _img((110, 90, 100)))
    assert "lpips" not in out and "dists" not in out
    assert "ssim" in out  # the shallow baseline still measures

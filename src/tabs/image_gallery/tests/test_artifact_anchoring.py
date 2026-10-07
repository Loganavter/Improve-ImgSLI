"""Source-anchoring of the absolute artifact detectors (plan-gallery-ai-quality).

The four absolute detectors (banding / halo / blocking / chroma_fringing) carry
a constant content bias — crisp cel art reads as "halo", a clean gradient can
read as "banding". A gallery compares variants of the SAME source, so the bias
is identical across variants and cancels in the delta. ``analyze_images``
anchors those four to the source when one is available.

Invariants guarded here:
- anchored self-pair (candidate is its own source) => clean, even when the
  absolute detector flags the content (the cel-art false positive);
- a candidate genuinely worse than its source still flags;
- the no-source path is unchanged (byte-for-byte the old absolute severities);
- the three source-relative detectors are never double-anchored.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402


def _gradient(step: int) -> Image.Image:
    """Horizontal ramp, optionally posterized to *step* levels (banding)."""
    x = np.linspace(0, 255, 256).astype(np.uint8)
    arr = np.tile(x, (64, 1))
    if step > 1:
        arr = ((arr // step) * step).astype(np.uint8)
    return Image.fromarray(arr, "L").convert("RGB")


def _flat(value: int = 128) -> Image.Image:
    return Image.new("RGB", (128, 128), (value, value, value))


def _checker() -> Image.Image:
    arr = np.zeros((128, 128, 3), dtype=np.uint8)
    arr[::8, :, :] = 255
    arr[:, ::8, :] = 255
    return Image.fromarray(arr, "RGB")


def _noisy() -> Image.Image:
    rng = np.random.default_rng(7)
    arr = np.clip(rng.normal(128, 30, (128, 128, 3)), 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


_IMAGES = [_flat, _checker, _noisy, lambda: _gradient(1), lambda: _gradient(16)]


@pytest.mark.parametrize("factory", _IMAGES)
def test_anchored_self_pair_is_clean(factory) -> None:
    """A content bias cannot manufacture an artifact: candidate == source ⇒ clean."""
    from tabs.image_gallery.services.artifacts import _ANCHORED, Severity, analyze_images

    img = factory()
    got = analyze_images(img, img)
    for art in _ANCHORED:
        assert got[art] == Severity.CLEAN, (factory.__name__, art, got[art])


def test_anchor_flags_worse_than_source() -> None:
    """A genuinely banded candidate vs a smooth source still flags."""
    from tabs.image_gallery.services.artifacts import (
        Artifact,
        Severity,
        analyze_images,
        detect_banding,
    )

    source = _gradient(1)  # smooth ramp — clean
    candidate = _gradient(16)  # posterized — banded
    # Sanity: the detector itself really sees the difference.
    assert detect_banding(source) == Severity.CLEAN
    assert detect_banding(candidate) in (Severity.MILD, Severity.FLAGGED)
    got = analyze_images(candidate, source)
    assert got[Artifact.BANDING] in (Severity.MILD, Severity.FLAGGED)


def test_content_bias_cancels_on_self_pair() -> None:
    """The cel-art case: absolute flag on both sides ⇒ anchored clean."""
    from tabs.image_gallery.services.artifacts import (
        Artifact,
        Severity,
        analyze_images,
        detect_banding,
    )

    banded = _gradient(16)
    assert detect_banding(banded) in (Severity.MILD, Severity.FLAGGED)  # absolute bias
    assert analyze_images(banded, banded)[Artifact.BANDING] == Severity.CLEAN


def test_no_source_path_is_absolute() -> None:
    """With no source the returned severities equal the raw detectors."""
    from tabs.image_gallery.services.artifacts import (
        Artifact,
        analyze_images,
        detect_banding,
        detect_blocking,
        detect_chroma_fringing,
        detect_halo,
        detect_invented_texture,
        detect_noise_amplification,
        detect_over_smoothing,
    )

    candidate = _gradient(16)
    expected = {
        Artifact.BANDING: detect_banding(candidate),
        Artifact.HALO: detect_halo(candidate),
        Artifact.OVER_SMOOTHING: detect_over_smoothing(candidate),
        Artifact.INVENTED_TEXTURE: detect_invented_texture(candidate),
        Artifact.BLOCKING: detect_blocking(candidate),
        Artifact.CHROMA_FRINGING: detect_chroma_fringing(candidate),
        Artifact.NOISE_AMPLIFICATION: detect_noise_amplification(candidate),
    }
    assert analyze_images(candidate, None) == expected


def test_source_relative_detectors_not_double_anchored() -> None:
    """The three source-relative detectors stay out of the anchor set."""
    from tabs.image_gallery.services.artifacts import Artifact, _ANCHORED

    assert Artifact.OVER_SMOOTHING not in _ANCHORED
    assert Artifact.INVENTED_TEXTURE not in _ANCHORED
    assert Artifact.NOISE_AMPLIFICATION not in _ANCHORED
    assert set(_ANCHORED) == {
        Artifact.BANDING,
        Artifact.HALO,
        Artifact.BLOCKING,
        Artifact.CHROMA_FRINGING,
    }


def test_anchored_severity_flows_through_quality_sot() -> None:
    """Anchored output is what the single-source-of-truth UI reads (deterministic)."""
    from types import SimpleNamespace

    from tabs.image_gallery.services.artifacts import Artifact, analyze_images
    from tabs.image_gallery.use_cases import quality

    source = _gradient(1)
    candidate = _gradient(16)
    mapping = analyze_images(candidate, source)
    item = SimpleNamespace(metrics={}, artifacts={})
    assert quality.set_artifacts(item, mapping) is True
    # Single source of truth returns the anchored severity, deterministically.
    anchored = str(mapping[Artifact.BANDING].value if hasattr(mapping[Artifact.BANDING], "value") else mapping[Artifact.BANDING])
    assert quality.severity(item, "banding") == anchored
    assert anchored in ("mild", "flagged")
    # The mode triplet reads the same anchored value (fidelity: banding/halo/blocking).
    assert quality.mode_triplet(item, "fidelity")[0] == anchored
    assert quality.severity(item, "banding") == anchored  # stable across calls

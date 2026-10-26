"""INVARIANT: "Reset metrics cache" zeroes the Jev rank pins and VLM briefs.

Both are measured decisions produced by a paid backend: a pinned Jev order and
a cached tie-break/brief are measurements, so a reset that claims to zero every
measurement must delete them instead of serving them again on the next pass.

Falsification story (red on ``int/backend-isolation``): ``clear_metrics_caches``
asks ``services.jev_cache`` and ``services.vlm_cache`` for ``clear_default_cache``
— a symbol neither module defines. The ``getattr``/``callable`` guard turns that
into a silent no-op, so both directories survive the reset untouched.

The test seeds through the modules' PUBLIC save APIs into a temporary cache
root (``conftest.counters`` redirects ``cache_kind_dir``) and then exercises the
REAL reset; ``clear_default_cache`` is not patched, so the directory is cleared
by production code or not at all.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import CompareBrief, TieBreakResult
from tabs.image_gallery.services import jev_cache, vlm_cache
from tabs.image_gallery.use_cases.cache_reset import clear_metrics_caches


class _Owner:
    """Minimal reset owner: an empty pool and the two optional hooks."""

    def __init__(self) -> None:
        self.state = SimpleNamespace(items=[])
        self.profile_clears = 0

    def clear_metric_profile(self) -> None:
        self.profile_clears += 1


def test_reset_clears_jev_and_vlm_pins(tmp_path, counters) -> None:
    cache_root = tmp_path / "cache"

    jev_cache.default_cache().put("w0-rank-pin", {"/gallery/a.png": 1})
    a, b = Path("/gallery/a.png"), Path("/gallery/b.png")
    vlm_cache.save_tie_break(
        a,
        1,
        b,
        2,
        TieBreakResult(
            winner_path=str(a),
            loser_path=str(b),
            reason="sharper",
            confidence=0.9,
            model="judge-model",
            decided_at_iso="t",
        ),
    )
    vlm_cache.save_brief(
        a,
        1,
        b,
        2,
        CompareBrief(
            pair=(str(a), str(b)),
            summary="same scene, b is cleaner",
            differences=("noise",),
            tags=("noise",),
            model="judge-model",
            created_at_iso="t",
        ),
    )

    jev_dir = cache_root / jev_cache.CACHE_DIR_NAME
    # ``vlm_cache`` has no ``CACHE_DIR_NAME`` constant; the directory name is
    # the literal its ``vlm_cache_dir()`` passes to ``cache_kind_dir``.
    vlm_dir = cache_root / "gallery_vlm_cache"
    seeded = sorted(jev_dir.glob("rank_*.json")) + sorted(vlm_dir.glob("*.json"))
    assert len(seeded) == 3, f"fixture sanity: expected 3 seeded pins, got {seeded!r}"
    assert all(path.is_file() for path in seeded)

    owner = _Owner()
    clear_metrics_caches(owner)

    assert not list(jev_dir.glob("rank_*.json")), (
        "the reset left a pinned Jev rank on disk: "
        f"{[p.name for p in jev_dir.glob('rank_*.json')]!r}"
    )
    assert not list(vlm_dir.glob("tie_*.json")), (
        "the reset left a cached VLM tie-break on disk"
    )
    assert not list(vlm_dir.glob("brief_*.json")), (
        "the reset left a cached VLM compare brief on disk"
    )
    assert not any(path.exists() for path in seeded)
    assert owner.profile_clears == 1

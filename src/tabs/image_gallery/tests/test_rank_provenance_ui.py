"""Rank provenance in the badge + stats strip (``plan-gallery-rank-backends``).

R4: every surface that shows a rank must also be able to say *which ranker*
produced it — **Algorithms** (deterministic metric fusion), **AI (Jev)** (the
opt-in non-deterministic ranking) or **Manual** (a Keep/Make-best pick). An
item with no measured rank shows no number (never ``#0``).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.services.rank_badge import (
    RANK_SOURCE_FUSION,
    RANK_SOURCE_JEV,
    RANK_SOURCE_LABEL,
    RANK_SOURCE_MANUAL,
    rank_provenance,
    rank_source_of,
    resolve_rank_badge,
    stamp_badges,
)

_I18N = Path(__file__).resolve().parents[1] / "resources" / "i18n"


def _item(**kw):
    return SimpleNamespace(**kw)


def _load(lang: str) -> dict:
    return json.loads((_I18N / lang / "image_gallery.json").read_text(encoding="utf-8"))


def test_each_rank_source_renders_matching_provenance() -> None:
    """A fake item per ``rank_source`` renders the matching provenance text."""
    expected = {
        RANK_SOURCE_FUSION: "Algorithms",
        RANK_SOURCE_JEV: "AI (Jev)",
        RANK_SOURCE_MANUAL: "Manual",
    }
    for src, label in expected.items():
        item = _item(rank=2, rank_source=src)
        assert rank_source_of(item) == src
        assert rank_provenance(item) == label
        badge = resolve_rank_badge(item)
        assert badge.source == src
        assert badge.provenance == label


def test_provenance_translated_via_callable() -> None:
    seen: list[tuple[str, str]] = []

    def tr(key: str, default: str) -> str:
        seen.append((key, default))
        return f"<{default}>"

    out = rank_provenance(_item(rank=1, rank_source="jev"), translate=tr)
    assert out == "<AI (Jev)>"
    assert seen == [("image_gallery.rank.source.ai", "AI (Jev)")]


def test_manual_beats_domain_fallback() -> None:
    assert rank_provenance(_item(rank=1, rank_source="manual"), domain="ai") == "Manual"


def test_domain_fallback_when_no_explicit_source() -> None:
    """A ranked item without ``rank_source`` falls back to the active backend."""
    assert rank_provenance(_item(rank=1), domain="ai") == "AI (Jev)"
    assert rank_provenance(_item(rank=1), domain="algorithms") == "Algorithms"


def test_unmeasured_item_has_no_number_and_no_provenance() -> None:
    """No measured axis ⇒ no number (never ``#0``) and no ranker claim."""
    item = _item(rank=None, metrics={})
    badge = resolve_rank_badge(item)
    assert badge.text == ""
    assert badge.rank is None
    assert badge.source is None
    assert badge.provenance == ""
    assert rank_source_of(item) is None
    assert rank_provenance(item) == ""


def test_zero_rank_is_never_rendered_as_a_number() -> None:
    badge = resolve_rank_badge(_item(rank=0, rank_source="fusion"))
    assert badge.text == ""
    assert badge.rank is None


def test_stamp_badges_stamps_source_and_kind() -> None:
    it = _item(path="/g/x.png", rank=2, rank_source="jev")
    stamp_badges([it], None)
    assert it.badge == "#2"
    assert it.badge_source == "jev"


def test_i18n_label_parity_en_ru() -> None:
    en = _load("en")["image_gallery"]["rank"]
    ru = _load("ru")["image_gallery"]["rank"]
    assert set(en) == set(ru)
    assert set(en["source"]) == set(ru["source"])
    for key, value in en.items():
        if isinstance(value, dict):
            for sub, val in value.items():
                assert val.strip(), (key, sub)
                assert ru[key][sub].strip(), (key, sub)
        else:
            assert value.strip(), key
            assert ru[key].strip(), key
    # The label map covers every ranker and points at a real en key.
    for src, (key, default) in RANK_SOURCE_LABEL.items():
        leaf = key.split("image_gallery.rank.source.", 1)[1]
        assert leaf in en["source"], src
        assert en["source"][leaf] == default, src


def test_gallery_i18n_has_zero_gaps() -> None:
    from devtools.check_translations import main as check_translations

    assert check_translations(["--root", str(_I18N), "--strict"]) == 0


def test_stats_strip_states_the_ranker(qtbot) -> None:
    from tabs.image_gallery.ui.stats_strip import StatsStrip

    strip = StatsStrip()
    qtbot.addWidget(strip)
    # Hidden until a ranker is known — never a fabricated one.
    assert strip.rank_source == ""
    assert strip.rank_provenance_label.text() == ""

    strip.set_rank_provenance("jev")
    assert strip.rank_source == "jev"
    assert "AI (Jev)" in strip.rank_provenance_label.text()

    strip.set_rank_provenance("manual")
    assert "Manual" in strip.rank_provenance_label.text()

    strip.set_rank_provenance(None)
    assert strip.rank_source == ""
    assert strip.rank_provenance_label.text() == ""


def test_stats_strip_domain_fallback_and_retranslate(qtbot) -> None:
    from tabs.image_gallery.ui.stats_strip import StatsStrip

    strip = StatsStrip()
    qtbot.addWidget(strip)
    strip.set_rank_provenance(None, domain="algorithms")
    assert strip.rank_source == "fusion"
    assert "Algorithms" in strip.rank_provenance_label.text()

    # A live translator swap re-applies the provenance label.
    def tr(key: str, default: str) -> str:
        if key == "image_gallery.rank.ranked_by":
            return "Via {source}"
        if key == "image_gallery.rank.source.ai":
            return "IA(Je)"
        return default

    strip.set_rank_provenance("jev")
    strip.retranslate(tr)
    assert "IA(Je)" in strip.rank_provenance_label.text()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

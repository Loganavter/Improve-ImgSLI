"""W2 — toolbar Algorithms|AI domain switch (plan-gallery-two-domain-axes).

Covers the segmented domain switch on ``GalleryToolbar`` (defaults, exclusive
helper, objectNames, emission) plus the domain gate that keeps the algorithms
view from ordering by the AI quality score.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.models import AiAnalysisResult, GalleryItem
from tabs.image_gallery.ui.toolbar import GalleryToolbar
from tabs.image_gallery.widget import ImageGalleryWidget


@pytest.fixture
def toolbar(qtbot):
    widget = GalleryToolbar()
    qtbot.addWidget(widget)
    return widget


def test_domain_switch_defaults_to_algorithms(toolbar: GalleryToolbar) -> None:
    assert toolbar.judgment_domain == "algorithms"
    assert toolbar.domain_switch.isChecked() is True
    assert toolbar.domain_switch_ai.isChecked() is False


def test_domain_switch_widgets_exist_by_objectname(toolbar: GalleryToolbar) -> None:
    assert toolbar.findChild(object, "gallery_toolbar_domain_switch_container") is not None
    alg = toolbar.findChild(object, "gallery_toolbar_domain_switch")
    ai = toolbar.findChild(object, "gallery_toolbar_domain_switch_ai")
    assert alg is toolbar.domain_switch
    assert ai is toolbar.domain_switch_ai


def test_domain_switch_is_icon_only(toolbar: GalleryToolbar) -> None:
    """Segments are icon-only; the localized label is a tooltip, never inline.

    Regression: the i18n language-switch refresh called ``setText`` on these
    icon-only buttons, so «Алгоритмы»/«ИИ» appeared next to the icons and
    clipped in the 34px toolbar row.
    """
    assert getattr(toolbar.domain_switch, "_text", "") == ""
    assert getattr(toolbar.domain_switch_ai, "_text", "") == ""
    assert toolbar.domain_switch.toolTip()
    assert toolbar.domain_switch_ai.toolTip()


def test_set_judgment_domain_emits_only_on_change(toolbar: GalleryToolbar) -> None:
    got: list[str] = []
    toolbar.domainChanged.connect(got.append)
    toolbar.set_judgment_domain("ai")
    assert got == ["ai"]
    assert toolbar.judgment_domain == "ai"
    assert toolbar.domain_switch_ai.isChecked() is True
    assert toolbar.domain_switch.isChecked() is False
    # Same domain again — no emit (exclusive helper reverts the toggle flip).
    toolbar.set_judgment_domain("ai")
    assert got == ["ai"]
    toolbar.set_judgment_domain("algorithms")
    assert got == ["ai", "algorithms"]


def test_domain_switch_normalizes_unknown_domain(toolbar: GalleryToolbar) -> None:
    toolbar.set_judgment_domain("bogus")
    assert toolbar.judgment_domain == "algorithms"


def test_sort_options_for_domain_gates_ai_quality(toolbar: GalleryToolbar) -> None:
    assert "Sort: AI quality" not in toolbar._sort_options_for_domain()
    toolbar.set_judgment_domain("ai")
    assert "Sort: AI quality" in toolbar._sort_options_for_domain()


def test_sort_ai_quality_row_disabled_under_algorithms(qtbot) -> None:
    """The AI-quality row is listed but not selectable in the algorithms domain."""
    toolbar = GalleryToolbar()
    qtbot.addWidget(toolbar)
    toolbar.show()
    qtbot.waitExposed(toolbar)
    ai_idx = toolbar._sort_items.index("Sort: AI quality")
    name_idx = toolbar._sort_items.index("Sort: Name")

    toolbar._on_sort_clicked()
    flyout = toolbar._sort_flyout
    assert flyout is not None
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    assert flyout.row_widget(ai_idx).isEnabled() is False
    assert flyout.row_widget(name_idx).isEnabled() is True

    # Close, switch to the AI domain, reopen: the option becomes selectable.
    toolbar._on_sort_clicked()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)
    toolbar.set_judgment_domain("ai")
    toolbar._on_sort_clicked()
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    assert flyout.row_widget(ai_idx).isEnabled() is True


# --------------------------------------------------------------------------
# widget-side domain gate on sort
# --------------------------------------------------------------------------


def _scored(name: str, mean: int, *, rank: int | None = None) -> GalleryItem:
    return GalleryItem(
        path=Path(f"/g/{name}"),
        mtime_ns=0,
        rank=rank,
        analysis=AiAnalysisResult(
            description="d",
            tags=(),
            model="m",
            analyzed_at_iso="t",
            sharpness=mean,
            noise=mean,
            exposure=mean,
            composition=mean,
        ),
    )


def _sort_self(*, items, domain):
    calls: dict = {"rebuild": []}
    return SimpleNamespace(
        _items=list(items),
        _series=[],
        _mode="fidelity",
        _source_path=None,
        _judgment_domain=domain,
        # Unbound-method harness: `self` lookups resolve on the fake.
        _sort_keyfunc=ImageGalleryWidget._sort_keyfunc,
        set_triage=lambda *_a: None,
        rebuild_grid=lambda it: calls["rebuild"].append(list(it)),
    ), calls


def test_sort_under_algorithms_does_not_order_by_ai_quality(qapp) -> None:
    # AI quality says hi>lo; rank says lo(1)>hi(9). Algorithms domain must
    # follow rank, never the AI score.
    hi = _scored("hi.png", 90, rank=9)
    lo = _scored("lo.png", 40, rank=1)
    fake, calls = _sort_self(items=[hi, lo], domain="algorithms")

    ImageGalleryWidget._on_sort_changed(fake, "Sort: AI quality")

    assert len(calls["rebuild"]) == 1
    assert [it.path.name for it in calls["rebuild"][0]] == ["lo.png", "hi.png"]


def test_sort_under_ai_orders_by_ai_quality(qapp) -> None:
    hi = _scored("hi.png", 90, rank=9)
    lo = _scored("lo.png", 40, rank=1)
    fake, calls = _sort_self(items=[hi, lo], domain="ai")

    ImageGalleryWidget._on_sort_changed(fake, "Sort: AI quality")

    assert len(calls["rebuild"]) == 1
    assert [it.path.name for it in calls["rebuild"][0]] == ["hi.png", "lo.png"]


def test_on_domain_changed_normalizes_and_mirrors(qapp) -> None:
    from tabs.image_gallery.models import GalleryState

    state = GalleryState()
    fake = SimpleNamespace(_controller=SimpleNamespace(state=state))
    fake._judgment_domain = "algorithms"

    ImageGalleryWidget._on_domain_changed(fake, "ai")
    assert fake._judgment_domain == "ai"
    assert state.judgment_domain == "ai"

    ImageGalleryWidget._on_domain_changed(fake, "bogus")
    assert fake._judgment_domain == "algorithms"
    assert state.judgment_domain == "algorithms"


def test_on_domain_changed_calls_controller_activate(qapp) -> None:
    calls: list[str] = []
    fake = SimpleNamespace(
        _controller=SimpleNamespace(activate_judgment_domain=lambda d: calls.append(d))
    )
    fake._judgment_domain = "algorithms"
    ImageGalleryWidget._on_domain_changed(fake, "ai")
    assert calls == ["ai"]


def test_run_ai_for_visible_only_visible_unanalyzed(qapp) -> None:
    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.models import AnalysisStatus

    vis = GalleryItem(path=Path("/g/vis.png"), mtime_ns=1)
    off = GalleryItem(path=Path("/g/off.png"), mtime_ns=1)
    done = GalleryItem(
        path=Path("/g/done.png"), mtime_ns=1, analysis_status=AnalysisStatus.DONE
    )
    analyzed: list[str] = []
    fake = SimpleNamespace(
        widget=SimpleNamespace(visible_paths=lambda: [Path("/g/vis.png"), Path("/g/done.png")]),
        state=SimpleNamespace(items=[vis, off, done]),
        _judgment_domain="ai",
        analyze=lambda ctx: analyzed.extend(p.name for p in ctx.targets),
        _AI_VISIBLE_CAP=12,
    )
    GalleryController._run_ai_for_visible(fake)
    assert analyzed == ["vis.png"]

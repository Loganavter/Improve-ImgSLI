"""Toolbar switch persistence (view grid/list + Algorithms|AI domain)."""

from __future__ import annotations

from types import SimpleNamespace

from core.state_management.gallery_actions import GalleryViewPrefsSet
from tabs.image_gallery.state.models import fresh_gallery_slot_state
from tabs.image_gallery.state.reducer import GallerySlotReducer
from tabs.image_gallery.widget import ImageGalleryWidget


def test_reducer_applies_view_prefs_and_dedupes_noop():
    st = fresh_gallery_slot_state()
    assert st.view_list is False and st.judgment_domain == "algorithms"

    st2 = GallerySlotReducer.reduce(
        st, GalleryViewPrefsSet(view_list=True, judgment_domain="ai")
    )
    assert st2.view_list is True
    assert st2.judgment_domain == "ai"

    st3 = GallerySlotReducer.reduce(
        st2, GalleryViewPrefsSet(view_list=True, judgment_domain="ai")
    )
    assert st3 is st2  # identical state → dispatcher no-op


def test_apply_view_prefs_sets_domain_quietly_no_ai_run():
    calls: list = []
    state = SimpleNamespace(judgment_domain="algorithms")
    fake = SimpleNamespace(
        _judgment_domain="algorithms",
        _view_mode=False,
        toolbar=SimpleNamespace(
            set_view_list=lambda v: calls.append(("view", v)),
            blockSignals=lambda b: calls.append(("block", b)),
            set_judgment_domain=lambda d: calls.append(("domain", d)),
        ),
        _controller=SimpleNamespace(
            state=state,
            activate_judgment_domain=lambda d: calls.append(("activate", d)),
        ),
    )
    ImageGalleryWidget.apply_view_prefs(fake, view_list=True, judgment_domain="ai")

    assert ("view", True) in calls
    assert ("domain", "ai") in calls  # switch position applied
    assert not any(c[0] == "activate" for c in calls)  # quiet: no lazy AI run
    assert fake._judgment_domain == "ai"
    assert state.judgment_domain == "ai"


class _WidgetFake:
    """Namespace double that binds the unbound widget methods under test."""

    _persist_view_prefs = ImageGalleryWidget._persist_view_prefs

    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_view_toggle_persists_prefs():
    recorded: dict = {}
    fake = _WidgetFake(
        _view_mode=False,
        _judgment_domain="ai",
        _grid_view=SimpleNamespace(set_view_mode=lambda m: None),
        _controller=SimpleNamespace(set_view_prefs=lambda **kw: recorded.update(kw)),
    )
    ImageGalleryWidget._on_view_toggled(fake, True)
    assert recorded == {"view_list": True, "judgment_domain": "ai"}


def test_domain_change_persists_prefs():
    recorded: dict = {}
    fake = _WidgetFake(
        _judgment_domain="algorithms",
        _controller=SimpleNamespace(
            activate_judgment_domain=lambda d: None,
            set_view_prefs=lambda **kw: recorded.update(kw),
        ),
    )
    ImageGalleryWidget._on_domain_changed(fake, "ai")
    assert recorded == {"view_list": False, "judgment_domain": "ai"}

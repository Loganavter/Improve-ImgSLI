"""B3: IC slot duplicate gate routes through one has-content predicate.

``_slot_has_duplicatable`` (pixels ∨ path) owns the nothing-to-duplicate
check; ``_begin_duplicate`` calls it instead of re-composing the
``image is None and not path`` literal. Carry gates stay path-only (the
carry API takes paths) and are pinned unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace


def _provider(*, image1_path: str = ""):
    from tabs.image_compare.ui.context_menu import ImageCompareContextMenuProvider

    doc = SimpleNamespace(
        image1_path=image1_path, image2_path="", image_list1=[], image_list2=[]
    )
    store = SimpleNamespace(get_session_state_slot=lambda name: doc)
    return ImageCompareContextMenuProvider(canvas=None, store=store)


def test_duplicate_gate_table():
    provider = _provider(image1_path="")
    assert provider._slot_has_duplicatable(1) is False

    provider = _provider(image1_path="/x/a.png")
    assert provider._slot_has_duplicatable(1) is True

    # Pixels without a path still count (duplicates via image data).
    provider = _provider(image1_path="")
    provider._peek_image = lambda slot: object()
    assert provider._slot_has_duplicatable(1) is True


def test_begin_duplicate_nothing_to_do_is_silent():
    """Imageless + pathless slot → silent no-op (no raise, no overlay)."""
    provider = _provider(image1_path="")
    assert provider._begin_duplicate(1) is None


def test_carry_gates_stay_path_only():
    """Carry needs a path (pixels alone are not carryable) — unchanged."""
    provider = _provider(image1_path="")
    assert provider._begin_carry_slot(1) is None
    assert provider._begin_carry_list_item(1, 0) is None

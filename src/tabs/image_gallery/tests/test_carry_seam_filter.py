"""B3: gallery carry filters through the seam ``is_loadable_image_path``.

The card ``Move``/``Compare`` entries funnel through ``carry_selected``
(card files themselves are B5-excluded and untouched) — so the single
``is_file``-only filter here is the one gate. An existing non-image file
must never be carried into workspace tabs.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _owner(selected, order=None):
    st = SimpleNamespace(selected_paths=set(selected))
    if order is not None:
        st.selected_order = list(order)
    return SimpleNamespace(state=st)


def test_carry_rejects_existing_non_image(tmp_path: Path) -> None:
    """Existing ``.txt`` selection → False, service never touched."""
    from tabs.image_gallery.use_cases import carry as _carry

    txt = tmp_path / "note.txt"
    txt.write_text("nope")
    owner = _owner({txt})
    assert _carry.carry_selected(owner) is False


def test_carry_dispatches_only_loadable(tmp_path: Path, monkeypatch) -> None:
    """Mixed selection → only the loadable image reaches the service."""
    from tabs.image_gallery.use_cases import carry as _carry

    real = tmp_path / "a.png"
    real.write_bytes(b"\x89PNG\r\n\x1a\n")
    txt = tmp_path / "b.txt"
    txt.write_text("nope")
    ghost = tmp_path / "ghost.png"
    owner = _owner({real, txt, ghost})

    seen: list = []
    monkeypatch.setattr(
        _carry, "_dispatch_via_image_carry", lambda paths, pixmap=None: seen.append(list(paths)) or True
    )
    assert _carry.carry_selected(owner) is True
    assert seen == [[real]]

"""Card click routing: plain click opens quick look, Ctrl+click selects.

Regression: single click used to toggle selection like Ctrl+click, so there
was no way to open a file without selecting it first.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.widget import ImageGalleryWidget


def _stub_self(monkeypatch, calls: dict):
    import tabs.image_gallery.use_cases.selection as selection_mod

    monkeypatch.setattr(
        selection_mod,
        "toggle_card",
        lambda owner, path, additive=False: calls.setdefault("toggle", []).append(
            (owner, path, additive)
        ),
    )
    return SimpleNamespace(
        _owner_for_triage=lambda: calls.setdefault("owner", object()),
        show_quick_look=lambda path: calls.setdefault("open", []).append(path),
        analyze_requested=SimpleNamespace(emit=lambda path: calls.setdefault("emit", []).append(path)),
    )


def test_plain_click_opens_quick_look_not_selection(monkeypatch) -> None:
    """Single click routes to show_quick_look; toggle_card stays silent."""
    calls: dict = {}
    self = _stub_self(monkeypatch, calls)
    ImageGalleryWidget._on_card_toggle(self, Path("/gallery/a.png"), additive=False)
    assert calls.get("open") == [Path("/gallery/a.png")]
    assert "toggle" not in calls


def test_ctrl_click_toggles_selection_not_open(monkeypatch) -> None:
    """Ctrl+click routes to selection.toggle_card with additive=True."""
    calls: dict = {}
    self = _stub_self(monkeypatch, calls)
    ImageGalleryWidget._on_card_toggle(self, Path("/gallery/b.png"), additive=True)
    assert "open" not in calls
    assert len(calls.get("toggle", [])) == 1
    owner, path, additive = calls["toggle"][0]
    assert path == Path("/gallery/b.png")
    assert additive is True

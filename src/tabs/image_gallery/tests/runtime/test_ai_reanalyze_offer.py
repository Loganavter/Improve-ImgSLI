"""Re-analyze offer after an AI-settings change (scope choice + action path).

RED BEFORE: ``use_cases/ai_analysis`` had no ``offer_reanalysis`` /
``reanalyze_targets`` / scope constants at all (``AttributeError`` on the parent
commit) — switching the provider left every existing scorecard pointing at a
model the new provider may not serve, with no offer to redo the analysis.

The offer is pinned at two levels:

* the decision + target resolution (identity changed? analyses exist? which
  cards per scope?) runs on a fake owner with an injected scope answer and an
  injected re-analyze callable — no app, no network, no real modal;
* the modal itself is built through the shared ``AppMessageDialog`` and must
  expose exactly the three scopes plus an explicit "Not now" (a window close is
  never read as "re-analyze everything").
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.use_cases import ai_analysis


def _identity(model: str = "vendor/model-a", effort: str = "auto") -> dict:
    return {
        "model": model,
        "base_url": "https://openrouter.ai/api/v1",
        "mode": "camera",
        "profile": "sharpness,clipping",
        "reasoning_effort": effort,
        "prompt_schema_version": 1,
    }


class _Item:
    def __init__(self, path: Path, analysis=None) -> None:
        self.path = path
        self.analysis = analysis
        self.mtime_ns = 0


class _Owner:
    """Fake GalleryController: state + widget + the action-context inputs."""

    def __init__(self, items, *, visible=(), selected=(), domain="ai") -> None:
        self.state = SimpleNamespace(
            items=list(items),
            selected_paths=set(selected),
            selected_order=[],
            mode="camera",
        )
        self.widget = SimpleNamespace(visible_paths=lambda: list(visible))
        self._judgment_domain = domain
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(reasoning_effort="auto")
        )
        self.ran: list[tuple[Path, ...]] = []

    def _tr(self, key: str, default: str) -> str:
        return default

    def reanalyze(self, ctx) -> None:  # the real action entry point
        self.ran.append(tuple(ctx.targets))


def _pool():
    a, b, c, d = (
        _Item(Path("/img/a.png"), analysis={"score": 1}),
        _Item(Path("/img/b.png"), analysis={"score": 2}),
        _Item(Path("/img/c.png"), analysis={"score": 3}),
        _Item(Path("/img/d.png"), analysis=None),
    )
    return a, b, c, d


def _failing_scope(*_args, **_kwargs):
    raise AssertionError("the scope dialog must not open")


def test_unchanged_identity_never_opens_the_modal():
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path])

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity(),
        show_scope=_failing_scope,
    )

    assert result is None
    assert owner.ran == []


def test_changed_identity_without_analyses_never_opens_the_modal():
    d = _Item(Path("/img/d.png"), analysis=None)
    owner = _Owner([d], visible=[d.path])

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity("vendor/model-b"),
        show_scope=_failing_scope,
    )

    assert result is None
    assert owner.ran == []


def test_algorithms_domain_is_not_offered():
    """An AI scorecard redo in the algorithms domain would silently re-measure."""
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path], domain="algorithms")

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity("vendor/model-b"),
        show_scope=_failing_scope,
    )

    assert result is None
    assert owner.ran == []


def test_not_now_does_not_reanalyze():
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path, b.path], selected=[a.path])

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity("vendor/model-b"),
        show_scope=lambda owner, parent=None: "",
    )

    assert result is None
    assert owner.ran == []


def test_visible_scope_reruns_only_the_analyzed_visible_cards():
    a, b, c, d = _pool()
    # ``d`` is visible but has no analysis: it is not a re-analysis target.
    owner = _Owner([a, b, c, d], visible=[a.path, b.path, d.path])

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity("vendor/model-b"),
        show_scope=lambda owner, parent=None: "visible",
    )

    assert result == {"scope": "visible", "targets": (a.path, b.path)}
    assert owner.ran == [(a.path, b.path)]


def test_selection_scope_reruns_the_selection():
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path], selected=[b.path, c.path])

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(effort="auto"),
        new_identity=_identity(effort="high"),
        show_scope=lambda owner, parent=None: "selection",
    )

    assert result == {"scope": "selection", "targets": (b.path, c.path)}
    assert owner.ran == [(b.path, c.path)]


def test_all_scope_reruns_every_analyzed_card():
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path], selected=[a.path])

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity("vendor/model-b"),
        show_scope=lambda owner, parent=None: "all",
    )

    assert result == {"scope": "all", "targets": (a.path, b.path, c.path)}
    assert owner.ran == [(a.path, b.path, c.path)]


def test_empty_scope_resolution_runs_nothing():
    """Visible viewport empty (not laid out yet) -> no widening to the pool."""
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[])

    result = ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity("vendor/model-b"),
        show_scope=lambda owner, parent=None: "visible",
    )

    assert result == {"scope": "visible", "targets": ()}
    assert owner.ran == []


def test_injected_reanalyze_callable_receives_the_action_context():
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path, b.path])
    seen = []

    ai_analysis.offer_reanalysis(
        owner,
        old_identity=_identity(),
        new_identity=_identity("vendor/model-b"),
        show_scope=lambda owner, parent=None: "visible",
        reanalyze_fn=lambda ow, ctx: seen.append((ow, ctx.backend, tuple(ctx.targets))),
    )

    assert seen == [(owner, "ai", (a.path, b.path))]
    assert owner.ran == []


# -- the modal itself ----------------------------------------------------------


def _button_label(button) -> str:
    """The toolkit ``Button`` store its caption in ``_text`` (no ``text()``)."""
    text = getattr(button, "text", None)
    if callable(text):
        return str(text())
    return str(getattr(button, "_text", "") or "")


def _patched_modal(monkeypatch, *, press: str):
    """Replace ``exec`` with an immediate scripted dismissal; record labels."""
    from shared_toolkit.ui.message_dialog import AppMessageDialog
    from sli_ui_toolkit.widgets import Button

    recorded: dict = {}

    def _fake_exec(self) -> int:
        actions = self._ok_button.parentWidget()
        recorded["labels"] = [
            _button_label(b) for b in actions.findChildren(Button)
        ]
        recorded["title"] = self.windowTitle()
        pressed = getattr(self, press)
        pressed.clicked.emit()
        if press in ("_ok_button", "_dont_ask_button"):
            self.accept()
        else:
            self.reject()
        return 0

    monkeypatch.setattr(AppMessageDialog, "exec", _fake_exec)
    return recorded


def test_modal_offers_three_scopes_and_an_explicit_not_now(qapp, monkeypatch):
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path])
    recorded = _patched_modal(monkeypatch, press="_cancel_button")

    ai_analysis._ask_reanalyze_scope(owner)

    assert "Visible images" in recorded["labels"]
    assert "Selected images" in recorded["labels"]
    assert "All analyzed images" in recorded["labels"]
    assert "Not now" in recorded["labels"]
    assert recorded["title"] == "AI settings changed"


def test_modal_primary_action_is_the_visible_scope(qapp, monkeypatch):
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path])
    _patched_modal(monkeypatch, press="_ok_button")

    assert ai_analysis._ask_reanalyze_scope(owner) == "visible"


def test_modal_dont_ask_button_is_the_selection_scope(qapp, monkeypatch):
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path])
    _patched_modal(monkeypatch, press="_dont_ask_button")

    assert ai_analysis._ask_reanalyze_scope(owner) == "selection"


def test_modal_cancel_button_is_the_all_scope(qapp, monkeypatch):
    a, b, c, d = _pool()
    owner = _Owner([a, b, c, d], visible=[a.path])
    _patched_modal(monkeypatch, press="_cancel_button")

    assert ai_analysis._ask_reanalyze_scope(owner) == "all"

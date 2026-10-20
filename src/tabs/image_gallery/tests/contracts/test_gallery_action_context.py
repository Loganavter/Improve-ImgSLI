"""ENFORCEMENT: every gallery action carries ONE explicit ``ActionContext``.

Owner directive (2026-10-20): "If the user picked the AI backend or the
algorithmic one, everything downstream — every analyzer, group action and the
rest — must receive that parameter. Fallbacks in both places can only get in
the way. On mass processing: it must never go around; there must be exactly one
way to process, and the actions themselves should not even be able to imagine
how mass differs from point processing."

This module makes the regressions this task removes impossible-ish:

* reflective — every gallery action reachable from the host registry is a
  handler taking an ``ActionContext`` (walk the registry, inspect signatures);
* lint — no action re-derives scope from set iteration
  (``next(iter(selected_paths))``) and the first-visible-card fallback
  (``_first_item_path``) is gone from the whole gallery package;
* lint — handlers do not read the settings store / judgment domain to CHOOSE
  a backend; a credential/identity read must be marked
  ``# action-context:`` with its reason;
* empty scope — no analyzer/worker starts and a named refusal comes back;
* no silent backend fallback — an invalid domain refuses and leaves the
  authority untouched; an unconfigured ``ai`` context marks the target
  ``not_configured`` and never switches to algorithms.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

GALLERY = Path(__file__).resolve().parents[2]
SRC = GALLERY
HANDLER_MODULES = (
    "use_cases/ai_analyze.py",
    "use_cases/ai_analysis.py",
    "use_cases/gallery_actions.py",
    "use_cases/registration.py",
    "ui/card/context_menu/popup.py",
    "ui/widget_parts/card_actions.py",
)


def _iter_py(root: Path):
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        yield path


def _dotted(node: ast.AST) -> str:
    """``a.b.c`` for an attribute chain, ``""`` for anything else."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _called_names(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            out.append(_dotted(node.func))
    return out


# ---------------------------------------------------------------------------
# reflective: the registry is the action inventory, so its handlers are the
# inventory of places that must take the context
# ---------------------------------------------------------------------------


def test_every_registered_gallery_action_takes_an_action_context(monkeypatch) -> None:
    from tabs.image_gallery.tab import ImageGalleryTab
    from tabs.image_gallery.use_cases import registration
    from tabs.image_gallery.use_cases.action_context import ActionContext
    from ui.actions.registry import ActionRegistry

    registry = ActionRegistry()
    tab = ImageGalleryTab()
    assert tab.create_service("contribute_actions", registry) is True

    rows = [a for a in registry.all_actions() if a.owner_tab == tab.session_type]
    assert rows, "the gallery registered no actions at all"
    assert len(rows) == len(registration.GALLERY_ACTION_HANDLERS)

    dispatched: list[str] = []
    monkeypatch.setattr(
        registration, "run_action", lambda _tab, action_id: dispatched.append(action_id)
    )

    for descriptor in rows:
        handler = registration.handler_for(descriptor.action_id)
        assert handler is not None, (
            f"{descriptor.action_id} is registered but has no ActionContext handler "
            "(the registry must not advertise an action that re-derives its own scope)"
        )
        sig = inspect.signature(handler)
        params = list(sig.parameters.values())
        assert params, f"{descriptor.action_id} handler takes no arguments"
        ctx_param = params[-1]
        assert ctx_param.name == "ctx", (
            f"{descriptor.action_id} handler's context parameter is "
            f"{ctx_param.name!r}, expected 'ctx'"
        )
        annotation = ctx_param.annotation
        assert annotation is ActionContext or annotation == "ActionContext", (
            f"{descriptor.action_id} handler's 'ctx' must be annotated "
            f"ActionContext, got {annotation!r}"
        )
        assert descriptor.run is not None
        # The descriptor must route through the ONE context entry point — a
        # stub/direct-controller closure would not append here.
        descriptor.run()
        assert dispatched and dispatched[-1] == descriptor.action_id


# ---------------------------------------------------------------------------
# lint: the two silent scope fallbacks are gone
# ---------------------------------------------------------------------------


def test_no_action_iterates_the_selection_set_for_scope() -> None:
    """``next(iter(selected_paths))`` is set order, not a scope decision."""
    offenders: list[str] = []
    for path in _iter_py(SRC):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _dotted(node.func) != "next" or not node.args:
                continue
            inner = node.args[0]
            if not isinstance(inner, ast.Call) or _dotted(inner.func) != "iter":
                continue
            if not inner.args:
                continue
            if _dotted(inner.args[0]).rsplit(".", 1)[-1] == "selected_paths":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not offenders, (
        "an action re-derived its scope from selection SET order — resolve it "
        "once through use_cases.action_context.build_context:\n" + "\n".join(offenders)
    )


def test_first_visible_card_fallback_is_deleted() -> None:
    """An action may never hit a card the user did not point at."""
    offenders: list[str] = []
    for path in _iter_py(SRC):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "_first_item_path":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
            elif isinstance(node, ast.Attribute) and node.attr == "_first_item_path":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not offenders, (
        "the first-visible-card fallback is back — an empty scope is a valid "
        "answer and callers must refuse, not substitute a card:\n"
        + "\n".join(offenders)
    )


def test_handlers_do_not_choose_a_backend() -> None:
    """No handler reads the domain/settings to decide WHICH backend runs.

    ``_judgment_domain`` may only be snapshotted by the context builder
    (``use_cases/action_context.py``). Settings reads are allowed only for
    credentials/cache identity and must say so with an
    ``# action-context:`` marker on the same line.
    """
    offenders: list[str] = []
    for rel in HANDLER_MODULES:
        path = SRC / rel
        if not path.exists():
            offenders.append(f"{rel}: handler module missing")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.Name):
                name = node.id
            if name == "_judgment_domain":
                # A STORE is the authority writer (ai_analysis._set_judgment_domain);
                # a LOAD is a handler choosing its own backend.
                if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                    continue
                offenders.append(f"{rel}:{node.lineno}: reads _judgment_domain")
            elif name == "_ai_settings_store":
                line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                if "# action-context:" not in line:
                    offenders.append(
                        f"{rel}:{node.lineno}: unmarked settings read "
                        "(add '# action-context: <reason>')"
                    )
    assert not offenders, (
        "an action handler is deciding the backend instead of receiving it:\n"
        + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# empty scope: nothing starts, a named refusal comes back
# ---------------------------------------------------------------------------


def _analysis_owner(*, domain="ai", configured=True, **extra):
    item = SimpleNamespace(
        path=Path("/gallery/a.png"),
        mtime_ns=1,
        analysis=None,
        analysis_status=None,
        analysis_error=None,
        metrics={},
    )
    settings = SimpleNamespace(
        enabled=configured,
        api_key="k" if configured else "",
        model="m",
        base_url="http://h",
        reasoning_effort="auto",
    )
    owner = SimpleNamespace(
        state=SimpleNamespace(
            mode="camera",
            metric_profile=None,
            items=[item],
            selected_paths={item.path},
            selected_order=[item.path],
            source_path=None,
        ),
        widget=SimpleNamespace(refresh_card=lambda it: None, refresh_cards=lambda its: None),
        _judgment_domain=domain,
        _ai_settings_store=SimpleNamespace(load=lambda: settings),
        _tr=lambda key, default: default,
        _folder_gen=0,
        _begin_analysis=lambda *a, **k: pytest.fail(
            "an analyzer started for an action the owner refused"
        ),
        _pool_start=lambda *a, **k: pytest.fail(
            "a worker started for an action the owner refused"
        ),
    )
    owner.__dict__.update(extra)
    return owner, item


def test_empty_scope_refuses_and_starts_nothing() -> None:
    from tabs.image_gallery.use_cases import ai_analysis, gallery_actions
    from tabs.image_gallery.use_cases.action_context import (
        REFUSAL_EMPTY_SCOPE,
        ActionContext,
        Refusal,
    )

    owner, _item = _analysis_owner()
    empty = ActionContext(targets=(), backend="ai", origin="menu")

    calls = (
        ai_analysis.analyze,
        ai_analysis.reanalyze,
        gallery_actions.group,
        gallery_actions.ungroup,
        gallery_actions.reset_metrics,
        gallery_actions.find_similar,
        gallery_actions.carry,
    )
    for fn in calls:
        refusal = fn(owner, empty)
        assert isinstance(refusal, Refusal), f"{fn.__name__} did not return a refusal"
        assert refusal.reason == REFUSAL_EMPTY_SCOPE, (
            f"{fn.__name__} refused with {refusal.reason!r}, expected "
            f"{REFUSAL_EMPTY_SCOPE!r}"
        )


def test_keyboard_entry_needs_an_explicit_focus() -> None:
    """No selection + no explicit focus = empty scope, never the first card."""
    from tabs.image_gallery.use_cases import action_scope
    from tabs.image_gallery.use_cases.action_context import build_context

    owner, _item = _analysis_owner(domain="algorithms")
    owner.state.selected_paths = set()
    owner.state.selected_order = []
    owner.focused_path = None

    assert action_scope.resolve_targets(owner) == []
    ctx = build_context(owner, origin="keyboard", focused=True)
    assert ctx.targets == ()


# ---------------------------------------------------------------------------
# no silent backend fallback
# ---------------------------------------------------------------------------


def test_invalid_domain_refuses_and_keeps_the_authority() -> None:
    from tabs.image_gallery.use_cases import ai_analysis

    owner = SimpleNamespace(
        _judgment_domain="ai",
        state=SimpleNamespace(),
        widget=SimpleNamespace(),
    )
    with pytest.raises(ValueError):
        ai_analysis._set_judgment_domain(owner, "bogus")
    assert owner._judgment_domain == "ai", "invalid input was coerced to algorithms"

    with pytest.raises(ValueError):
        ai_analysis.activate_judgment_domain(owner, "")
    assert owner._judgment_domain == "ai", "a failed switch silently changed the domain"
    assert getattr(owner.state, "judgment_domain", "ai") == "ai"


def test_unconfigured_ai_marks_not_configured_and_never_switches() -> None:
    from tabs.image_gallery.models import AnalysisStatus
    from tabs.image_gallery.use_cases import ai_analysis
    from tabs.image_gallery.use_cases.action_context import (
        REFUSAL_NOT_CONFIGURED,
        build_context,
    )

    owner, item = _analysis_owner(domain="ai", configured=False)
    ctx = build_context(owner, origin="menu", card_path=item.path)

    refusal = ai_analysis.analyze(owner, ctx)

    assert refusal is not None
    assert refusal.reason == REFUSAL_NOT_CONFIGURED
    assert item.analysis_status == AnalysisStatus.ERROR
    assert "Configure the AI API key" in str(item.analysis_error)
    assert owner._judgment_domain == "ai", "an unconfigured ai action switched backends"


def test_context_requires_a_backend_and_keeps_its_fields() -> None:
    from tabs.image_gallery.use_cases.action_context import ActionContext

    with pytest.raises(TypeError):
        ActionContext(targets=())  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        ActionContext(targets=(), backend="")
    with pytest.raises(ValueError):
        ActionContext(targets=(), backend="algorithms", origin="guess")

    ctx = ActionContext(
        targets=(Path("/a.png"),),
        backend="ai",
        profile=None,
        mode="camera",
        effort="high",
        origin="menu",
    )
    assert ctx.targets == (Path("/a.png"),)
    assert ctx.backend == "ai"
    assert ctx.mode == "camera"
    assert ctx.effort == "high"


def test_backend_travels_from_the_owner_authority() -> None:
    from tabs.image_gallery.use_cases.action_context import (
        BACKEND_AI,
        BACKEND_ALGORITHMS,
        build_context,
    )

    owner, item = _analysis_owner(domain="ai")
    ctx = build_context(owner, origin="menu", card_path=item.path)
    assert ctx.backend == BACKEND_AI
    assert ctx.targets == (item.path,)

    owner._judgment_domain = "algorithms"
    ctx = build_context(owner, origin="menu", card_path=item.path)
    assert ctx.backend == BACKEND_ALGORITHMS

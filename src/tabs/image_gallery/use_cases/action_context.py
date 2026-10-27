"""ONE explicit action context for every Image Gallery action.

Owner directive (2026-10-20): "If the user picked the AI backend or the
algorithmic one, everything downstream — every analyzer, group action and the
rest — must receive that parameter. Fallbacks in both places can only get in
the way. On mass processing: it must never go around; there must be exactly one
way to process, and the actions themselves should not even be able to imagine
how mass differs from point processing."

Before this module each action re-decided two things on its own:

* **which cards** — the context menu resolved them once, but registry/keyboard
  handlers re-read the selection (``next(iter(selected_paths))`` = set order,
  not a decision) and an empty scope silently fell back to the first visible
  card;
* **which backend** — ``_begin_analysis`` re-read ``state.mode`` / the active
  profile and the judgment-domain writers coerced anything unknown to
  ``"algorithms"``.

``ActionContext`` is the single carrier. A point action is
``targets=(path,)``: there is no other form, so no downstream code can branch
on "mass vs point" — it always loops ``ctx.targets``. ``backend`` is REQUIRED
and has no default anywhere (an invalid/missing domain is a named ``ValueError``
raised by :func:`current_backend`, never a coercion).

``build_context`` is the ONE builder. Call sites:

* context menu / registry action: ``build_context(owner, origin="menu"|"action",
  card_path=...)``;
* keyboard: ``build_context(owner, origin="keyboard", focused=True)`` — the
  focused card is an EXPLICIT input, not a fallback.

Empty targets are a valid result: callers no-op with a named
:class:`Refusal` (never substitute a card).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tabs.image_gallery.use_cases import action_scope

BACKEND_ALGORITHMS = "algorithms"
BACKEND_AI = "ai"
BACKENDS: tuple[str, ...] = (BACKEND_ALGORITHMS, BACKEND_AI)

ORIGIN_MENU = "menu"
ORIGIN_KEYBOARD = "keyboard"
ORIGIN_ACTION = "action"
ORIGINS: tuple[str, ...] = (ORIGIN_MENU, ORIGIN_KEYBOARD, ORIGIN_ACTION)

#: Named refusals. Actions return these instead of fabricating a scope or
#: switching a backend (the two silent fallbacks this task removes). The scope
#: vocabulary is owned by ``use_cases.action_scope`` (its ``Scope.refused``
#: token IS the refusal reason) — these aliases keep one spelling.
REFUSAL_EMPTY_SCOPE = action_scope.REFUSAL_EMPTY_SCOPE
REFUSAL_AMBIGUOUS_SCOPE = action_scope.REFUSAL_AMBIGUOUS_SCOPE
REFUSAL_NO_ITEMS = action_scope.REFUSAL_NO_ITEMS
REFUSAL_NOT_CONFIGURED = "not_configured"
REFUSAL_NO_HANDLER = "no_handler"
#: The AI backend has no axis set yet (0 axes would measure nothing).
REFUSAL_NO_PROFILE = "no_profile"


@dataclass(frozen=True, slots=True)
class Refusal:
    """Why an action did nothing. ``reason`` is the stable machine token."""

    reason: str
    targets: tuple[Path, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Everything one action needs; frozen so no handler can re-decide it.

    ``profile`` is the active ``MetricProfile`` (its axis ids reach the prompt
    and the cache identity), not a name string — the annotation stays loose so
    this module imports no services.
    """

    targets: tuple[Path, ...]
    backend: str
    profile: object | None = None
    mode: str | None = None
    effort: str | None = None
    origin: str = ORIGIN_MENU

    def __post_init__(self) -> None:
        if self.backend not in BACKENDS:
            raise ValueError(
                f"ActionContext.backend must be one of {BACKENDS!r}, "
                f"got {self.backend!r} (there is no default backend)"
            )
        if self.origin not in ORIGINS:
            raise ValueError(
                f"ActionContext.origin must be one of {ORIGINS!r}, got {self.origin!r}"
            )
        object.__setattr__(
            self,
            "targets",
            tuple(p if isinstance(p, Path) else Path(p) for p in (self.targets or ())),
        )

    @property
    def is_empty(self) -> bool:
        return not self.targets


def current_backend(owner) -> str:
    """The owner's current judgment domain, validated — never coerced.

    ``owner._judgment_domain`` is the single authority (see
    ``use_cases.ai_analysis._set_judgment_domain``). Anything else — a missing
    attribute, an empty string, a typo — raises instead of defaulting to
    ``algorithms``: a silent default is what let an action analyze with the
    wrong backend after a Settings switch.
    """
    domain = str(getattr(owner, "_judgment_domain", "") or "").strip().lower()
    if domain not in BACKENDS:
        raise ValueError(
            f"owner has no valid judgment domain (got {domain!r}); an action "
            "context cannot choose a backend for it"
        )
    return domain


def _analysis_parameters(owner) -> dict:
    """Snapshot the analysis parameters an action must carry.

    Mode + active profile + reasoning effort are read ONCE here, so downstream
    code never re-reads them (the reason a result could be stored under a
    configuration other than the one that produced it). The profile is the slot
    of THIS action's backend (``profile_for_domain``), so an AI action carries
    the judge's axis set and an Algorithms action the local derivation — never
    the other backend's.

    The settings read is marked ``# action-context:`` because it exists ONLY to
    snapshot the effort the request will use — it never selects a backend.
    """
    state = getattr(owner, "state", None)
    try:
        mode = getattr(state, "mode", None) if state is not None else None
    except Exception:
        mode = None
    backend = current_backend(owner)
    try:
        from tabs.image_gallery.use_cases.profile_select import active_profile

        profile = active_profile(state, domain=backend) if state is not None else None
    except Exception:
        profile = None
    effort = None
    try:
        settings = owner._ai_settings_store.load()  # action-context: effort snapshot only
        effort = getattr(settings, "reasoning_effort", None)
    except Exception:
        effort = None
    return {
        "backend": backend,
        "profile": profile,
        "mode": mode,
        "effort": effort,
    }


def context_for_paths(owner, paths, *, origin: str) -> ActionContext:
    """An explicit context for an already-known target set (internal loops).

    Used by the domain switch's bounded visible pass and the deprecated point
    adapters; it performs no scope resolution of its own.
    """
    return ActionContext(
        targets=tuple(paths or ()), origin=origin, **_analysis_parameters(owner)
    )


def point_context(owner, path: Path, *, origin: str = ORIGIN_ACTION) -> ActionContext:
    """The point form of an action: ``targets=(path,)`` — nothing else."""
    return context_for_paths(owner, (Path(path),), origin=origin)


def build_context(
    owner,
    *,
    origin: str,
    card_path=None,
    focused: bool = False,
    action_id: str | None = None,
) -> ActionContext:
    """The ONE context builder for every gallery action.

    ``action_id`` selects the scope rule from ``action_scope.ACTION_SCOPE_POLICY``
    (the ONE policy table); without it the pre-policy selection_or_card
    precedence applies. ``card_path`` (context menu / Quick Look) and
    ``focused=True`` (keyboard) are the only inputs, and neither ever
    substitutes a card for an empty scope: an empty scope is a valid answer the
    handler refuses by name.

    The analysis parameters and backend are snapshotted from the owner once.
    """
    if action_id is not None:
        targets = action_scope.resolve_scope(
            owner, action_id, card_path=card_path, focused=focused
        ).targets
    else:
        targets = action_scope.resolve_targets(
            owner, card_path=card_path, focused=focused
        )
    return ActionContext(
        targets=tuple(targets), origin=origin, **_analysis_parameters(owner)
    )


__all__ = [
    "ActionContext",
    "BACKEND_AI",
    "BACKEND_ALGORITHMS",
    "BACKENDS",
    "ORIGIN_ACTION",
    "ORIGIN_KEYBOARD",
    "ORIGIN_MENU",
    "ORIGINS",
    "REFUSAL_AMBIGUOUS_SCOPE",
    "REFUSAL_EMPTY_SCOPE",
    "REFUSAL_NO_HANDLER",
    "REFUSAL_NO_PROFILE",
    "REFUSAL_NO_ITEMS",
    "REFUSAL_NOT_CONFIGURED",
    "Refusal",
    "build_context",
    "context_for_paths",
    "current_backend",
    "point_context",
]

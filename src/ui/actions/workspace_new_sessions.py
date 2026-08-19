"""Bind ``workspace.new_*`` actions to session types.

Runners resolve ``TabRegistry.get_tab`` at click time so deferred tabs
still work.  The public API is generic — no tab-specific names.
"""

from __future__ import annotations

from collections.abc import Callable

from core.actions.types import ActionTarget


def runner_for(
    session_type: str,
    create_session: Callable[[str], None],
) -> Callable[[], None]:
    """Return a click handler that creates a session of *session_type*."""
    def _run() -> None:
        from tabs.registry import TabRegistry

        if TabRegistry().get_tab(session_type) is None:
            return
        create_session(session_type)

    return _run


def target_for(
    session_type: str,
    *,
    ensure_visible: Callable[[], None] | None = None,
    resolve_card: Callable[[str], object | None] | None = None,
) -> ActionTarget | None:
    """Return an ``ActionTarget`` for a tab's new-session action."""
    if ensure_visible is None and resolve_card is None:
        return None
    return ActionTarget(
        ensure_visible=ensure_visible,
        resolve_widget=(
            (lambda st=session_type: resolve_card(st) if resolve_card is not None else None)
            if resolve_card is not None
            else None
        ),
    )


# Backward-compatible aliases (deprecated — prefer runner_for / target_for)
def image_compare_runner(
    create_session: Callable[[str], None],
) -> Callable[[], None]:
    return runner_for("image_compare", create_session)


def multi_compare_runner(
    create_session: Callable[[str], None],
) -> Callable[[], None]:
    return runner_for("multi_compare", create_session)


def image_compare_target(
    *,
    ensure_visible: Callable[[], None] | None = None,
    resolve_card: Callable[[str], object | None] | None = None,
) -> ActionTarget | None:
    return target_for(
        "image_compare",
        ensure_visible=ensure_visible,
        resolve_card=resolve_card,
    )


def multi_compare_target(
    *,
    ensure_visible: Callable[[], None] | None = None,
    resolve_card: Callable[[str], object | None] | None = None,
) -> ActionTarget | None:
    return target_for(
        "multi_compare",
        ensure_visible=ensure_visible,
        resolve_card=resolve_card,
    )

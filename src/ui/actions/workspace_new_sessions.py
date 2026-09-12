"""Bind ``workspace.new_*`` actions to session types.

Session-type literals live here (and in tab packages), not under
``ui/main_window`` — platform isolation forbids ``image_compare`` /
``multi_compare`` word matches in the main-window tree. Runners resolve
``TabRegistry.get_tab`` at click time so deferred tabs still work.
"""

from __future__ import annotations

from collections.abc import Callable

from core.actions.types import ActionTarget

_IMAGE_COMPARE_SESSION = "image_compare"
_MULTI_COMPARE_SESSION = "multi_compare"


def _runner_for(
    session_type: str,
    create_session: Callable[[str], None],
) -> Callable[[], None]:
    def _run() -> None:
        from tabs.registry import TabRegistry

        if TabRegistry().get_tab(session_type) is None:
            return
        create_session(session_type)

    return _run


def _target_for(
    session_type: str,
    *,
    ensure_visible: Callable[[], None] | None,
    resolve_card: Callable[[str], object | None] | None,
) -> ActionTarget | None:
    if ensure_visible is None and resolve_card is None:
        return None
    return ActionTarget(
        ensure_visible=ensure_visible,
        resolve_widget=(
            (lambda st=session_type: resolve_card(st) if resolve_card else None)
            if resolve_card is not None
            else None
        ),
    )


def image_compare_runner(
    create_session: Callable[[str], None],
) -> Callable[[], None]:
    return _runner_for(_IMAGE_COMPARE_SESSION, create_session)


def multi_compare_runner(
    create_session: Callable[[str], None],
) -> Callable[[], None]:
    return _runner_for(_MULTI_COMPARE_SESSION, create_session)


def image_compare_target(
    *,
    ensure_visible: Callable[[], None] | None = None,
    resolve_card: Callable[[str], object | None] | None = None,
) -> ActionTarget | None:
    return _target_for(
        _IMAGE_COMPARE_SESSION,
        ensure_visible=ensure_visible,
        resolve_card=resolve_card,
    )


def multi_compare_target(
    *,
    ensure_visible: Callable[[], None] | None = None,
    resolve_card: Callable[[str], object | None] | None = None,
) -> ActionTarget | None:
    return _target_for(
        _MULTI_COMPARE_SESSION,
        ensure_visible=ensure_visible,
        resolve_card=resolve_card,
    )

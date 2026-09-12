"""Frozen action catalog types for Find Action / command palette."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionTarget:
    """Explicit chrome widget ref for highlight / "show me where".

    Pass the live widget at registration time when it already exists — do not
    reverse-lookup by attribute name (``getattr(widget, "btn_x")``).

    Variants:
    - ``widget`` — pulse this control
    - ``widget`` + ``menu_action_id`` — open that title-bar menu and pulse the row
    - ``ensure_visible`` + ``resolve_widget`` — bring UI on screen (e.g. session
      picker), then pulse whatever ``resolve_widget`` returns
    """

    widget: object | None = None
    menu_action_id: str | None = None
    ensure_visible: Callable[[], None] | None = None
    resolve_widget: Callable[[], object | None] | None = None


@dataclass(frozen=True, slots=True)
class ActionDescriptor:
    """One searchable, runnable host or tab action."""

    action_id: str
    label_key: str
    description_key: str | None = None
    breadcrumb: tuple[str, ...] = ()
    owner_tab: str | None = None
    topic: str | None = None
    shortcut: str | None = None
    help_page: str | None = None
    help_anchor: str | None = None
    # i18n keys resolved at query time, in addition to label/description/breadcrumb.
    search_keys: tuple[str, ...] = ()
    # Literal tokens (ids, English backend names) that are not i18n keys.
    search_terms: tuple[str, ...] = ()
    # Explicit position in the empty (unfiltered) palette, e.g. a Settings
    # page followed by its groups and their member slots. Empty means "no
    # preference" — falls back to id-based ordering. Owners set this instead
    # of encoding hierarchy into the action id for the palette to parse back.
    sort_key: tuple[int, ...] = ()
    run: Callable[[], None] | None = None
    target: ActionTarget | None = None

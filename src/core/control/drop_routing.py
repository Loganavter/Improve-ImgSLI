"""Folder/file drop routing for the control surface (plain functions).

``open_folder`` hands paths to whichever live tab accepts them -- through
each tab's own ``accepts_drop``/``handle_drop`` (the same code path a user's
drag-and-drop uses), never by naming a concrete tab class. This module is
that routing, split out of ``core.control.handlers`` so the handler keeps its
file-size budget and so the rules are unit-testable with plain fakes.

Two shapes matter:

* a **folder** -- what a folder-native tab wants (it scans the directory
  itself);
* **files** -- what a file-only tab wants (one whose drop hook never accepts
  a directory). The control surface cannot drive those tabs' "add images"
  dialog from a headless client, so a folder aimed at such a tab is expanded
  with the shared extension set and the files are handed over -- that is the
  only way the live surface can feed them. Which kind is which is *discovered
  from the tab itself* (``accepts_drop``), never assumed here: the platform
  stays tab-agnostic.

A ``hint`` (the host-side drop context a mouse drop would carry -- ``slot``
for Image Compare, ``side`` for Multi Compare) travels verbatim to the tab's
own ``handle_drop``; the router never interprets it. Tabs whose
``handle_drop`` predates the hint parameter keep working: the hinted call is
retried without it (see :func:`_drop`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from .discovery import MethodError

__all__ = [
    "VALID_SIDES",
    "VALID_SLOTS",
    "accepts_paths",
    "drop_hint",
    "folder_image_paths",
    "open_folder_into",
    "route_paths",
]

#: Placement values a drop hint may name: an Image Compare slot (1 = left,
#: 2 = right) and a Multi Compare split side. Different tabs, one hint per
#: call — see :func:`drop_hint`.
VALID_SLOTS: tuple[int, ...] = (1, 2)
VALID_SIDES: tuple[str, ...] = ("left", "right", "top", "bottom")


def drop_hint(params: dict[str, Any]) -> dict[str, Any] | None:
    """Target hint parsed from a drop request's params, or ``None``.

    The drop path normally derives its target from the mouse (``slot`` for
    Image Compare, ``side`` for Multi Compare). A headless control client has
    no pointer, so it may name the same value instead; the hint is passed down
    untouched and each tab reads the key it owns. One hint per call: the two
    belong to different tabs, and honouring one while the other is also set
    would make the request a lie. Unknown values are the control surface's own
    ``MethodError`` — never a silently ignored drop.
    """
    slot = params.get("slot")
    side = params.get("side")
    if slot is None and side is None:
        return None
    if slot is not None and side is not None:
        raise MethodError(
            "pass either slot or side, not both",
            "slot=1|2 targets Image Compare (left/right); "
            "side=left|right|top|bottom targets Multi Compare",
        )
    if slot is not None:
        number = slot if isinstance(slot, int) and not isinstance(slot, bool) else None
        if number is None and isinstance(slot, str) and slot.strip().isdigit():
            number = int(slot.strip())
        if number not in VALID_SLOTS:
            raise MethodError(
                f"unknown slot {slot!r}",
                "use slot=1 (left) or slot=2 (right) — Image Compare",
            )
        return {"slot": number}
    if side not in VALID_SIDES:
        raise MethodError(
            f"unknown side {side!r}",
            "use one of: " + ", ".join(VALID_SIDES) + " (Multi Compare)",
        )
    return {"side": side}


def accepts_paths(tab: Any, paths: list[Path]) -> bool:
    """True when *tab*'s own drop hook accepts *paths*. Never raises."""
    try:
        return bool(tab.accepts_drop(list(paths)))
    except Exception:
        return False


def route_paths(
    tabs: Iterable[tuple[str, Any]],
    paths: list[Path],
    *,
    only: str | None = None,
    hint: dict[str, Any] | None = None,
) -> str | None:
    """Hand *paths* to the first accepting tab; returns its session type.

    *only* restricts the search to one session type (the targeted path used
    by ``open_folder_into``). *hint* is the host-side drop context (see the
    module docstring), passed through untouched. A tab that accepts the paths
    but whose ``handle_drop`` returns falsy is skipped, exactly like the
    untargeted auto-route.
    """
    for session_type, tab in tabs:
        if only is not None and session_type != only:
            continue
        if not accepts_paths(tab, paths):
            continue
        try:
            if _drop(tab, paths, hint):
                return session_type
        except Exception:
            continue
    return None


def _drop(tab: Any, paths: list[Path], hint: dict[str, Any] | None) -> Any:
    """``tab.handle_drop`` with the optional hint, tolerant of older tabs.

    ``handle_drop`` grew its ``hint`` parameter after the first tabs shipped,
    so a tab (or a plain fake) whose hook still takes only ``paths`` must keep
    working: the hinted call is retried without it. With no hint this is
    byte-for-byte today's call -- one positional argument, no retry.
    """
    if hint is None:
        return tab.handle_drop(list(paths))
    try:
        return tab.handle_drop(list(paths), hint)
    except TypeError:
        # Raised before the body runs (arity), so the retry cannot double-apply
        # a drop: the hinted call never got past argument binding.
        return tab.handle_drop(list(paths))


def folder_image_paths(folder: Path) -> list[Path]:
    """Supported images directly inside *folder* (name-sorted; [] on error).

    Non-recursive, mirroring the gallery's own scan depth, and through the
    shared extension set (``shared.image_extensions``) so both paths agree on
    what counts as an image. Never raises.
    """
    from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS

    try:
        entries = sorted(folder.iterdir(), key=lambda path: path.name.lower())
    except OSError:
        return []
    return [
        path
        for path in entries
        if path.is_file() and path.suffix.lower() in ACCEPTED_IMAGE_EXTENSIONS
    ]


def open_folder_into(
    folder: Path,
    wanted: str,
    *,
    tabs: Callable[[], list[tuple[str, Any]]],
    kinds: Iterable[str],
    run_action: Callable[[str], Any],
    hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hand *folder* to the named tab kind, creating that tab if it is absent.

    ``tabs`` is a provider, not a snapshot: creating the tab goes through
    ``workspace.new_<kind>`` and the list must be re-read afterwards.
    ``hint`` is forwarded verbatim to every routing attempt (folder first,
    then the expanded files), so a targeted drop is placed where the caller
    asked -- a tab that does not understand the hint ignores it.
    Returns the handler-shaped ``{"routed", "path", "tab"[", "images"]}``;
    ``images`` is present only when the folder had to be expanded into files
    (honest: the tab took those files, not the directory).

    Raises ``ValueError`` for an unknown kind or when the tab accepts neither
    shape -- the caller maps it to the control surface's own error type.
    """
    kinds = list(kinds)
    if wanted not in kinds:
        raise ValueError(
            f"unknown tab kind {wanted!r} (kinds: {', '.join(sorted(kinds))})"
        )
    routed = route_paths(tabs(), [folder], only=wanted, hint=hint)
    if routed is None and not any(
        session_type == wanted for session_type, _tab in tabs()
    ):
        run_action(f"workspace.new_{wanted}")
        routed = route_paths(tabs(), [folder], only=wanted, hint=hint)
    images: list[Path] = []
    if routed is None:
        images = folder_image_paths(folder)
        if images:
            routed = route_paths(tabs(), images, only=wanted, hint=hint)
    if routed is None:
        raise ValueError(f"tab {wanted!r} did not accept {folder}")
    result: dict[str, Any] = {"routed": True, "path": str(folder), "tab": routed}
    if images:
        result["images"] = len(images)
    return result

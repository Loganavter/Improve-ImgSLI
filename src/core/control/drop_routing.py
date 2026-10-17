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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

__all__ = [
    "accepts_paths",
    "folder_image_paths",
    "open_folder_into",
    "route_paths",
]


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
) -> str | None:
    """Hand *paths* to the first accepting tab; returns its session type.

    *only* restricts the search to one session type (the targeted path used
    by ``open_folder_into``). A tab that accepts the paths but whose
    ``handle_drop`` returns falsy is skipped, exactly like the untargeted
    auto-route.
    """
    for session_type, tab in tabs:
        if only is not None and session_type != only:
            continue
        if not accepts_paths(tab, paths):
            continue
        try:
            if tab.handle_drop(list(paths)):
                return session_type
        except Exception:
            continue
    return None


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
) -> dict[str, Any]:
    """Hand *folder* to the named tab kind, creating that tab if it is absent.

    ``tabs`` is a provider, not a snapshot: creating the tab goes through
    ``workspace.new_<kind>`` and the list must be re-read afterwards.
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
    routed = route_paths(tabs(), [folder], only=wanted)
    if routed is None and not any(
        session_type == wanted for session_type, _tab in tabs()
    ):
        run_action(f"workspace.new_{wanted}")
        routed = route_paths(tabs(), [folder], only=wanted)
    images: list[Path] = []
    if routed is None:
        images = folder_image_paths(folder)
        if images:
            routed = route_paths(tabs(), images, only=wanted)
    if routed is None:
        raise ValueError(f"tab {wanted!r} did not accept {folder}")
    result: dict[str, Any] = {"routed": True, "path": str(folder), "tab": routed}
    if images:
        result["images"] = len(images)
    return result

"""Tab → host help contribution registry.

Tabs publish topic subtrees via ``notify_all("contribute_help", registry)``.
The host owns the shell tree (root / workspace / ui / platform); tabs own
their workspace hubs, pages, aliases, body roots, and icon resolvers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtGui import QIcon

IconResolver = Callable[[str], QIcon | None]


@dataclass(slots=True)
class HelpSubtreeContribution:
    """One tab's help fragment to merge into the host tree."""

    attach_under: str
    child_ids: tuple[str, ...]
    nodes: dict[str, dict[str, Any]]
    aliases: dict[str, str] = field(default_factory=dict)
    body_root: Path | None = None
    resolve_icon: IconResolver | None = None
    asset_root: Path | None = None


class HelpContributionRegistry:
    """Mutable bag filled by ``contribute_help`` hooks, then merged once."""

    def __init__(self) -> None:
        self._subtrees: list[HelpSubtreeContribution] = []

    def contribute(
        self,
        *,
        attach_under: str,
        child_ids: tuple[str, ...] | list[str],
        nodes: dict[str, dict[str, Any]],
        aliases: dict[str, str] | None = None,
        body_root: Path | str | None = None,
        resolve_icon: IconResolver | None = None,
        asset_root: Path | str | None = None,
    ) -> None:
        root = Path(body_root) if body_root is not None else None
        assets = Path(asset_root) if asset_root is not None else None
        self._subtrees.append(
            HelpSubtreeContribution(
                attach_under=attach_under,
                child_ids=tuple(child_ids),
                nodes=dict(nodes),
                aliases=dict(aliases or {}),
                body_root=root,
                resolve_icon=resolve_icon,
                asset_root=assets,
            )
        )

    @property
    def subtrees(self) -> tuple[HelpSubtreeContribution, ...]:
        return tuple(self._subtrees)

    def icon_resolvers(self) -> tuple[IconResolver, ...]:
        return tuple(s.resolve_icon for s in self._subtrees if s.resolve_icon is not None)

    def asset_roots(self) -> tuple[Path, ...]:
        return tuple(s.asset_root for s in self._subtrees if s.asset_root is not None)

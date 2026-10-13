"""Help topic tree: scanned hubs/pages, tab hub presentation, path resolution.

Audit-Meta: pattern=single-owner reason="one merged HelpTree: fs scan + hub-fragment overlay, path/body/asset resolution, and validation share one cache — splitting would fork the scope"
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from plugins.help.contribution import HelpHubContribution
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

HelpNodeKind = Literal["hub", "page"]
IconResolver = Callable[[str], Any]

_installed_hub_contributions: list[HelpHubContribution] | None = None
_plugin_help_roots_cache: tuple[Path, ...] | None = None


@dataclass(frozen=True, slots=True)
class HelpNode:
    node_id: str
    kind: HelpNodeKind
    title: str
    description: str = ""
    children: tuple[str, ...] = ()
    body: str | None = None  # relative path under body_root/<lang>/
    title_key: str | None = None
    description_key: str | None = None
    icon: str | None = None
    body_root: Path | None = None  # None → host resources/help


@dataclass(frozen=True, slots=True)
class HelpTree:
    root_id: str
    nodes: dict[str, HelpNode]
    asset_roots: tuple[Path, ...] = ()
    icon_resolvers: tuple[IconResolver, ...] = ()
    def get(self, node_id: str) -> HelpNode | None:
        return self.nodes.get(node_id)

    def require(self, node_id: str) -> HelpNode:
        node = self.get(node_id)
        if node is None:
            raise KeyError(f"Unknown help node: {node_id}")
        return node

    def children_of(self, node_id: str) -> tuple[HelpNode, ...]:
        node = self.require(node_id)
        return tuple(self.require(child_id) for child_id in node.children)

    def resolve_path(self, slug_or_id: str) -> str:
        """Map a dotted help path to a canonical node id (``KeyError`` if missing)."""
        key = (slug_or_id or "").strip()
        if not key:
            return self.root_id
        if key in self.nodes:
            return key
        raise KeyError(f"Unknown help page: {slug_or_id!r}")

    def path_to(self, node_id: str) -> tuple[str, ...]:
        """Root-inclusive path of ids from root to ``node_id``."""
        target = node_id
        parent_of: dict[str, str | None] = {self.root_id: None}
        for nid, node in self.nodes.items():
            for child in node.children:
                parent_of[child] = nid
        chain: list[str] = []
        cur: str | None = target
        seen: set[str] = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = parent_of.get(cur)
        chain.reverse()
        if not chain or chain[0] != self.root_id:
            return (self.root_id, target)
        return tuple(chain)

    def siblings_of(self, node_id: str) -> tuple[HelpNode, ...]:
        """Nodes that share the same parent (including ``node_id``)."""
        if node_id == self.root_id:
            return (self.require(self.root_id),)
        parent_of: dict[str, str] = {}
        for nid, node in self.nodes.items():
            for child in node.children:
                parent_of[child] = nid
        parent = parent_of.get(node_id)
        if parent is None:
            return (self.require(node_id),)
        return self.children_of(parent)

    def parent_id(self, node_id: str) -> str | None:
        if node_id == self.root_id:
            return None
        for nid, node in self.nodes.items():
            if node_id in node.children:
                return nid
        return None


def host_help_root() -> Path:
    return Path(resource_path("resources/help"))


def install_help_contributions(
    contributions: list[HelpHubContribution],
) -> HelpTree:
    """Store tab hub-presentation fragments and rebuild the cached tree.

    Structure is scanned from the filesystem; fragments only overlay hub
    titles/descriptions/icons and icon resolvers (see
    ``plugins.help.scan``).
    """
    global _installed_hub_contributions
    _installed_hub_contributions = list(contributions)
    clear_help_tree_cache()
    return get_help_tree()


def build_help_tree() -> HelpTree:
    """Build the tree from the filesystem scan (web canon).

    Structure, bodies and asset roots come from ``scan_help_tree``; hub
    presentation and icon resolvers come from the installed hub fragments.
    """
    from plugins.help.scan import scan_help_tree

    return scan_help_tree(_installed_hub_contributions or [])


def _validate_tree(tree: HelpTree) -> None:
    for node in tree.nodes.values():
        for child_id in node.children:
            if child_id not in tree.nodes:
                raise KeyError(f"{node.node_id} references missing child {child_id}")
        if node.kind == "page" and not node.body:
            raise ValueError(f"page {node.node_id} missing body")


@lru_cache(maxsize=1)
def get_help_tree() -> HelpTree:
    return build_help_tree()


def clear_help_tree_cache() -> None:
    get_help_tree.cache_clear()


def clear_help_label_cache() -> None:
    from plugins.help import labels

    labels.clear_help_label_cache()


def clear_help_contributions() -> None:
    """Drop installed tab hub fragments (tests / full rebuild)."""
    global _installed_hub_contributions
    _installed_hub_contributions = None
    clear_help_tree_cache()
    clear_help_label_cache()


def normalize_help_language(language: str) -> str:
    lang = (language or "en").strip() or "en"
    base = lang.split("_")[0].lower() if "_" in lang else lang.lower()
    if base == "pt":
        return "pt_BR"
    if base.startswith("zh"):
        return "zh"
    if base in ("ru", "en"):
        return base
    return "en"


def resolve_help_body_path(
    language: str,
    body_rel: str,
    *,
    body_root: Path | None = None,
) -> Path:
    """Prefer ``<lang>/<body>``, fall back to ``en/<body>`` under ``body_root``."""
    root = body_root if body_root is not None else host_help_root()
    lang_code = normalize_help_language(language)

    candidate = root / lang_code / body_rel
    if candidate.is_file():
        return candidate
    return root / "en" / body_rel


def read_help_page_markdown(
    language: str,
    body_rel: str,
    *,
    body_root: Path | None = None,
) -> str:
    from plugins.help.interpolate import interpolate_help_markdown

    path = resolve_help_body_path(language, body_rel, body_root=body_root)
    if not path.is_file():
        return f"## Missing page\n\nBody not found: `{body_rel}`\n"
    raw = path.read_text(encoding="utf-8")
    return interpolate_help_markdown(raw, language)


def _plugin_help_asset_roots() -> tuple[Path, ...]:
    """Filesystem roots of plugin-owned help packages (not tab-registered).

    Last-resort fallback for trees built without plugin contributions
    (e.g. tabs-only test trees): plugin ``resources/help`` packages follow
    the same ``assets/<rel>`` layout as tab contributions. Cached — the
    package layout is static per checkout.
    """
    global _plugin_help_roots_cache
    if _plugin_help_roots_cache is None:
        src_root = Path(__file__).resolve().parents[2]
        plugins = src_root / "plugins"
        roots: list[Path] = []
        if plugins.is_dir():
            roots = sorted(
                p for p in plugins.glob("*/resources/help") if p.is_dir()
            )
        _plugin_help_roots_cache = tuple(roots)
    return _plugin_help_roots_cache


def resolve_help_asset(rel_path: str, tree: HelpTree | None = None) -> Path | None:
    """Resolve a figure path against host + contributed asset roots."""
    rel = rel_path.lstrip("/")
    roots: list[Path] = [host_help_root()]
    if tree is not None:
        roots.extend(tree.asset_roots)
    candidates: list[Path] = []
    for root in roots:
        candidates.append(root / "assets" / rel)
        candidates.append(root / rel)
    for root in _plugin_help_asset_roots():
        candidates.append(root / "assets" / rel)
        candidates.append(root / rel)
    for path in candidates:
        if path.is_file():
            return path
    return None
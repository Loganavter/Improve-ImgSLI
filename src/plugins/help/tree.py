"""Help topic tree: hubs, pages, legacy slug aliases, tab contributions."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from plugins.help.contribution import HelpContributionRegistry, HelpSubtreeContribution
from utils.resource_loader import resource_path

HelpNodeKind = Literal["hub", "page"]
IconResolver = Callable[[str], Any]

_installed_contributions: HelpContributionRegistry | None = None


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
    aliases: dict[str, str]
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

    def resolve_alias(self, slug_or_id: str) -> str:
        """Map legacy ``help_page`` slug or node id → canonical node id."""
        key = (slug_or_id or "").strip()
        if not key:
            return self.root_id
        if key in self.nodes:
            return key
        mapped = self.aliases.get(key)
        if mapped and mapped in self.nodes:
            return mapped
        raise KeyError(f"Unknown help slug or node: {slug_or_id!r}")

    def path_to(self, node_id: str) -> tuple[str, ...]:
        """Root-inclusive path of ids from root to ``node_id``."""
        target = self.resolve_alias(node_id) if node_id not in self.nodes else node_id
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


def _node_from_raw(
    node_id: str,
    data: dict[str, Any],
    *,
    body_root: Path | None = None,
) -> HelpNode:
    kind = data["kind"]
    if kind not in ("hub", "page"):
        raise ValueError(f"Invalid kind for {node_id}: {kind}")
    return HelpNode(
        node_id=node_id,
        kind=kind,
        title=str(data.get("title") or node_id),
        description=str(data.get("description") or ""),
        children=tuple(data.get("children") or ()),
        body=data.get("body"),
        title_key=data.get("title_key"),
        description_key=data.get("description_key"),
        icon=data.get("icon"),
        body_root=body_root,
    )


def load_help_tree(tree_path: Path | None = None) -> HelpTree:
    """Load host shell tree only (no tab contributions)."""
    path = tree_path or (host_help_root() / "tree.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    nodes: dict[str, HelpNode] = {}
    for node_id, data in raw["nodes"].items():
        nodes[node_id] = _node_from_raw(node_id, data, body_root=None)
    root_id = str(raw.get("root_id") or "root")
    if root_id not in nodes:
        raise KeyError(f"root_id {root_id!r} missing from nodes")
    aliases = {str(k): str(v) for k, v in (raw.get("aliases") or {}).items()}
    tree = HelpTree(root_id=root_id, nodes=nodes, aliases=aliases)
    _validate_tree(tree)
    return tree


def merge_help_contributions(
    base: HelpTree,
    registry: HelpContributionRegistry,
) -> HelpTree:
    """Attach tab subtrees under host parents; merge aliases and asset roots."""
    nodes = dict(base.nodes)
    aliases = dict(base.aliases)
    asset_roots: list[Path] = list(base.asset_roots)

    for fragment in registry.subtrees:
        _apply_subtree(nodes, aliases, asset_roots, fragment)

    tree = HelpTree(
        root_id=base.root_id,
        nodes=nodes,
        aliases=aliases,
        asset_roots=tuple(asset_roots),
        icon_resolvers=registry.icon_resolvers(),
    )
    _validate_tree(tree)
    return tree

def _apply_subtree(
    nodes: dict[str, HelpNode],
    aliases: dict[str, str],
    asset_roots: list[Path],
    fragment: HelpSubtreeContribution,
) -> None:
    parent = nodes.get(fragment.attach_under)
    if parent is None:
        raise KeyError(
            f"help contribution attach_under {fragment.attach_under!r} missing"
        )

    for node_id, data in fragment.nodes.items():
        if node_id in nodes:
            raise KeyError(f"help contribution redefines existing node {node_id}")
        nodes[node_id] = _node_from_raw(
            node_id, data, body_root=fragment.body_root
        )

    for alias, target in fragment.aliases.items():
        if alias in aliases and aliases[alias] != target:
            raise KeyError(
                f"help alias conflict {alias!r}: "
                f"{aliases[alias]!r} vs {target!r}"
            )
        aliases[alias] = target

    existing_children = list(parent.children)
    for child_id in fragment.child_ids:
        if child_id not in nodes:
            raise KeyError(
                f"help contribution child {child_id} missing from contributed nodes"
            )
        if child_id not in existing_children:
            existing_children.append(child_id)
    nodes[fragment.attach_under] = replace(parent, children=tuple(existing_children))

    if fragment.asset_root is not None and fragment.asset_root not in asset_roots:
        asset_roots.append(fragment.asset_root)


def install_help_contributions(registry: HelpContributionRegistry) -> HelpTree:
    """Store tab contributions and rebuild the cached merged tree."""
    global _installed_contributions
    _installed_contributions = registry
    clear_help_tree_cache()
    return get_help_tree()


def build_help_tree(
    tree_path: Path | None = None,
    *,
    contributions: HelpContributionRegistry | None = None,
) -> HelpTree:
    base = load_help_tree(tree_path)
    registry = contributions if contributions is not None else _installed_contributions
    if registry is None:
        return base
    return merge_help_contributions(base, registry)


def _validate_tree(tree: HelpTree) -> None:
    for node in tree.nodes.values():
        for child_id in node.children:
            if child_id not in tree.nodes:
                raise KeyError(f"{node.node_id} references missing child {child_id}")
        if node.kind == "page" and not node.body:
            raise ValueError(f"page {node.node_id} missing body")
    for alias, target in tree.aliases.items():
        if target not in tree.nodes:
            raise KeyError(f"alias {alias!r} → missing {target}")


@lru_cache(maxsize=1)
def get_help_tree() -> HelpTree:
    return build_help_tree()


def clear_help_tree_cache() -> None:
    get_help_tree.cache_clear()


def clear_help_contributions() -> None:
    """Drop installed tab contributions (tests / full rebuild)."""
    global _installed_contributions
    _installed_contributions = None
    clear_help_tree_cache()


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
    for path in candidates:
        if path.is_file():
            return path
    return None

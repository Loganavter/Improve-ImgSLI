"""Filesystem-derived help tree (web canon, phase 2: titles from ``##``).

Derives node ids, kinds, children and body paths by scanning
``<package>/resources/help/en/`` directories instead of reading
``tree.json`` + contribution ``nodes`` dicts:

- host package (``src/resources/help``) mounts at the tree root;
- ``src/tabs/<name>`` mounts at ``workspace.<name>`` (convention);
- ``src/plugins/<name>`` mounts at the ``HELP_MOUNT`` dotted id declared in
  ``src/plugins/<name>/help.py`` (single line, no node registry).

Layout convention per mount: exactly one ``*.md`` directly under ``en/``
(and no subdirectories) means the mount id itself is a page (e.g.
``platform.settings``); otherwise the mount is a hub and every ``*.md`` is a
page ``<mount>.<relative-stem>`` (e.g. a tab's ``comparison`` page).

Presentation (hub titles/descriptions/icons, ``help://`` aliases, asset roots
and icon resolvers) still flows through the installed contribution fragments
— the isolation-safe channel — until phase 3 removes aliases. Page titles
and card subtitles come from each page's own ``##`` heading, an optional
leading frontmatter block (``description``/``icon``), and the first paragraph
fallback (see ``plugins.help.labels`` and ``plugins.help.meta``); the
app-shell hubs (``root``/``workspace``/``ui``/``platform``) keep their static
meta below.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from plugins.help.meta import PageMeta, parse_page_meta
from plugins.help.tree import HelpNode, HelpTree, _validate_tree, host_help_root

#: Canonical language for structure discovery; per-file fallback to EN at
#: read time stays in ``resolve_help_body_path``.
_CANON_LANG = "en"

#: App-shell root order (kept fixed; deeper levels are fs-sorted).
ROOT_CHILDREN = ("about", "workspace", "ui", "platform")

#: Static presentation for the four app-shell hubs (title/description keys
#: resolve through the ``help`` i18n pack; everything else is scanned).
HOST_HUB_META = {
    "root": {
        "title_key": "help.hub.root.title",
        "description_key": "help.hub.root.desc",
        "title": "Help",
        "description": "Browse topics by area",
        "icon": "help.svg",
    },
    "workspace": {
        "title_key": "help.hub.workspace.title",
        "description_key": "help.hub.workspace.desc",
        "title": "Workspace",
        "description": "Session types and compare tools",
        "icon": "photo_icon.svg",
    },
    "ui": {
        "title_key": "help.hub.ui.title",
        "description_key": "help.hub.ui.desc",
        "title": "UI",
        "description": "Controls, lists, canvas chrome",
        "icon": "text-manipulator.svg",
    },
    "platform": {
        "title_key": "help.hub.platform.title",
        "description_key": "help.hub.platform.desc",
        "title": "Platform",
        "description": "Settings, files, shortcuts",
        "icon": "settings.svg",
    },
}

def _src_root() -> Path:
    return host_help_root().parent.parent


def _read_plugin_mount(plugin_dir: Path) -> str | None:
    """Return the ``HELP_MOUNT`` dotted id from ``plugins/<name>/help.py``."""
    help_py = plugin_dir / "help.py"
    if not help_py.is_file():
        return None
    try:
        module = ast.parse(help_py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for stmt in module.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "HELP_MOUNT"
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            return stmt.value.value
    return None


def _discover_packages() -> list[tuple[str | None, Path]]:
    """Return ``(mount, help_dir)`` for host (mount ``None`` = root) + tabs + plugins."""
    found: list[tuple[str | None, Path]] = []
    host = host_help_root()
    if (host / _CANON_LANG).is_dir():
        found.append((None, host))
    src = _src_root()
    for tab_dir in sorted((src / "tabs").glob("*/resources/help")):
        if (tab_dir / _CANON_LANG).is_dir():
            found.append((f"workspace.{tab_dir.parent.parent.name}", tab_dir.resolve()))
    for plugin_dir in sorted((src / "plugins").glob("*/resources/help")):
        if (plugin_dir / _CANON_LANG).is_dir():
            mount = _read_plugin_mount(plugin_dir.parent.parent)
            if mount is not None:
                found.append((mount, plugin_dir.resolve()))
    return found


def _page_meta(path: Path) -> PageMeta:
    """Parse a page's leading frontmatter; a read failure yields empty meta."""
    try:
        return parse_page_meta(path.read_text(encoding="utf-8"))
    except OSError:
        return PageMeta()


def _page_node(
    node_id: str,
    body: str,
    body_root: Path | None,
    *,
    description: str = "",
    icon: str = "",
) -> HelpNode:
    return HelpNode(
        node_id=node_id,
        kind="page",
        title=node_id,
        description=description,
        children=(),
        body=body,
        title_key=None,
        description_key=None,
        icon=icon,
        body_root=body_root,
    )


def _hub_node(node_id: str, children: tuple[str, ...], body_root: Path | None = None) -> HelpNode:
    return HelpNode(
        node_id=node_id,
        kind="hub",
        title=node_id,
        description="",
        children=children,
        body=None,
        title_key=None,
        description_key=None,
        icon="",
        body_root=body_root,
    )


def _normalize_fragments(fragments: Any) -> list[Any]:
    """Accept the installed hub-fragment list (plain list, no registry)."""
    if fragments is None:
        return []
    return list(fragments)


def scan_help_tree(hub_fragments: Any = ()) -> HelpTree:
    """Build a ``HelpTree`` purely from the filesystem.

    Structure (ids, kinds, bodies, children) and asset roots come from the
    scan; hub presentation and icon resolvers come from the installed
    ``HelpHubContribution`` fragments.
    """
    frags = _normalize_fragments(hub_fragments)

    hub_meta: dict[str, dict[str, Any]] = dict(HOST_HUB_META)
    for fragment in frags:
        hub_meta[fragment.mount] = fragment.hub_meta()

    resolvers: list[Any] = []
    for fragment in frags:
        resolver = fragment.resolve_icon
        if resolver is not None:
            resolvers.append(resolver)

    discovered: list[tuple[str | None, Path]] = _discover_packages()

    nodes: dict[str, HelpNode] = {}
    host_root = host_help_root().resolve()
    hub_roots: dict[str, Path | None] = {}

    def add_hub(node_id: str, body_root: Path | None = None) -> None:
        if node_id not in nodes:
            nodes[node_id] = _hub_node(node_id, (), body_root)
            hub_roots[node_id] = body_root
        elif body_root is not None and hub_roots.get(node_id) is None:
            hub_roots[node_id] = body_root

    pending_children: dict[str, set[str]] = {}

    def attach(parent: str, child: str) -> None:
        pending_children.setdefault(parent, set()).add(child)

    for mount, help_dir in discovered:
        body_root: Path | None = None if help_dir.resolve() == host_root else help_dir.resolve()
        lang_dir = help_dir / _CANON_LANG
        md_files = sorted(
            p for p in lang_dir.rglob("*.md") if ".git" not in p.parts and "assets" not in p.relative_to(lang_dir).parts
        )
        top_files = [p for p in md_files if p.parent == lang_dir]
        has_subdirs = any(p.parent != lang_dir for p in md_files)

        if mount is None:
            # Host package: ids mirror the relative path (about, ui.buttons…).
            for path in md_files:
                rel = path.relative_to(lang_dir)
                stem = rel.with_suffix("")
                page_id = ".".join(stem.parts)
                parent = ".".join(stem.parts[:-1]) if len(stem.parts) > 1 else "root"
                meta = _page_meta(path)
                nodes[page_id] = _page_node(
                    page_id,
                    rel.as_posix(),
                    None,
                    description=meta.description,
                    icon=meta.icon,
                )
                if parent == "root":
                    attach("root", page_id)
                else:
                    add_hub(parent)
                    attach(parent, page_id)
            for path in md_files:
                rel = path.relative_to(lang_dir)
                for i in range(1, len(rel.parts)):
                    hub_id = ".".join(rel.parts[:i])
                    if hub_id in nodes and nodes[hub_id].kind == "page":
                        continue
                    add_hub(hub_id)
                    parent = ".".join(rel.parts[: i - 1]) if i > 1 else "root"
                    attach(parent, hub_id)
        elif len(top_files) == 1 and not has_subdirs:
            # Single-page package: the mount id itself is the page.
            rel = top_files[0].relative_to(lang_dir)
            meta = _page_meta(top_files[0])
            nodes[mount] = _page_node(
                mount,
                rel.as_posix(),
                body_root,
                description=meta.description,
                icon=meta.icon,
            )
            parent = mount.rpartition(".")[0]
            attach(parent, mount)
            add_hub(parent)
        else:
            # Multi-page package: the mount is a hub of pages.
            add_hub(mount, body_root)
            parent = mount.rpartition(".")[0]
            attach(parent, mount)
            add_hub(parent)
            for path in md_files:
                rel = path.relative_to(lang_dir)
                stem = rel.with_suffix("")
                page_id = mount + "." + ".".join(stem.parts)
                meta = _page_meta(path)
                nodes[page_id] = _page_node(
                    page_id,
                    rel.as_posix(),
                    body_root,
                    description=meta.description,
                    icon=meta.icon,
                )
                if len(stem.parts) > 1:
                    hub_id = mount + "." + ".".join(stem.parts[:-1])
                    add_hub(hub_id, body_root)
                    attach(hub_id, page_id)
                    attach(mount, hub_id)
                else:
                    attach(mount, page_id)

    # Synthesized mount containers + root.
    for hub_id in ("workspace", "root"):
        add_hub(hub_id)
    if "workspace" in pending_children:
        attach("root", "workspace")
    for parent, children in pending_children.items():
        add_hub(parent)
        ordered = tuple(sorted(children))
        if parent == "root":
            ordered = tuple(c for c in ROOT_CHILDREN if c in children) + tuple(
                sorted(c for c in children if c not in ROOT_CHILDREN)
            )
        nodes[parent] = _hub_node(parent, ordered, hub_roots.get(parent))

    for hub_id, meta in hub_meta.items():
        current = nodes.get(hub_id)
        if current is not None and current.kind == "hub":
            nodes[hub_id] = HelpNode(
                node_id=current.node_id,
                kind=current.kind,
                title=str(meta.get("title", current.node_id)),
                description=str(meta.get("description", "")),
                children=current.children,
                body=None,
                title_key=meta.get("title_key"),
                description_key=meta.get("description_key"),
                icon=str(meta.get("icon", "")),
                body_root=current.body_root,
            )

    tree = HelpTree(
        root_id="root",
        nodes=nodes,
        icon_resolvers=tuple(resolvers),
    )
    _validate_tree(tree)
    return tree

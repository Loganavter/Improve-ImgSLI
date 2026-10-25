"""Help topic tree: scanned hubs/pages, tab hub presentation, path resolution.

Audit-Meta: pattern=single-owner reason="one merged HelpTree: fs scan + hub-fragment overlay, path/body/asset resolution, and validation share one cache — splitting would fork the scope"
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from plugins.help.contribution import HelpHubContribution
from plugins.help.meta import split_frontmatter
from core.log_names import APP_LOGGER_NAME
from utils.resource_loader import resource_path

logger = logging.getLogger(APP_LOGGER_NAME)

HelpNodeKind = Literal["hub", "page"]
IconResolver = Callable[[str], Any]

_installed_hub_contributions: list[HelpHubContribution] | None = None


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
    path = resolve_help_body_path(language, body_rel, body_root=body_root)
    if not path.is_file():
        return f"## Missing page\n\nBody not found: `{body_rel}`\n"
    # Bodies carry literal, on-screen labels (no `{{tr:}}` interpolation):
    # help content is written per language, so no runtime key lookup is needed.
    raw = path.read_text(encoding="utf-8")
    # Strip the optional card frontmatter so the rendered page never starts
    # with a bare `---` block (the meta is parsed separately by the scan).
    _meta, body = split_frontmatter(raw)
    return body


#: Manifests of record for locale/theme figure variants: the recipe set
#: (``help_figures.py``) and the live set captured from a running app
#: (``help_live.py``). Both write the same ``assets/<locale>/<theme>/`` layout,
#: so both must contribute declarations — reading only the recipe manifest left
#: a live figure's matrix invisible to the resolver, and a missing live cell
#: silently fell back to the base (English/dark) image instead of failing closed.
#: Runtime reads them defensively: a packaged/toolkit-only install may ship
#: neither, and a missing manifest must degrade to the flat base image.
_VARIANT_MANIFEST = Path(__file__).resolve().parents[2] / "devtools" / "help_figures.json"
_LIVE_VARIANT_MANIFEST = (
    Path(__file__).resolve().parents[2] / "devtools" / "help_figures_live.json"
)


def _help_asset_tail(path: Path) -> tuple[str, ...]:
    """Path tail from the nearest ``help`` component (manifest destinations key)."""
    parts = path.parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "help":
            return parts[index:]
    return parts


@lru_cache(maxsize=1)
def _declared_help_variants() -> dict[tuple[str, ...], frozenset[tuple[str, str]]]:
    """``(locale, theme)`` pairs declared per figure destination.

    A figure with a single locale *and* a single theme ships one flat file, so
    it declares no variant folder (empty set). A figure with more than one
    variant declares the full locale x theme matrix and every cell lives under
    ``assets/<locale>/<theme>/``. Declarations are the UNION of both manifests:
    two figures may describe the same destination (the devtool surface of
    record and the live recipe that actually captures it), and a union keeps
    the stronger claim instead of letting load order decide.
    """
    declared: dict[tuple[str, ...], frozenset[tuple[str, str]]] = {}
    for manifest in (_VARIANT_MANIFEST, _LIVE_VARIANT_MANIFEST):
        try:
            raw = json.loads(Path(manifest).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = raw.get("figures") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            destination, locales, themes = (
                entry.get("destination"),
                entry.get("locales"),
                entry.get("themes"),
            )
            if (
                not isinstance(destination, str)
                or not isinstance(locales, list)
                or not isinstance(themes, list)
                or not locales
                or not themes
            ):
                continue
            pairs = frozenset(
                (str(locale), str(theme).lower())
                for locale in locales
                for theme in themes
            )
            if len(pairs) <= 1:
                continue
            key = _help_asset_tail(Path(destination))
            declared[key] = declared.get(key, frozenset()) | pairs
    return declared


def clear_help_variant_cache() -> None:
    """Drop the parsed variant declarations (tests / edited recipes)."""
    _declared_help_variants.cache_clear()


def _declared_variants_for(base: Path) -> frozenset[tuple[str, str]]:
    return _declared_help_variants().get(_help_asset_tail(base), frozenset())


def _help_assets_root(base: Path) -> Path:
    """Nearest ``assets`` ancestor of the literal asset path (variant home)."""
    for parent in base.parents:
        if parent.name == "assets":
            return parent
    return base.parent


def resolve_help_asset(
    rel_path: str,
    body_file: Path | str | None = None,
    *,
    locale: str | None = None,
    theme: str | None = None,
    declared_variants: Iterable[tuple[str, str]] | None = None,
) -> Path | None:
    """Resolve a body-relative image path to a locale/theme variant.

    Chain, same literal markdown path (``assets/<name>`` is today's base):

    1. ``assets/<locale>/<theme>/<name>``
    2. ``assets/<locale>/<name>``
    3. ``assets/<theme>/<name>``
    4. ``assets/<name>``

    ``declared_variants`` is the figure's declared ``(locale, theme)`` matrix
    (default: read from ``src/devtools/help_figures.json``). Fail-closed: a
    declared variant that is absent is a content bug, so the resolver returns
    ``None`` (the dialog's placeholder path) instead of silently showing the
    base image in the wrong language/theme. Falling back to the base image is
    only allowed when the manifest does not declare the requested variant.
    Without ``locale``/``theme`` this is exactly the old body-relative lookup.
    """
    if not body_file:
        return None
    # Canonicalise once: markdown paths carry ``../`` segments, and the variant
    # folders are built from the asset root (``assets/<locale>/<theme>/``), so a
    # ``..``-laden base would never compare equal to a real variant.
    base = (Path(body_file).parent / rel_path.lstrip("/")).resolve()
    if not locale or not theme:
        return base if base.is_file() else None
    language = normalize_help_language(locale)
    theme_name = theme.strip().lower()
    if not theme_name:
        return base if base.is_file() else None

    declared = (
        frozenset(declared_variants)
        if declared_variants is not None
        else _declared_variants_for(base)
    )
    declared_locales = {code for code, _ in declared}
    declared_themes = {name for _, name in declared}
    root = _help_assets_root(base)
    candidates = (
        (root / language / theme_name / base.name, (language, theme_name) in declared),
        (root / language / base.name, language in declared_locales),
        # A theme-only file serves every locale, so a locale x theme matrix
        # never declares it: ``declared_themes`` is a projection of the matrix,
        # and treating it as a theme-only declaration made an undeclared locale
        # (zh, which ships no figure variants yet) fail closed to a placeholder
        # instead of falling back to the base image.
        (root / theme_name / base.name, False),
    )
    for candidate, _declared_here in candidates:
        if candidate.is_file():
            return candidate
    missing = [path for path, declared_here in candidates if declared_here]
    if missing:
        logger.warning(
            "Help asset variant declared but missing: %s (locale=%s theme=%s)",
            ", ".join(str(path) for path in missing),
            language,
            theme_name,
        )
        return None
    return base if base.is_file() else None
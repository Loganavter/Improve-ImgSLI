"""G1 ratchet: no producer names a model — ``catalog`` is the only home.

``plan-gallery-analysis-engine-2026-10-20`` §Gates G1 / §Invariants I2: a
producer receives a ``BackendRef`` from the catalog and therefore cannot spell a
vendor model id. Today each network path carries its own constant
(``services/jev_client.py:54`` ``JEV_MODEL``) while the endpoint comes from the
user's settings — the mismatch behind defect B1. This gate keeps a new literal
from appearing in a second place: the single home is
``src/engine/analysis/catalog.py``, everything else must be reasoned into
``MODEL_LITERAL_ALLOWLIST`` and removed by its wave.

The scanner is AST-only (a string ``ast.Constant`` anywhere in ``src/``), so a
literal in a docstring-free code path, a dict value or a keyword argument is all
caught the same way. False positives are the interesting half and are pinned by
explicit tests below:

* MIME types (``image/png``) are content types, not vendors;
* URLs (``https://host/v1``) are endpoints, not ids, and never survive the
  one-slash rule anyway;
* multi-segment relative paths (``src/tabs/x.py``) are paths — the one-slash
  rule plus the namespace rule below keeps single-segment resource paths
  (``resources/help``) and dispatcher action ids (``multi_compare/add_slot``)
  out as well;
* whitespace, ``n/a``-style placeholders, filename suffixes and a digit-only
  right side are not model names.

A slash-joined pair whose left segment names a directory in this repo is a path
or a namespaced key, never a vendor id: no vendor is a directory here, and that
rule is what keeps the whole ``multi_compare/<action>`` action vocabulary and
``resources/<thing>`` paths out of the allowlist instead of drowning it.

Known limit, stated rather than hidden: the plan's shape is ``vendor/model``, so
a bare id with no vendor prefix (``ai_providers.py``'s OpenAI preset carries
``"gpt-6-luna"`` without a slash) is outside this gate. The catalog becomes the
only home for those too in W5; this gate covers the prefixed form.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache

import pytest

from ._framework import SRC, iter_py, rel
from .analysis_gates_allowlist import (
    assert_ratchet,
    add_hit,
    make_key,
    source_line,
)

PLAN = "plan-gallery-analysis-engine-2026-10-20"

#: The one module allowed to name a model identity (plan §Target architecture:
#: ``catalog.py`` = provider/model resolution + validation).
CATALOG = "src/engine/analysis/catalog.py"

#: Exactly one slash, both sides ``[a-z0-9][a-z0-9._-]*`` — the shape of an
#: OpenRouter-style ``vendor/model`` id.
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")

#: Content types (``_EXT_TO_MIME`` in ``ai_client/request.py`` feeds these).
MIME_PREFIXES = ("image/", "audio/", "video/", "text/", "application/")

#: Display placeholders that happen to fit the shape.
PLACEHOLDER_TOKENS = frozenset({"n/a"})

#: A right side ending in a source/resource suffix names a file, not a model.
FILE_SUFFIXES = (
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".ico",
    ".qss",
    ".css",
    ".html",
    ".glsl",
    ".vert",
    ".frag",
)

#: Current real hits, derived by running the scanner (never guessed).
#: Shrink-only: W5 moves every model identity into ``catalog.py`` and P9 deletes
#: the per-path constant, so each entry below must disappear with its wave.
MODEL_LITERAL_ALLOWLIST: dict[str, str] = {
    "src/tabs/image_gallery/services/jev_client.py|JEV_MODEL = \"typesafe/jev-router\"": (
        "the per-path constant behind defect B1 (JEV_MODEL while the endpoint is "
        "the user's) — W5 replaces it with a catalog-resolved BackendRef; P9 "
        "deletes JEV_MODEL (plan §Phases P5/P9)"
    ),
    "src/tabs/image_gallery/services/ai_client/request.py|\"z-ai/glm-5.3-flash\",": (
        "DEFAULT_FALLBACK_MODELS entry — W5 moves the OpenRouter fallback chain "
        "into the catalog (`ProviderPreset.models`), so no request path names an "
        "id (plan §Invariants I2)"
    ),
    "src/tabs/image_gallery/services/ai_client/request.py|\"openai/gpt-6-luna\",": (
        "DEFAULT_FALLBACK_MODELS entry — same W5 move into the catalog as its "
        "sibling above (plan §Phases P4/P5)"
    ),
    (
        "src/tabs/image_gallery/services/ai_providers.py|"
        "curated_models=(\"openrouter/auto\", \"z-ai/glm-5.3-flash\", "
        "\"openai/gpt-6-luna\"),"
    ): (
        "the settings provider preset's curated list — W5 makes `catalog.py` the "
        "only home (`ProviderPreset.models`), leaving this preset to reference it"
    ),
    "src/tabs/image_gallery/services/ai_providers.py|default_model=\"openrouter/auto\",": (
        "default model of the OpenRouter preset — resolved through the catalog "
        "in W5; until then it is the same identity as the curated list"
    ),
    "src/tabs/image_compare/presenters/image_canvas/background_parts/use_cases/geometry.py|else \"sources/previews\",": (
        "NOT a model id: right side is the preview-source namespace key "
        "(`sources/previews`), left side is a data namespace rather than a repo "
        "directory, so the shape rule cannot separate it — allowlisted as a "
        "false positive of the vendor/model shape; no wave, it is not a violation"
    ),
    "src/ui/widgets/color/recents.py|_SETTINGS_KEY = \"color_picker/recents\"": (
        "NOT a model id: a QSettings key namespace (`color_picker/recents`) whose "
        "left segment is not a directory, so the shape rule cannot separate it — "
        "allowlisted as a false positive; no wave, it is not a violation"
    ),
}


@lru_cache(maxsize=1)
def _path_namespaces() -> frozenset[str]:
    """Directory names of this repo (plus the repo-root ones).

    A slash-joined pair whose left segment is a directory is a path or a
    namespaced key. Computing it from the tree instead of hardcoding a list
    means a new tab (``multi_compare``'s action ids) or resource directory does
    not need an allowlist entry to stay clean.
    """
    names = {p.name for p in SRC.rglob("*") if p.is_dir()}
    names.update({"src", "tests", "docs", "scripts"})
    return frozenset(names)


def looks_like_model_id(text: str, namespaces: frozenset[str]) -> bool:
    """True for a ``vendor/model`` string that is not a known non-id shape."""
    if not text or any(ch.isspace() for ch in text):
        return False
    if text in PLACEHOLDER_TOKENS:
        return False
    if text.startswith(MIME_PREFIXES):
        return False
    # A URL has a scheme separator; anything with more than one slash is a
    # multi-segment relative path (``src/tabs/x.py``), not a two-part id.
    if "://" in text or text.count("/") != 1:
        return False
    left, right = text.split("/")
    if not MODEL_ID_RE.match(text):
        return False
    if left in namespaces:
        return False
    if right.isdigit():
        # ``imgsli-app-snapshot/1`` — a schema id versioned by an integer.
        return False
    return not right.endswith(FILE_SUFFIXES)


def find_model_literal_hits(
    sources: dict[str, str],
    *,
    namespaces: frozenset[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """``path|line`` -> occurrences for every vendor/model literal in *sources*."""
    names = _path_namespaces() if namespaces is None else namespaces
    hits: dict[str, tuple[str, ...]] = {}
    for path in sorted(sources):
        if path == CATALOG:
            continue
        source = sources[path]
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and looks_like_model_id(node.value, names)
            ):
                add_hit(
                    hits,
                    path=path,
                    lineno=node.lineno,
                    line=source_line(source, node.lineno),
                )
    return hits


def _src_sources() -> dict[str, str]:
    return {rel(p): p.read_text(encoding="utf-8") for p in iter_py(SRC)}


# ---------------------------------------------------------------------------
# real tree
# ---------------------------------------------------------------------------


def test_no_vendor_model_literals_outside_the_catalog():
    assert_ratchet(
        f"G1 model literals ({PLAN})",
        MODEL_LITERAL_ALLOWLIST,
        find_model_literal_hits(_src_sources()),
    )


# ---------------------------------------------------------------------------
# false-positive / true-positive classification (pure predicate + scanner)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "image/png",
        "audio/wav",
        "video/mp4",
        "text/plain",
        "application/json",
    ],
)
def test_mime_types_are_not_model_ids(text):
    assert not looks_like_model_id(text, _path_namespaces())


@pytest.mark.parametrize(
    "text",
    [
        "src/tabs/image_gallery/services/jev_client.py",
        "resources/help",
        "resources/i18n",
        "canvas/features",
        "use_cases/ai_analysis.py",
        "multi_compare/add_slot",
        "image_gallery.domain.ai",
    ],
)
def test_paths_and_namespaces_are_not_model_ids(text):
    assert not looks_like_model_id(text, _path_namespaces())


@pytest.mark.parametrize(
    "text",
    [
        "https://openrouter.ai/api/v1",
        "https://example.com/a/b",
        "vendor /model",
        "n/a",
        "imgsli-app-snapshot/1",
        "",
        "no-slash-at-all",
        "UPPER/Model",
    ],
)
def test_urls_whitespace_placeholders_and_versions_are_not_model_ids(text):
    assert not looks_like_model_id(text, _path_namespaces())


@pytest.mark.parametrize(
    "text",
    [
        "typesafe/jev-router",
        "openrouter/auto",
        "openai/gpt-6-luna",
        "z-ai/glm-5.3-flash",
        "vendor/vision_2",
    ],
)
def test_vendor_model_ids_are_flagged(text):
    assert looks_like_model_id(text, _path_namespaces())


def test_scanner_flags_a_fresh_model_literal():
    src = (
        "def run(ctx):\n"
        '    model = "typesafe/jev-router"\n'
        "    return model\n"
    )
    hits = find_model_literal_hits(
        {"src/tabs/image_gallery/analysis/producers/rank/producer.py": src}
    )
    assert list(hits) == [
        make_key(
            "src/tabs/image_gallery/analysis/producers/rank/producer.py",
            'model = "typesafe/jev-router"',
        )
    ]


def test_scanner_ignores_the_catalog_and_noise():
    model = 'PRESET = ("openrouter/auto",)\n'
    noise = (
        'MIME = "image/png"\n'
        'HELP = "resources/help"\n'
        'ACTION = "multi_compare/add_slot"\n'
        'SCHEMA = "imgsli-app-snapshot/1"\n'
        'EMPTY = "n/a"\n'
    )
    # The catalog is the designated home: its literals are exempt.
    assert find_model_literal_hits({CATALOG: model}) == {}
    # Every non-id shape is clean outside it too...
    assert find_model_literal_hits({"src/tabs/image_gallery/ui/help.py": noise}) == {}
    # ...but the same literal outside the catalog is a violation.
    assert list(find_model_literal_hits({"src/tabs/image_gallery/ui/help.py": model}))


def test_namespaced_keys_that_look_like_ids_are_allowlisted_not_excluded():
    """``sources/previews`` / ``color_picker/recents`` are namespaces, not ids.

    Their left segment is not a directory, so the shape rule cannot separate
    them from a vendor id; they are reasoned allowlist entries instead of a
    silent exclusion, so a reviewer sees exactly which strings got a pass.
    """
    src = 'A = "sources/previews"\nB = "color_picker/recents"\n'
    hits = find_model_literal_hits({"src/x.py": src})
    assert set(hits) == {
        make_key("src/x.py", 'A = "sources/previews"'),
        make_key("src/x.py", 'B = "color_picker/recents"'),
    }


def test_allowlist_entries_all_actually_hit_today():
    """A stale entry (fixed code) must fail — proved on the real allowlist."""
    if not MODEL_LITERAL_ALLOWLIST:
        pytest.skip("no grandfathered model literals on this tree")
    with pytest.raises(AssertionError, match="STALE"):
        assert_ratchet(
            "G1 probe (an empty scan must report every entry as stale)",
            MODEL_LITERAL_ALLOWLIST,
            {},
        )

"""G5 ratchet: gallery UI reads ``AxisValue`` records, never the raw dicts.

``plan-gallery-analysis-engine-2026-10-20`` §Gates G5 (``test_analysis_no_direct
_reads``) / §Invariant I6 ("One read path"): after P2 a surface renders an
``AxisValue`` whose producer/backend/status travel with the value; nobody in
``ui/`` reaches into ``item.metrics`` — the raw detector dict — because that is
how "whose number is this" becomes unanswerable (defect B6).

Both spellings are the same read and both are scanned:

* attribute access — ``item.metrics`` (``ast.Attribute``, load context);
* the ``getattr(item, "metrics", None)`` string form the gallery UI actually
  uses today (grep-proof is not the point; the raw dict is).

Name-prefix variants are NOT this dict and are pinned clean by tests:
``.metrics_rows``, ``.metrics_cache``, ``.metrics_fingerprint``, ``._metrics``
and ``.metrics_ready`` are row caches / fingerprints / flags, not the detector
dict. A subscript (``report["metrics"]``) is a plain dict lookup on some other
report, not an item attribute, and is likewise clean.

Every allowlisted reader is a W3 (read-path) entry: ``AxisReader`` replaces it
in the same wave that deletes the domain-wide read swap.
"""

from __future__ import annotations

import ast

import pytest

from ._framework import SRC, rel
from .analysis_gates_allowlist import (
    assert_ratchet,
    add_hit,
    make_key,
    source_line,
)

PLAN = "plan-gallery-analysis-engine-2026-10-20"

#: Gate scope: surfaces live here (``services/**`` is the adapter's business).
GALLERY = SRC / "tabs" / "image_gallery"
UI = GALLERY / "ui"

#: The raw detector dict's attribute name.
RAW_METRICS = "metrics"

#: Current raw-dict readers in ``ui/`` (derived by running the scanner).
#: Shrink-only: W3's ``AxisReader`` replaces every one of them.
RAW_METRIC_READ_ALLOWLIST: dict[str, str] = {
    "src/tabs/image_gallery/ui/quick_look/headers.py|metrics = getattr(item, \"metrics\", None)": (
        "quick-look header reads width/height out of the raw metrics dict — W3 "
        "reads the dimension facts from the AnalysisContext/AxisReader"
    ),
    "src/tabs/image_gallery/ui/quick_look/meta.py|metrics_pre = getattr(item, \"metrics\", None)": (
        "meta line caches dims from the raw dict (48/57) — W3 reads them from the "
        "context, not the detector dict"
    ),
    "src/tabs/image_gallery/ui/quick_look/meta.py|metrics = getattr(item, \"metrics\", None) or {}": (
        "meta line reads upscale_factor from the raw dict (67) — W3 AxisReader"
    ),
    "src/tabs/image_gallery/ui/quick_look/meta.py|ma = getattr(item, \"metrics\", None) or {}": (
        "side-by-side meta compares two raw dicts (205/206) — W3 compares "
        "AxisValues so provenance travels with the numbers"
    ),
    "src/tabs/image_gallery/ui/quick_look/meta.py|mb = getattr(other, \"metrics\", None) or {}": (
        "the second half of the side-by-side comparison (206) — W3 AxisReader"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/cache.py|metrics = getattr(item, \"metrics\", None) or {}": (
        "metrics row cache keys off the raw dict (129) — W3 keys off the "
        "AnalysisRecord generation/plan id"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/cache.py|mt = getattr(m, \"metrics\", None) or {}": (
        "warm/compare pass fingerprints raw dicts (103) — W3 fingerprint of the "
        "record instead"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/rows.py|metrics = getattr(item, \"metrics\", None) or {}": (
        "row builder reads the raw dict as a fallback beside quality_read (284) "
        "— W3 drops the fallback: a gap renders as a gap"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/rows.py|mt = getattr(m, \"metrics\", None) or {}": (
        "series/compare rows read raw dicts (603) — W3 AxisReader per item"
    ),
    "src/tabs/image_gallery/ui/quick_look/preview.py|metrics = getattr(src_item, \"metrics\", None) if src_item is not None else None": (
        "preview reads orientation/upscale hints from the raw dict (368) — W3 "
        "reads the context"
    ),
    "src/tabs/image_gallery/ui/quick_look_hooks.py|m = getattr(it, \"metrics\", None)": (
        "quick-look settle hook scans raw dicts (481) — W3 makes the settle "
        "level-triggered on the record"
    ),
    "src/tabs/image_gallery/ui/widget_parts/view_prefs.py|metrics = getattr(it, \"metrics\", None)": (
        "view restore reads embedding_dist_to_centroid from the raw dict (126) "
        "— W3 reads that axis as an AxisValue"
    ),
}


def _getattr_string(node: ast.Call) -> str | None:
    """The name in ``getattr(obj, "<name>"[, default])``, else ``None``."""
    if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
        return None
    if len(node.args) < 2:
        return None
    name = node.args[1]
    if isinstance(name, ast.Constant) and isinstance(name.value, str):
        return name.value
    return None


def find_raw_metric_read_hits(
    sources: dict[str, str],
) -> dict[str, tuple[str, ...]]:
    """``path|line`` -> occurrences for every ``item.metrics`` read in *sources*."""
    hits: dict[str, tuple[str, ...]] = {}
    for path in sorted(sources):
        source = sources[path]
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            note = ""
            if (
                isinstance(node, ast.Attribute)
                and node.attr == RAW_METRICS
                and isinstance(node.ctx, ast.Load)
            ):
                note = "attribute read .metrics"
            elif isinstance(node, ast.Call) and _getattr_string(node) == RAW_METRICS:
                note = 'getattr string read "metrics"'
            if note:
                add_hit(
                    hits,
                    path=path,
                    lineno=node.lineno,
                    line=source_line(source, node.lineno),
                    note=note,
                )
    return hits


def _ui_sources() -> dict[str, str]:
    return {
        rel(p): p.read_text(encoding="utf-8")
        for p in sorted(UI.rglob("*.py"))
        if "__pycache__" not in p.parts and "tests" not in p.parts
    }


# ---------------------------------------------------------------------------
# real tree
# ---------------------------------------------------------------------------


def test_ui_reads_no_raw_metric_dicts():
    assert_ratchet(
        f"G5 raw metric-dict reads in ui/ ({PLAN})",
        RAW_METRIC_READ_ALLOWLIST,
        find_raw_metric_read_hits(_ui_sources()),
    )


# ---------------------------------------------------------------------------
# falsifiability: both spellings are flagged, look-alikes are not
# ---------------------------------------------------------------------------


def test_scanner_flags_attribute_and_getattr_reads():
    src = (
        "def rows(item, other):\n"
        "    raw = item.metrics\n"
        '    alt = getattr(item, "metrics", None)\n'
        "    return raw, alt\n"
    )
    hits = find_raw_metric_read_hits({"src/tabs/image_gallery/ui/example.py": src})
    assert len(hits) == 2
    assert make_key(
        "src/tabs/image_gallery/ui/example.py", "raw = item.metrics"
    ) in hits
    assert make_key(
        "src/tabs/image_gallery/ui/example.py",
        'alt = getattr(item, "metrics", None)',
    ) in hits


def test_scanner_ignores_look_alike_names():
    src = (
        "def rows(self, item, report):\n"
        "    a = self._metrics\n"
        "    b = item.metrics_rows\n"
        "    c = item.metrics_cache\n"
        "    d = item.metrics_fingerprint\n"
        "    e = item.metrics_ready\n"
        "    f = report[\"metrics\"]\n"
        '    g = getattr(item, "metrics_rows", None)\n'
        '    item.metrics = None\n'
        "    return a, b, c, d, e, f, g\n"
    )
    assert find_raw_metric_read_hits({"src/tabs/image_gallery/ui/example.py": src}) == {}


def test_allowlist_is_shrink_only():
    """An entry whose reader was migrated to ``AxisReader`` must fail."""
    if not RAW_METRIC_READ_ALLOWLIST:
        pytest.skip("no raw metric readers left in ui/")
    with pytest.raises(AssertionError, match="STALE"):
        assert_ratchet("G5 probe (empty scan)", RAW_METRIC_READ_ALLOWLIST, {})

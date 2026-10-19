"""L6 gate: a LIVE-APPEARANCE test must drain the coalesced metrics bus first.

``connect_ui_metrics`` folds ``UiFont.font_changed`` and ``UiScale.scale_changed``
into ONE ``UiMetrics.changed`` emission scheduled on a zero-timer (see the
toolkit ``ui_metrics`` module). Nothing happens inside ``set_factor`` /
``set_family`` / ``FontManager.apply_from_state``; the consumer slots run on a
later event-loop turn. A test that moves a metric and then immediately reads
widget geometry or label metrics therefore reads PRE-FLUSH state: it can be
falsely red (the old geometry) or — worse — falsely green if its expected value
is the stale one.

**Predicate (kept deliberately conservative).** A test is a *live-appearance
assertion* when a single ``test_*`` function does both, in source order:

1. **triggers the coalesced metrics path** — a call that subscribes a live
   widget to the bus (``connect_ui_metrics``), notifies the bus
   (``emit_appearance`` / ``begin_appearance`` / ``end_appearance``), or moves a
   metric source (``UiScale.set_factor`` / ``set_scale`` / ``set_ui_scale``,
   ``UiFont.set_family``, ``FontManager.apply_from_state``); and then
2. **asserts widget geometry or label metrics** — an ``assert`` whose tested
   expression reads a geometry/layout attribute (``width``, ``height``,
   ``size``, ``sizeHint``, ``minimumSize``, ``geometry``, ``rect``, ``pos``,
   ``spacing``, ``margins``, ``contentsRect``, …), a text metric
   (``pixelSize``, ``pointSize``, ``fontMetrics``, ``lineSpacing``,
   ``boundingRect``), or calls a label/text measurement helper
   (``_label_size``, ``text_width``, …).

Between the triggering event and the first such assertion there must be a
**drain**: ``drain_until_stable`` (``tests/helpers/drain_until_stable.py``, the
documented entry point — it spins real event-loop turns, unlike a bare
``processEvents()``), or another call recognisable as a drain. Not recognised
as drains: ``qapp.processEvents()`` and fixed ``qtbot.wait()`` sleeps (the
helper's own docstring records that a ``processEvents``-only drain can return
before the zero-timer fires). Recognised equivalents: any call whose name says
``drain``/``spin`` (``_drain``, ``_spin_until_changed``,
``_drain_metrics_channel``), a ``…flush…metrics`` / ``wait_for_ui_metrics``
name, and any module-local helper whose body actually spins a ``QEventLoop`` or
calls one of those (``_settle`` in ``test_color_picker_scale.py``).

Anything the static predicate cannot separate from a real trap is recorded in
``tests/contracts/drain_guard_allowlist.py`` with a reason. The allowlist is a
ratchet: entries must name a real file/test and must still suppress a finding,
otherwise the gate fails and the entry has to be removed.

**Falsification** (asserted below, not just described): a synthetic source that
triggers the path and asserts geometry without draining is flagged and the
offender is named; the same source with a ``drain_until_stable`` call between
the trigger and the assertion passes. A third control pins conservatism: a
trigger with no geometry/label assertion afterwards is not a finding.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from tests.contracts._framework import ROOT, SRC, parse, rel
from tests.contracts.drain_guard_allowlist import ALLOWLIST

#: Corpus: host test tree plus every tab's own tests (``src/tabs/<tab>/tests``).
SCAN_ROOTS: tuple[Path, ...] = (ROOT / "tests",) + tuple(
    sorted((SRC / "tabs").glob("*/tests"))
)

#: This module carries the synthetic sources used as falsification probes; it
#: drives no widgets and must not be scanned as corpus.
_SELF = Path(__file__).resolve()

#: Call names that move/subscribe the coalesced appearance channel. Restricted
#: names (``set_factor`` etc.) are additionally checked against the receiver so
#: an unrelated ``render_config.set_factor`` is not mistaken for ``UiScale``.
_TRIGGER_NAMES = {
    "connect_ui_metrics",
    "emit_appearance",
    "begin_appearance",
    "end_appearance",
    "set_scale",
    "set_ui_scale",
}
_RECEIVER_RESTRICTED_TRIGGERS = {
    "set_factor": ("uiscale", "ui_scale"),
    "set_family": ("uifont", "ui_font"),
    "apply_from_state": ("fontmanager", "font_manager"),
}

#: Geometry / label-metric reads that make an ``assert`` a live-appearance read.
_GEOMETRY_ATTRS = frozenset(
    {
        "width",
        "height",
        "size",
        "sizeHint",
        "minimumSize",
        "maximumSize",
        "minimumWidth",
        "minimumHeight",
        "maximumWidth",
        "maximumHeight",
        "geometry",
        "rect",
        "x",
        "y",
        "pos",
        "frameGeometry",
        "contentsRect",
        "spacing",
        "margins",
        "contentsMargins",
        "pixelSize",
        "pointSize",
        "pointSizeF",
        "fontMetrics",
        "lineSpacing",
        "boundingRect",
        "horizontalAdvance",
        "advance",
    }
)

#: Measurement helpers that hide the attribute read behind a function name
#: (``_label_size(label)`` is still a label-metric assertion).
_LABEL_METRIC_HELPER = re.compile(
    r"^(label|text|font)[_a-z]*(size|width|height|metric|advance)", re.IGNORECASE
)

#: Exact drain entry points; the rest of the drain surface is name/body based.
_DRAIN_EXACT = frozenset(
    {
        "drain_until_stable",
        "drain_ui_metrics",
        "drain_appearance",
        "drain_metrics_channel",
        "flush_ui_metrics",
        "wait_for_ui_metrics",
        "wait_for_metrics_flush",
    }
)

_METRIC_FLUSH = re.compile(r"(flush|wait).*metrics|metrics.*flush", re.IGNORECASE)


@dataclass(frozen=True)
class LiveAppearanceAssertion:
    """One detected live-appearance test (drained or not)."""

    path: str
    test: str
    trigger_line: int
    assert_line: int
    drained: bool

    def offender_line(self) -> str:
        return (
            f"{self.path}::{self.test} "
            f"(trigger at line {self.trigger_line}, first geometry/label "
            f"assert at line {self.assert_line})"
        )


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _receiver_root(node: ast.AST) -> str:
    """Leftmost name of a call chain: ``UiScale.get_instance().set_factor`` → ``UiScale``."""
    while isinstance(node, (ast.Attribute, ast.Call)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return getattr(node, "id", "") or ""


def _is_trigger(node: ast.Call) -> bool:
    name = _call_name(node)
    if name in _TRIGGER_NAMES:
        return True
    prefixes = _RECEIVER_RESTRICTED_TRIGGERS.get(name)
    if prefixes is None:
        return False
    root = _receiver_root(node.func).lower().replace("_", "")
    return any(prefix.replace("_", "") in root for prefix in prefixes)


def _is_drain_name(name: str) -> bool:
    plain = name.lstrip("_").lower()
    if plain in _DRAIN_EXACT:
        return True
    if "drain" in plain or "spin" in plain:
        return True
    return bool(_METRIC_FLUSH.search(plain))


def _spins_event_loop(fn: ast.AST) -> bool:
    """True when *fn*'s body actually drains the loop (not a bare processEvents)."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            if _is_drain_name(_call_name(node)):
                return True
            if getattr(node.func, "attr", "") in {"exec", "exec_"}:
                return True
        elif isinstance(node, ast.Name) and node.id == "QEventLoop":
            return True
        elif isinstance(node, ast.Attribute) and node.attr == "QEventLoop":
            return True
    return False


def _module_drain_names(tree: ast.Module) -> set[str]:
    """Module-local helpers that are equivalent drain entry points."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_") and _spins_event_loop(node):
                names.add(node.name)
    return names


def _asserts_geometry_or_label_metrics(node: ast.Assert) -> bool:
    for sub in ast.walk(node.test):
        if isinstance(sub, ast.Attribute) and sub.attr in _GEOMETRY_ATTRS:
            return True
        if isinstance(sub, ast.Call):
            name = _call_name(sub).lstrip("_")
            if _LABEL_METRIC_HELPER.match(name):
                return True
    return False


def _scan_tree(tree: ast.Module, path: str) -> list[LiveAppearanceAssertion]:
    """Find live-appearance assertions in every ``test_*`` function of *tree*.

    An undrained assertion is reported once per trigger segment; a drained
    assertion is still recorded so callers can prove the predicate fired (the
    exemplar positive control) rather than degenerated to "nothing detected".
    """
    drain_names = _module_drain_names(tree)
    findings: list[LiveAppearanceAssertion] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not fn.name.startswith("test_"):
            continue

        events: list[tuple[tuple[int, int], str, object]] = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                if _is_trigger(node):
                    events.append(((node.lineno, node.col_offset), "trigger", node))
                elif name in drain_names or _is_drain_name(name):
                    events.append(((node.lineno, node.col_offset), "drain", node))
            elif isinstance(node, ast.Assert):
                if _asserts_geometry_or_label_metrics(node):
                    events.append(((node.lineno, node.col_offset), "assert", node))
        events.sort(key=lambda item: item[0])

        trigger_line: int | None = None
        drained_since_trigger = False
        segment_finding_reported = False
        for _pos, kind, node in events:
            if kind == "trigger":
                trigger_line = node.lineno
                drained_since_trigger = False
                segment_finding_reported = False
            elif kind == "drain":
                drained_since_trigger = True
            elif kind == "assert" and trigger_line is not None:
                if drained_since_trigger:
                    findings.append(
                        LiveAppearanceAssertion(
                            path=path,
                            test=fn.name,
                            trigger_line=trigger_line,
                            assert_line=node.lineno,
                            drained=True,
                        )
                    )
                elif not segment_finding_reported:
                    findings.append(
                        LiveAppearanceAssertion(
                            path=path,
                            test=fn.name,
                            trigger_line=trigger_line,
                            assert_line=node.lineno,
                            drained=False,
                        )
                    )
                    segment_finding_reported = True
    return findings


def scan_source(source: str, path: str = "<synthetic>") -> list[LiveAppearanceAssertion]:
    """Scan one source string (used by the falsification tests below)."""
    return _scan_tree(ast.parse(source), path)


def iter_corpus_files(roots: tuple[Path, ...] = SCAN_ROOTS):
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or path.resolve() == _SELF:
                continue
            yield path


def scan_corpus(roots: tuple[Path, ...] = SCAN_ROOTS) -> list[LiveAppearanceAssertion]:
    findings: list[LiveAppearanceAssertion] = []
    for path in iter_corpus_files(roots):
        tree = parse(path)
        if tree is None:
            continue
        findings.extend(_scan_tree(tree, rel(path)))
    return findings


def _allowlisted(path: str, test: str) -> bool:
    return path in ALLOWLIST or f"{path}::{test}" in ALLOWLIST


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_live_appearance_tests_drain_before_asserting():
    offenders = [f for f in scan_corpus() if not f.drained]
    unexplained = [f for f in offenders if not _allowlisted(f.path, f.test)]

    assert not unexplained, (
        "A live-appearance test must drain the coalesced metrics channel before "
        "asserting widget geometry/label metrics. connect_ui_metrics schedules "
        "UiMetrics.changed on a zero-timer, so a scale/font change is not "
        "visible yet at the next statement: an undrained assert reads the "
        "pre-flush value (falsely red) or a stale expected value (falsely "
        "green). Fix: call drain_until_stable(qapp, <getter>) between the "
        "change and the assertion (tests/helpers/drain_until_stable.py). "
        "Undrained live-appearance assertions:\n"
        + "\n".join(f"  {f.offender_line()}" for f in unexplained)
        + "\n\nIf the test legitimately reads pre-flush/build-time state, add "
        "the entry to tests/contracts/drain_guard_allowlist.py with a reason."
    )


def test_known_drained_exemplar_is_detected():
    """Positive control: the predicate fires on the canonical drained test.

    Without this, the gate could silently degenerate to "no test detected"
    after a rename and stay green forever.
    """
    exemplar = "tests/plugins/test_export_dialog_labels_scale.py::test_export_dialog_labels_scale_live"
    findings = [
        f
        for f in scan_corpus()
        if f"{f.path}::{f.test}" == exemplar
    ]
    assert findings, (
        f"the live-appearance predicate no longer detects {exemplar} — the "
        "trigger/assert detection regressed and the gate is vacuous"
    )
    assert any(f.drained for f in findings), (
        f"{exemplar} is expected to drain before its live geometry assertion"
    )


def test_allowlist_entries_are_documented_and_current():
    """Every entry names a real file/test, carries a reason, and is still used."""
    problems: list[str] = []
    offenders = {(f.path, f.test) for f in scan_corpus() if not f.drained}

    for entry, reason in ALLOWLIST.items():
        if not reason.strip() or len(reason.strip()) < 20:
            problems.append(f"{entry}: missing a substantive one-line reason")
        elif "TODO" in reason or "FIXME" in reason:
            problems.append(f"{entry}: reason is a placeholder")
        if "::" in entry:
            path_text, test_name = entry.split("::", 1)
        else:
            path_text, test_name = entry, None

        path = ROOT / path_text
        tree = parse(path) if path.is_file() else None
        if tree is None:
            problems.append(f"{entry}: no such file under the repository root")
            continue
        if test_name is not None:
            names = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if test_name not in names:
                problems.append(f"{entry}: no test function named {test_name!r} in the file")

        still_needed = any(
            path_text == offender_path
            and (test_name is None or test_name == test)
            for offender_path, test in offenders
        )
        if not still_needed:
            problems.append(
                f"{entry}: stale entry — it no longer suppresses any undrained "
                "live-appearance assertion; remove it"
            )

    assert not problems, "Allowlist problems:\n" + "\n".join(
        f"  {item}" for item in problems
    )


# ---------------------------------------------------------------------------
# Falsification / controls
# ---------------------------------------------------------------------------

_UNDRAINED_SOURCE = '''
from PySide6.QtWidgets import QApplication
from sli_ui_toolkit.managers import UiScale


def build_label():
    return None


def test_scale_then_read_without_drain(qapp: QApplication):
    label = build_label()
    UiScale.get_instance().set_factor(1.5)
    assert label.width() == 27
'''


def test_synthetic_undrained_source_is_flagged():
    findings = scan_source(_UNDRAINED_SOURCE, path="tests/synthetic_undrained.py")

    assert findings, (
        "the predicate failed to flag a source that changes the UI scale and "
        "immediately asserts widget geometry — the gate cannot catch the L6 trap"
    )
    undrained = [f for f in findings if not f.drained]
    assert undrained, "the undrained source was classified as drained"
    offender = undrained[0]
    message = offender.offender_line()
    assert offender.test == "test_scale_then_read_without_drain"
    assert offender.assert_line > offender.trigger_line
    assert "tests/synthetic_undrained.py" in message, message
    assert "test_scale_then_read_without_drain" in message, message
    assert f"assert at line {offender.assert_line}" in message, message


def test_synthetic_drained_source_passes():
    drained_source = _UNDRAINED_SOURCE.replace(
        "    UiScale.get_instance().set_factor(1.5)\n",
        "    UiScale.get_instance().set_factor(1.5)\n"
        "    drain_until_stable(qapp, lambda: label.width())\n",
    )
    findings = scan_source(drained_source, path="tests/synthetic_drained.py")

    assert findings, "the drained control source was not recognised at all"
    assert all(f.drained for f in findings), (
        "a drain call between the trigger and the geometry assertion must "
        f"clear the finding; got {[f.offender_line() for f in findings if not f.drained]}"
    )


def test_trigger_without_geometry_assertion_is_not_flagged():
    """Conservatism control: the predicate needs BOTH halves."""
    source = '''
from sli_ui_toolkit.managers import UiScale


def test_scale_changes_recorded_state_only(qapp, journal):
    UiScale.get_instance().set_factor(1.5)
    assert journal.recorded == []
'''
    assert scan_source(source, path="tests/synthetic_model.py") == []

"""GA1 contract: a rank dispatch never covers a subset without saying so.

``plan-gallery-ai-judgement-2026-10-21`` §Gates GA1 / §Invariants M2
("complete": no variant enters the order without its own reading; a series that
cannot be completed is shown as *partial*, not as an order) and the verified
defects it encodes:

* **J1/J7** — the Jev readiness loop treats "at least 2 scored members" as
  ready (``controller.py:1247-1252``: ``_jev_scored_count(vector) < 2``) and
  then hands the WHOLE series to ``_launch_jev_batch`` (``controller.py:1275``,
  body at ``1338``). A 6-variant folder whose last card had no scores was
  applied as an authoritative ``1..N`` order in the 2026-10-21 live run.
* The two halves are one gate on purpose. The behaviour half proves a real
  partial vector reaches the dispatch seam unmarked; the AST half proves the
  single place that may decide "complete vs partial" —
  ``rank_completeness(members, vector) -> (scored, total, reason)``, the
  declared P1 interface — is not consulted at all on that loop. Fixing one
  without the other would leave the other half red.

Red-before (``--runxfail``): the behaviour half records ``scored=2 total=6``
dispatched with no partial marker; the AST half finds no ``rank_completeness``
reference in ``_run_jev_ranks``.

The gate accepts EITHER repair the plan allows (P1): refuse the dispatch, or
dispatch with an explicit partial marker. It does not dictate the marker's
field name — any of the shapes the interface can take is recognised (see
``_documented_partial``), because the defect is the SILENT subset, not a
spelling.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from ._framework import ROOT, SRC, parse

GATE = "GA1"
PLAN = "plan-gallery-ai-judgement-2026-10-21"

GALLERY = SRC / "tabs" / "image_gallery"
CONTROLLER = GALLERY / "controller.py"

#: Members of the synthetic series (6) and how many carry scores (2) — the
#: live shape: the tail card analyzed after the rank had already been applied.
TOTAL_MEMBERS = 6
SCORED_MEMBERS = 2

_ALLOWLIST = Path(__file__).with_name("gallery_judge_allowlist.txt")

#: Name fragments that make a dispatch argument/state field a completeness
#: statement. Deliberately narrow: a rank payload carries ``scores``/``items``
#: (not ``scored``), so today's silent dispatch cannot match by accident.
_PARTIAL_NAME_TOKENS = (
    "partial",
    "incomplete",
    "completeness",
    "missing",
)

#: String fragments with the same meaning (a reason line like
#: ``"2 of 6 scored"`` is a marker too).
_PARTIAL_STRING_TOKENS = (
    "partial",
    "incomplete",
    "scored",
    "missing",
)


def _allowlisted(gate: str) -> bool:
    """True while *gate* still has a line in the shrink-only ledger.

    Kept inline in each of the four gate modules (the ledger is the only shared
    artifact): deleting the line is what re-arms the gate, so a phase cannot
    claim a fix without dropping its entry.
    """
    for raw in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        gate_id = raw.split("#", 1)[0].split("|", 1)[0].strip()
        if gate_id == gate:
            return True
    return False


def _allowlist_rows() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for raw in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        assert len(parts) == 3, (
            "allowlist rows are '<GATE> | <test node id> | <reason>': " f"{raw!r}"
        )
        rows.append((parts[0], parts[1], parts[2]))
    return rows


# ---------------------------------------------------------------------------
# marker recognition (shared by the gate and its falsifiability test)
# ---------------------------------------------------------------------------


def _names_and_strings(value, *, depth: int = 0) -> tuple[list[str], list[str]]:  # type: ignore[no-untyped-def]
    """Every attribute/key NAME and every string VALUE under *value*.

    Depth-capped and cycle-free by construction (only dict/list/tuple/set and
    plain ``__dict__`` objects are followed), so a controller double with a
    stage gate and a pool is cheap to scan.
    """
    names: list[str] = []
    strings: list[str] = []
    if depth > 6:
        return names, strings
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                names.append(key)
            sub_names, sub_strings = _names_and_strings(item, depth=depth + 1)
            names += sub_names
            strings += sub_strings
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            sub_names, sub_strings = _names_and_strings(item, depth=depth + 1)
            names += sub_names
            strings += sub_strings
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        try:
            fields = vars(value)
        except TypeError:
            fields = {}
        for key, item in fields.items():
            names.append(key)
            sub_names, sub_strings = _names_and_strings(item, depth=depth + 1)
            names += sub_names
            strings += sub_strings
    return names, strings


def _carries_completeness_triple(value, *, depth: int = 0) -> bool:  # type: ignore[no-untyped-def]
    """True when a ``rank_completeness`` result shape is present somewhere.

    The declared interface returns ``(scored, total, reason)``; a dispatch that
    carries that tuple (or a list of them) has stated its own completeness even
    if it names nothing "partial".
    """
    if depth > 5:
        return False
    if isinstance(value, (list, tuple)):
        if (
            len(value) == 3
            and isinstance(value[0], int)
            and isinstance(value[1], int)
            and isinstance(value[2], str)
            and value[2].strip()
            and value[0] < value[1]
        ):
            return True
        return any(_carries_completeness_triple(item, depth=depth + 1) for item in value)
    if isinstance(value, dict):
        return any(
            _carries_completeness_triple(item, depth=depth + 1) for item in value.values()
        )
    return False


def _documented_partial(args, kwargs, owner) -> bool:  # type: ignore[no-untyped-def]
    """Does this dispatch (or the owner's state) state its own incompleteness?

    Accepted shapes match the plan's P1 wording ("dispatch with an explicit
    ``partial`` reason that the UI shows") and the declared
    ``rank_completeness`` output: a partial/incomplete/missing/completeness
    named argument or state field, a reason string that says the series was not
    fully scored, or the ``(scored, total, reason)`` triple itself.
    """
    payload = [list(args), dict(kwargs)]
    names, strings = _names_and_strings(payload)
    owner_names, owner_strings = _names_and_strings(
        [getattr(owner, "state", None), owner]
    )
    names += owner_names
    strings += owner_strings
    if any(
        token in name.lower() for name in names for token in _PARTIAL_NAME_TOKENS
    ):
        return True
    if any(
        token in text.lower() for text in strings for token in _PARTIAL_STRING_TOKENS
    ):
        return True
    return _carries_completeness_triple(payload)


# ---------------------------------------------------------------------------
# AST half: the readiness loop must consult the one completeness authority
# ---------------------------------------------------------------------------


def _find_method(tree: ast.Module, class_name: str, method_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return child
    return None


def _readiness_loop_problems() -> list[str]:
    """Problems with the ``_run_jev_ranks`` → ``_launch_jev_batch`` seam."""
    tree = parse(CONTROLLER)
    if tree is None:
        return [f"{CONTROLLER.relative_to(ROOT).as_posix()} does not parse"]
    fn = _find_method(tree, "GalleryController", "_run_jev_ranks")
    if fn is None:
        return [
            "_run_jev_ranks is gone from GalleryController — move this gate's "
            "seam with it, never delete the gate"
        ]
    referenced = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
    referenced |= {
        node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)
    }
    if "rank_completeness" not in referenced:
        return [
            "_run_jev_ranks never consults rank_completeness(members, vector): the "
            "readiness loop still decides 'complete' from "
            "`_jev_scored_count(vector) < 2` (controller.py:1247-1252) and then "
            "dispatches the whole series"
        ]
    return []


# ---------------------------------------------------------------------------
# behaviour half: a 2-of-6 vector driven through the real readiness loop
# ---------------------------------------------------------------------------


def _series_of(six_members, scored: int):
    from tabs.image_gallery.models import AiAnalysisResult, GalleryItem, Series

    members = []
    for index in range(six_members):
        item = GalleryItem(path=Path(f"/gallery/judge_{index}.png"), mtime_ns=0)
        if index < scored:
            item.analysis = AiAnalysisResult(
                description="",
                tags=(),
                model="m",
                analyzed_at_iso="t",
                axes={"ssim": 90 - index * 40},
            )
        members.append(item)
    return Series(id="series_1", members=members)


def _judge_owner(series):
    from tabs.image_gallery.models import Mode
    from tabs.image_gallery.use_cases import pipeline_stages

    return SimpleNamespace(
        state=SimpleNamespace(
            series=[series],
            items=list(series.members),
            mode=Mode.FIDELITY,
            metric_profile=None,
        ),
        _judgment_domain="ai",
        _folder_gen=0,
        _stage_gate=pipeline_stages.StageGate(),
        _AI_VISIBLE_CAP=12,
        widget=SimpleNamespace(visible_paths=lambda: []),
    )


def _behaviour_problems(monkeypatch) -> list[str]:  # type: ignore[no-untyped-def]
    from tabs.image_gallery.controller import GalleryController

    series = _series_of(TOTAL_MEMBERS, SCORED_MEMBERS)
    owner = _judge_owner(series)

    dispatches: list[tuple[tuple, dict]] = []

    def _record(_owner, ready, *args, **kwargs):
        # The seam under test: nothing is launched, only the call is recorded.
        dispatches.append(((ready, *args), dict(kwargs)))

    monkeypatch.setattr(GalleryController, "_launch_jev_batch", _record)
    GalleryController._run_jev_ranks(owner)

    problems: list[str] = []
    for args, kwargs in dispatches:
        ready = args[0] if args else ()
        incomplete: list[tuple[int, int]] = []
        for entry in ready or ():
            try:
                members, vector = entry[0], entry[1]
            except (TypeError, IndexError, KeyError):
                continue  # a repaired shape; the AST half owns that contract
            scored = GalleryController._jev_scored_count(vector)
            total = len(list(members))
            if scored < total:
                incomplete.append((scored, total))
        if incomplete and not _documented_partial(args, kwargs, owner):
            problems.append(
                "dispatched a "
                + ", ".join(f"{scored}/{total} scored" for scored, total in incomplete)
                + " series with no partial marker on the dispatch (and none on "
                "the owner's state): a subset is applied as a full order"
            )
    return problems


@pytest.mark.xfail(
    condition=_allowlisted(GATE),
    reason=(
        "GA1 red-before (plan-gallery-ai-judgement-2026-10-21 §Gates GA1): the "
        "readiness loop ranks any series with >=2 scored members "
        "(controller.py:1247-1252 → :1275) so a 2-of-6 vector reaches "
        "_launch_jev_batch unmarked; rank_completeness() does not exist. P1 "
        "deletes this line."
    ),
    strict=True,
    raises=AssertionError,
)
def test_a_partial_series_is_never_dispatched_as_a_complete_rank(monkeypatch) -> None:
    problems = _behaviour_problems(monkeypatch) + _readiness_loop_problems()
    assert not problems, (
        "GA1 (M2 complete): a rank may only be applied from a vector covering "
        "every member of the series, or the series must be dispatched as "
        "partial with a reason the UI can show.\n" + "\n".join(problems)
    )


# ---------------------------------------------------------------------------
# falsifiability + ledger integrity (green on today's tree, by design)
# ---------------------------------------------------------------------------


def test_the_marker_vocabulary_rejects_a_silent_subset() -> None:
    """The gate above is only meaningful if this predicate can say "no"."""
    vector = {"mode": "fidelity", "items": [{"alias": "img_1", "scores": {"ssim": 90}}]}
    silent = ([[(SimpleNamespace(id="s"), vector)]],)
    assert not _documented_partial(silent[0], {}, SimpleNamespace(state=None))
    # Every declared repair is recognised.
    assert _documented_partial([], {"partial_reason": "4 members unscored"}, SimpleNamespace())
    assert _documented_partial([[("2 of 6 scored",)]], {}, SimpleNamespace())
    assert _documented_partial([[(2, 6, "4 members carry no score")]], {}, SimpleNamespace())
    assert _documented_partial(
        [], {}, SimpleNamespace(state=SimpleNamespace(rank_partial="2 of 6"))
    )
    # A complete series needs no marker, and an empty reason is not a statement.
    assert not _documented_partial([[(6, 6, "")]], {}, SimpleNamespace())


def test_the_ledger_names_exactly_the_declared_gates() -> None:
    rows = _allowlist_rows()
    gates = [gate for gate, _node, _reason in rows]
    assert sorted(gates) == ["GA1", "GA3", "GA4", "GA5"], (
        "the ledger must carry exactly the four P0 gates, once each: "
        f"{gates!r}"
    )
    for gate, node, reason in rows:
        assert reason.strip(), f"{gate}: an allowlist row without a reason is a rubber stamp"
        assert ".py::" in node, f"{gate}: row must name '<path>.py::<test>': {node!r}"
        path_text, _, test_name = node.partition("::")
        target = ROOT / path_text
        assert target.is_file(), f"{gate}: {path_text} does not exist"
        assert f"def {test_name}(" in target.read_text(encoding="utf-8"), (
            f"{gate}: {path_text} has no test named {test_name!r} — the ledger "
            "must point at the gate that is actually xfailed"
        )
        assert re.search(r"\bP[1-4]\b", reason), (
            f"{gate}: the reason must name the phase that deletes the row "
            f"(plan {PLAN}): {reason!r}"
        )

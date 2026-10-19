"""Navigation coverage gate: every interactive control is nav-owned or exempt.

Requirement: ``spec.nav.coverage`` (frozen seam: ``docs/dev/EVIDENCE.md`` /
ADR-008; judging rule: ``docs/dev/MCP.md`` § *Judging keyboard reachability*).

> For a registered window, every visible+enabled interactive control reports a
> navigation owner (``owned_by_section`` not null) or appears in a **reasoned
> exemption list**.

The app's keyboard cursor is the toolkit ``NavigationManager``'s section graph,
not Qt focus, so "can a keyboard reach this control?" is judged through the pair
``ui_elements`` + ``ui_nav_state`` over a **real** widget tree — never through
``focusWidget()`` and never through ``ui_click`` (in-process delivery fires a
handler even for a control no real keyboard could reach).

This probe runs over the ``_Harness`` from
``tests/devtools/test_control_nav_state.py`` (imported, not duplicated: that
module already owns the nav-manager wiring and the two-section fixture).

Falsification (red against a blind "it's probably fine" probe):

* the element list is recomputed from ``ui_elements`` on every run — no
  hardcoded count, role tally, or id list — so adding an interactive control
  that no section owns and that is not exempt fails here with its id;
* ownership is read from the instrument (``nav_state.owner_of`` over the
  manager ``ui_nav_state`` itself reports), and the probe cross-checks the
  instrument's own focus row: a probe that kept a second, drifting ownership
  model would disagree with ``ui_nav_state`` and fail;
* the exemption list is narrow (one fixture double, with a stated reason); it
  is not a wildcard, so a new unowned control is *not* covered by it.

Runs offscreen only — no Xvfb (the supervisor runs the live proof).
"""

from __future__ import annotations

import pytest

from core.control import nav_state
from core.control.elements.inventory import collect_elements
from core.evidence.journal import record_evidence, reset_journal, verdict

# Reuse the fixture + handlers rather than re-wiring a NavigationManager here
# (a second wiring would diverge from the instrument under test).
try:  # collected as part of the ``tests`` package (repo root on sys.path)
    from tests.devtools.test_control_nav_state import _Harness, _handlers, _qapp
except ImportError:  # pytest prepend mode: tests/devtools is on sys.path
    from test_control_nav_state import _Harness, _handlers, _qapp

#: Roles that a user is expected to operate (``ui_elements`` role vocabulary).
INTERACTIVE_ROLES = frozenset({"button", "input", "action"})

#: Why the harness overlay's children are exempt from *section* ownership.
#:
#: ``_TestOverlay`` is a fixture double, not a product surface: it exists to pin
#: ``ui_nav_state``'s honest ``owned_by_section: null`` reading
#: (``test_control_nav_state.test_overlay_children_are_listed_and_unowned``).
#: It has no keyboard contract of its own, so exempting it records the fixture's
#: intent — it does not hide an app gap. Remove this single entry and the same
#: window reports its two buttons as orphans (the supervisor's fix-vs-exemption
#: call); it is deliberately not a wildcard.
_EXEMPT_OVERLAY_REASON = (
    "fixture double: _TestOverlay exists to pin ui_nav_state's honest "
    "owned_by_section=null reading (test_control_nav_state.py); no product "
    "control, no keyboard contract"
)


@pytest.fixture(autouse=True)
def _reset_evidence_journal():
    """Evidence is append-only: isolate this probe from every other one."""
    reset_journal()
    yield
    reset_journal()


def _within(widget, ancestor) -> bool:
    """True when *widget* is *ancestor* or lives inside it (never raises)."""
    if widget is ancestor:
        return True
    try:
        return bool(ancestor.isAncestorOf(widget))
    except Exception:
        return False


def _exemption(widget, harness: _Harness) -> str | None:
    """The stated reason this control is deliberately outside the section graph.

    One entry today (see ``_EXEMPT_OVERLAY_REASON``); any other unowned control
    stays an orphan and fails the probe.
    """
    if _within(widget, harness.overlay):
        return _EXEMPT_OVERLAY_REASON
    return None


def test_every_interactive_control_is_nav_owned_or_exempt() -> None:
    """spec.nav.coverage over the live harness window; emits derived evidence."""
    app = _qapp()
    harness = _Harness(app)
    try:
        handlers = _handlers(harness.window)
        payload = handlers.ui_elements({})
        state = handlers.ui_nav_state({})
        manager = nav_state.nav_manager()
        assert manager is not None, "the harness registered no navigation manager"

        # The payload carries no widget references; the inventory is the same
        # deterministic walk, so ids resolve back to the live widgets.
        widgets_by_id = {
            element.id: element.widget
            for element in collect_elements(
                registry=handlers._registry(), include_disabled=True
            )
        }

        # The probe must judge with the same ownership model the instrument
        # reports: if these disagree, the probe is not measuring the app's
        # navigation graph (a duplicated manager/section list would diverge).
        focus_row = state.get("focus") or {}
        focus_element_id = focus_row.get("element_id")
        if focus_element_id:
            focus_widget = widgets_by_id.get(focus_element_id)
            assert focus_widget is not None, (
                f"ui_nav_state reports focus {focus_element_id!r} that ui_elements "
                "does not inventory"
            )
            assert nav_state.owner_of(manager, focus_widget) == focus_row.get(
                "owned_by_section"
            ), (
                "probe ownership disagrees with ui_nav_state for the focused "
                f"widget: {focus_row.get('owned_by_section')!r} vs "
                f"{nav_state.owner_of(manager, focus_widget)!r}"
            )

        owned: list[str] = []
        exempt: list[str] = []
        orphans: list[str] = []
        detail: dict[str, str] = {}
        interactive: list[str] = []

        for row in payload.get("elements") or ():
            if row.get("role") not in INTERACTIVE_ROLES:
                continue
            if not row.get("visible") or not row.get("enabled"):
                continue
            element_id = row["id"]
            widget = widgets_by_id.get(element_id)
            if widget is None:
                # Cannot prove an owner without the live widget: an honest
                # orphan, never a silent skip (ids are meant to be stable).
                interactive.append(element_id)
                orphans.append(element_id)
                detail[element_id] = (
                    f"role={row.get('role')} label={row.get('label')!r} "
                    "(no live widget in the inventory walk)"
                )
                continue
            if not _within(widget, harness.window):
                continue  # another top-level window — not this registered window
            interactive.append(element_id)
            detail[element_id] = f"role={row.get('role')} label={row.get('label')!r}"
            if nav_state.owner_of(manager, widget):
                owned.append(element_id)
                continue
            reason = _exemption(widget, harness)
            if reason is not None:
                exempt.append(element_id)
                continue
            orphans.append(element_id)

        orphans.sort()
        ok = not orphans
        record_evidence("spec.nav.coverage",
                        kind="spec",
                        verdict="ok" if ok else "violated",
                        signal=(
                            f"interactive={len(interactive)} owned={len(owned)} "
                            f"exempt={len(exempt)} orphans={orphans}"
                        ),
                        reason=(
                            "every interactive control is nav-owned or explicitly "
                            "exempted"
                            if ok
                            else "interactive controls with no navigation owner and "
                            "no exemption"
                        ),
                        ids=tuple(orphans),
                        area="nav.coverage")

        record = verdict(None, "spec.nav.coverage")
        assert record is not None, "nav-coverage probe emitted no evidence"

        # Assert AFTER emitting, so the failure is readable as evidence.
        assert ok, (
            "spec.nav.coverage violated — interactive controls with no "
            "navigation owner and no reasoned exemption: "
            + ", ".join(
                f"{element_id} ({detail[element_id]})" for element_id in orphans
            )
        )
        assert record.verdict == "ok", record.signal
    finally:
        harness.close()

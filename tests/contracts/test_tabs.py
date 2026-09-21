"""Tab contract dogma.

Every package under ``src/tabs/`` must expose a ``TabContract`` subclass
with a filled-in ``session_type`` and ``display_name``; ``session_type`` must
be unique across tabs (it is the routing key in ``TabRegistry``).

Dogma source: docs/dev/tabs/contract.md.
"""

from __future__ import annotations

from tabs.contract import TabContract
from tabs.registry import TabRegistry

def _discover() -> list[TabContract]:
    registry = TabRegistry()
    registry.discover()
    return registry.list_tabs()

def test_at_least_one_tab_discovered():
    assert _discover(), "no TabContract implementations discovered under src/tabs/"

def test_every_tab_is_a_filled_contract():
    problems: list[str] = []
    for tab in _discover():
        if not isinstance(tab, TabContract):
            problems.append(f"{type(tab).__name__} is not a TabContract")
            continue
        if not isinstance(tab.session_type, str) or not tab.session_type.strip():
            problems.append(f"{type(tab).__name__}.session_type is empty")
        if not isinstance(tab.display_name, str) or not tab.display_name.strip():
            problems.append(f"{type(tab).__name__}.display_name is empty")
    assert not problems, "\n  - " + "\n  - ".join(problems)

def test_session_type_is_unique():
    # Uniqueness covers sources too: each session_type must trace back to
    # exactly one (class, module) origin, so a duplicate registration can
    # never silently shadow another tab's routing key.
    seen: dict[str, tuple[str, str]] = {}
    collisions: list[str] = []
    for tab in _discover():
        st = tab.session_type
        origin = (type(tab).__name__, type(tab).__module__)
        if st in seen:
            prev_cls, prev_mod = seen[st]
            collisions.append(
                f"session_type '{st}' used by {prev_cls} ({prev_mod}) "
                f"and {origin[0]} ({origin[1]})"
            )
        else:
            seen[st] = origin
    assert not collisions, "\n  - " + "\n  - ".join(collisions)


def test_startup_tier_is_a_valid_literal():
    problems: list[str] = []
    for tab in _discover():
        tier = getattr(tab, "startup_tier", "deferred")
        if tier not in ("bootstrap", "deferred"):
            problems.append(
                f"{type(tab).__name__} ({type(tab).__module__}).startup_tier={tier!r}"
            )
    assert not problems, "\n  - " + "\n  - ".join(problems)

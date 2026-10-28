"""An AI-domain analyze refusal reaches the UI, not only ``log.txt``.

RED-BEFORE (live 2026-10-28 14:53): the owner right-clicked a card and chose
Analyze. The handler logged

    src/tabs/image_gallery/use_cases/gallery_actions.py:184  analyze refused: no_profile (the AI backend has no
                            axis set yet — a 0-axis scorecard measures nothing)

at DEBUG, the menu closed, and the card stayed exactly as it was. The reason a
paid backend did nothing existed nowhere the user could look — their report was
"по UX это тоже не узнать".

The gallery already owns an error language for this domain: the controller
paints ``AnalysisStatus.ERROR`` + ``analysis_error`` on the cards
(``_mark_ai_profile_error``). The refusal now goes through that same surface and
the log line is a WARNING, because a backend that cannot run is not a trace
detail. An Algorithms refusal (empty scope / no items) keeps its DEBUG line: it
is an ordinary "nothing to do", not a broken backend.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.use_cases.action_context import (
    BACKEND_AI,
    REFUSAL_NO_ITEMS,
    REFUSAL_NO_PROFILE,
    ActionContext,
    Refusal,
)
from tabs.image_gallery.use_cases.gallery_actions import menu_action_handlers


def _ctx(backend=BACKEND_AI):
    return ActionContext(
        targets=(Path("/g/a.png"), Path("/g/b.png")),
        backend=backend,
        profile=None,
    )


def _owner(answer):
    """A thin owner double: ``analyze`` returns *answer*, and records the paint."""
    marked: list[str] = []
    owner = SimpleNamespace(
        analyze=lambda ctx: answer,
        _mark_ai_profile_error=marked.append,
    )
    return owner, marked


def test_a_no_profile_refusal_is_painted_on_the_cards_and_warns(caplog):
    refusal = Refusal(
        REFUSAL_NO_PROFILE,
        (Path("/g/a.png"), Path("/g/b.png")),
        "the AI backend has no axis set yet — a 0-axis scorecard measures nothing",
    )
    owner, marked = _owner(refusal)
    handlers = menu_action_handlers(owner=owner, ctx=_ctx())

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        handlers["analyze"]()

    assert marked == [refusal.detail], "the refusal must reach the card surface"
    warnings = [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING and "no_profile" in record.getMessage()
    ]
    assert warnings, "a paid backend that cannot run must log above DEBUG"


def test_a_not_configured_refusal_is_painted_too(caplog):
    from tabs.image_gallery.use_cases.action_context import REFUSAL_NOT_CONFIGURED

    refusal = Refusal(
        REFUSAL_NOT_CONFIGURED,
        (Path("/g/a.png"),),
        "the AI backend is selected but its settings are not configured",
    )
    owner, marked = _owner(refusal)
    handlers = menu_action_handlers(owner=owner, ctx=_ctx())

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        handlers["analyze"]()

    assert marked == [refusal.detail]


def test_an_algorithms_refusal_keeps_its_quiet_line(caplog):
    """An ordinary "nothing to do" must not paint every card as an AI error."""
    refusal = Refusal(REFUSAL_NO_ITEMS, (), "no resolved target is in the pool")
    owner, marked = _owner(refusal)
    handlers = menu_action_handlers(
        owner=owner, ctx=_ctx(backend="algorithms")
    )

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        handlers["analyze"]()

    assert marked == [], "a non-AI refusal is not an AI-backend error"
    assert not [
        record for record in caplog.records if record.levelno >= logging.WARNING
    ]


def test_a_successful_analyze_paints_nothing():
    owner, marked = _owner(None)
    handlers = menu_action_handlers(owner=owner, ctx=_ctx())
    handlers["analyze"]()
    assert marked == []

"""Every RenderConfig field survives dispatch + restart roundtrip.

Dogma source: docs/dev/STORE.md + docs/dev/STATE_SLOT_MANIFEST.md
(viewport.render_config is dispatch-only; the project viewport blob
carries it across restarts).

For each live ``RenderConfig`` field (read from the dataclass, not a
literal list -- template: tests/contracts/test_no_direct_store_mutation.py
``_build_intermediate``) there must exist:
(a) a reducer branch mentioning the field (some ``*reducer*.py``), i.e. a
dispatch path exists, and
(b) a persistence mention (some ``*persistence*.py``), i.e. the restart
roundtrip carries it.

Fields with a documented gap stay in KNOWN_GAPS with a reason (one owner
per invariant -- TESTING.md); any other uncovered field fails.

Template: tests/contracts/test_canvas_features_manifest.py (per-node
parametrize over live shape) + test_viewport_state_slots.py (live shape
+ source scan pair).
"""

from __future__ import annotations

import ast
import dataclasses

from ._framework import SRC, iter_py, read

KNOWN_GAPS: dict[str, str] = {
    "jpeg_quality": (
        "STATE_SLOT_MANIFEST.md + session_persistence.py:368 NOTE: no dedicated "
        "Action/reducer yet; serialized but stays at live value on restore"
    ),
}


def _render_config_fields() -> list[str]:
    from core.store_viewport import RenderConfig

    return [f.name for f in dataclasses.fields(RenderConfig)]


def _files_matching(sub: str) -> list:
    return [p for p in iter_py(SRC) if sub in p.as_posix()]


def _text_hits(sub: str, needle: str) -> list[str]:
    hits: list[str] = []
    for p in _files_matching(sub):
        try:
            text = read(p)
        except Exception:
            continue
        if needle in text:
            hits.append(p.as_posix())
    return hits


def test_render_config_fields_have_reducer_branch():
    fields = _render_config_fields()
    assert fields, "RenderConfig has no fields -- import broken?"
    offenders = [
        f for f in fields if f not in KNOWN_GAPS and not _text_hits("reducer", f)
    ]
    assert not offenders, (
        "RenderConfig fields with no reducer branch (no dispatch path -- "
        "the value can never land in the Store via Action):\n  - "
        + "\n  - ".join(offenders)
    )


def test_render_config_fields_survive_persistence_roundtrip():
    fields = _render_config_fields()
    offenders = [
        f
        for f in fields
        if f not in KNOWN_GAPS and not _text_hits("persistence", f)
    ]
    assert not offenders, (
        "RenderConfig fields invisible to *persistence*.py (restart drops "
        "them -- serialize/restore the field or register the gap):\n  - "
        + "\n  - ".join(offenders)
    )


def test_known_gaps_are_still_gaps():
    fields = set(_render_config_fields())
    stale = sorted(k for k in KNOWN_GAPS if k not in fields)
    assert not stale, (
        "Stale KNOWN_GAPS entries -- the field is gone, delete the exemption:\n  - "
        + "\n  - ".join(stale)
    )

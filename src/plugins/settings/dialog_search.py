"""In-dialog Settings search — reuses the Find Action catalog.

The search box in the Settings dialog filters *sections*, not chrome rows:
everything a query matches inside a section ("General ▸ Language ▸ English",
a group title, a control name, any translation) collapses into **one row
titled by the section** ("General"). Activating the row opens the section and
scrolls to the best-matching group/member inside it.

Matching and cross-language haystacks come from the host registry machinery
(``compute_action_haystacks`` — every supported UI language, ``ё``-folding),
and per-keystroke filtering happens **in the nav list itself**
(``IconListWidget.set_search_text``, ComboBox-style visible-index pool — no
widget rebuilds per keystroke). No second index is built: the ``SearchIndex``
tagging on ``SettingsSection`` remains the single source of truth.

The section catalog is materialized once per search session (``catalog_rows``)
into the sidebar's row pool.

Note: action ids are not parsed by splitting on ``.`` — section ids and group
title keys contain dots (e.g. ``builtin.general``, ``label.details``). The
id → chrome-address map is built by *enumerating* the registry's sections,
groups and members (the same enumeration ``actions.py`` registers rows from),
then looking action ids up exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sli_ui_toolkit.ui.widgets.comboboxes._search import (
    match_score_normalized,
    normalize_for_search,
)
from sli_ui_toolkit.widgets import IconListItem

from ui.actions.registry import (
    action_breadcrumb_text,
    compute_action_haystacks,
    get_action_registry,
)


@dataclass(slots=True)
class SettingsSearchResult:
    """One chrome row inside a section (page/group/member address + haystack)."""

    action_id: str
    section_id: str
    group_key: str | None
    member_key: str | None
    label: str = ""
    crumb: str = ""
    search_texts: tuple[str, ...] = ()


@dataclass(slots=True)
class SectionSearchResult:
    """One sidebar row per matching section — the search result unit."""

    section_id: str
    label: str
    search_texts: tuple[str, ...]
    rows: tuple[SettingsSearchResult, ...] = field(default_factory=tuple)


def chrome_map(dialog) -> dict[str, SettingsSearchResult]:
    """``action_id -> SettingsSearchResult`` for every settings chrome slot.

    Enumerates each active section's ``SearchIndex`` groups + members and the
    tab extras (``iter_extra_searches``) — the exact same enumeration
    ``plugins/settings/actions.py`` registers catalog rows from.
    """
    from plugins.settings.registry import get_settings_registry

    out: dict[str, SettingsSearchResult] = {}
    registry = get_settings_registry()
    for section in dialog._active_sections:
        sid = section.section_id
        out[f"settings.page.{sid}"] = SettingsSearchResult(
            action_id=f"settings.page.{sid}",
            section_id=sid,
            group_key=None,
            member_key=None,
        )
        for group in section.search.groups:
            _map_group(out, sid, group)
        for _owner, extra_search in registry.iter_extra_searches(sid):
            for group in extra_search.groups:
                _map_group(out, sid, group)
    return out


def _map_group(out: dict[str, SettingsSearchResult], sid: str, group) -> None:
    title = group.title_key
    if not title:
        return
    out[f"settings.group.{sid}.{title}"] = SettingsSearchResult(
        action_id=f"settings.group.{sid}.{title}",
        section_id=sid,
        group_key=title,
        member_key=None,
    )
    for member in group.member_keys:
        out[f"settings.group.{sid}.{title}.{member}"] = SettingsSearchResult(
            action_id=f"settings.group.{sid}.{title}.{member}",
            section_id=sid,
            group_key=title,
            member_key=member,
        )


def section_catalog(dialog) -> list[SectionSearchResult]:
    """One row per section, searchable by *anything* inside it.

    ``search_texts`` is the union of every chrome row's haystack (page, group
    and member rows — ids, labels, descriptions, breadcrumbs, aliases,
    normalized, all languages), so a query hits the section as soon as any
    entry inside it matches — and the best-matching entry stays addressable
    via ``best_address``.
    """
    registry = get_action_registry()
    by_id = chrome_map(dialog)
    sections: dict[str, list[SettingsSearchResult]] = {
        s.section_id: [] for s in dialog._active_sections
    }
    for action_id, base in by_id.items():
        action = registry.get(action_id)
        if action is None:
            continue
        base.label = _action_label(action)
        base.crumb = action_breadcrumb_text(action)
        # Normalize every haystack text with the SAME NFKD folding the
        # matcher's query side uses (``normalize_for_search`` — which
        # decomposes e.g. «й» → «и» + combining breve). The registry's
        # ``compute_action_haystacks`` only lowercases/ё-folds; scoring raw
        # texts against an NFKD query silently misses matches («русский»)
        # and falls back to random fuzzy subsequence hits.
        base.search_texts = tuple(
            normalize_for_search(text)
            for text in compute_action_haystacks(
                action_id=action.action_id,
                label_key=action.label_key,
                description_key=action.description_key,
                breadcrumb=tuple(action.breadcrumb or ()),
                topic=action.topic,
                shortcut=action.shortcut,
                search_keys=tuple(getattr(action, "search_keys", ()) or ()),
                search_terms=tuple(getattr(action, "search_terms", ()) or ()),
            )
        )
        sections[base.section_id].append(base)

    out: list[SectionSearchResult] = []
    for section in dialog._active_sections:
        rows = tuple(sections[section.section_id])
        merged: list[str] = []
        for row in rows:
            merged.extend(row.search_texts)
        out.append(
            SectionSearchResult(
                section_id=section.section_id,
                label=_section_title(dialog, section),
                search_texts=tuple(dict.fromkeys(merged)),
                rows=rows,
            )
        )
    return out


def _section_title(dialog, section) -> str:
    from ui.actions.registry import _display_text

    return _display_text(section.title_key)


def _action_label(action) -> str:
    from ui.actions.registry import _display_text

    return _display_text(action.label_key)


def build_results(dialog, query: str) -> list[SectionSearchResult]:
    """Ranked section rows for ``query`` (Find Action semantics).

    Uses the same scoring the nav list applies in ``set_search_text``; kept
    as a pure function so tests can assert on ranking without a widget.
    """
    norm_query = normalize_for_search(query)
    if not norm_query:
        return []
    scored: list[tuple[int, SectionSearchResult]] = []
    for section_result in section_catalog(dialog):
        score = _best_text_score(norm_query, section_result.search_texts)
        if score is not None:
            scored.append((score, section_result))
    scored.sort(key=lambda item: (item[0], item[1].section_id))
    return [result for _score, result in scored]


def _best_text_score(norm_query: str, texts: tuple[str, ...]) -> int | None:
    best: int | None = None
    for text in texts:
        score = match_score_normalized(norm_query, text)
        if score is not None:
            best = score if best is None else min(best, score)
    return best


def best_address(
    result: SectionSearchResult,
    query: str,
) -> tuple[str | None, str | None]:
    """Best ``(group_key, member_key)`` matched inside the section.

    ``(None, None)`` when only the section itself (page row / title) matched.
    ``match_score_normalized`` is non-fuzzy by default, so only locatable
    matches resolve (same rule as ``matching_targets``).
    """
    norm_query = normalize_for_search(query)
    if not norm_query:
        return None, None
    best_row: SettingsSearchResult | None = None
    best_score: int | None = None
    for row in result.rows:
        score = _best_text_score(norm_query, row.search_texts)
        if score is not None and (best_score is None or score < best_score):
            best_row = row
            best_score = score
    if best_row is None or best_row.group_key is None:
        return None, None
    return best_row.group_key, best_row.member_key


def section_icon(dialog, section_id: str):
    for section in dialog._active_sections:
        if section.section_id == section_id:
            return section.icon
    return None


def catalog_rows(dialog) -> list[IconListItem]:
    """Row specs for ``sidebar.set_items`` — one row per section, one pool
    per search session; per-keystroke filtering happens in the widget."""
    return [
        IconListItem(
            text=result.label,
            icon=section_icon(dialog, result.section_id),
            data=result,
            search_texts=result.search_texts,
        )
        for result in section_catalog(dialog)
    ]


def _row_depth(row: SettingsSearchResult) -> int:
    """Match depth inside a section: 0 = page/section, 1 = group, 2 = member."""
    if row.group_key is None:
        return 0
    if row.member_key is None:
        return 1
    return 2


def _row_score(norm_query: str, texts: tuple[str, ...]) -> int | None:
    score = _best_text_score(norm_query, texts)
    if score is None:
        return None
    return score


def matching_targets(
    dialog,
    result: SectionSearchResult,
    query: str,
) -> list[object]:
    """The controls to highlight inside the section for ``query``.

    Picks the least-deep matched level (section title < group < member) and
    returns **every** matched control on that level (1..N) — so a query that
    hits several members of one group pulses all of them. Scrolls each
    control into the page viewport as a side effect of the resolve helpers
    (same path Find Action reveal uses).

    ``match_score_normalized`` is non-fuzzy by default (exact / prefix /
    substring only — Find Action semantics), so long haystack texts cannot
    produce scatter hits that would pulse unrelated controls.
    """
    norm_query = normalize_for_search(query)
    if not norm_query:
        return []
    matched = [
        row
        for row in result.rows
        if _row_score(norm_query, row.search_texts) is not None
    ]
    if not matched:
        return []
    min_depth = min(_row_depth(row) for row in matched)
    targets: list[object] = []
    seen: set[int] = set()
    for row in matched:
        if _row_depth(row) != min_depth:
            continue
        widget = _resolve_row_widget(dialog, row)
        if widget is None:
            continue
        key = id(widget)
        if key in seen:
            continue
        seen.add(key)
        targets.append(widget)
    return targets


def _resolve_row_widget(dialog, row: SettingsSearchResult):
    """Scroll the matched control into view and return the widget to pulse.

    ``group_widget_for``/``member_widget_for`` already scroll (and
    ``member_widget_for`` opens combo dropdowns focused on the requested
    option). For combo members it returns the *dropdown row* (or a
    ``_PulseDeferred`` that pulses that row when the dropdown settles) — the
    closed field itself is never the highlight target, or the ring lands on
    the popup's anchor (the currently selected cell) instead of the
    requested option.
    """
    from ui.actions.combo_reveal import _PulseDeferred

    if row.member_key is not None:
        dialog.group_widget_for(row.group_key)
        target = dialog.member_widget_for(row.group_key, row.member_key)
        if target is None or isinstance(target, _PulseDeferred):
            return None
        return target
    if row.group_key is not None:
        return dialog.group_widget_for(row.group_key)
    return None


def navigate(
    dialog,
    result: SectionSearchResult,
    query: str = "",
) -> list[object]:
    """Open the section and return the controls to highlight (1..N).

    Does not touch the sidebar selection (in search mode the sidebar holds
    result rows, not sections) — it switches the page stack directly.
    """
    if result is None or not result.section_id:
        return []
    for index, section in enumerate(dialog._active_sections):
        if section.section_id == result.section_id:
            dialog.pages_stack.setCurrentIndex(index)
            break
    return matching_targets(dialog, result, query)

"""Host-owned action catalog (mirrors SettingsRegistry ownership)."""

from __future__ import annotations

from core.actions.types import ActionDescriptor


class ActionRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, ActionDescriptor] = {}

    def register(self, action: ActionDescriptor) -> None:
        if not action.action_id:
            raise ValueError("ActionDescriptor.action_id must be non-empty")
        self._by_id[action.action_id] = action
        _invalidate_haystack_cache(action.action_id)

    def unregister(self, action_id: str) -> None:
        self._by_id.pop(action_id, None)
        _invalidate_haystack_cache(action_id)

    def unregister_owner(self, owner_tab: str) -> None:
        doomed = [
            action_id
            for action_id, action in self._by_id.items()
            if action.owner_tab == owner_tab
        ]
        for action_id in doomed:
            del self._by_id[action_id]
            _invalidate_haystack_cache(action_id)

    def unregister_prefix(self, prefix: str) -> None:
        """Drop actions whose ids start with ``prefix`` (dialog chrome teardown).

        Prefer this over ``unregister_owner("image_compare")`` when clearing
        temporary dialog rows — owner unregister would also wipe toolbar actions.
        """
        if not prefix:
            return
        doomed = [
            action_id for action_id in self._by_id if action_id.startswith(prefix)
        ]
        for action_id in doomed:
            del self._by_id[action_id]
            _invalidate_haystack_cache(action_id)

    def get(self, action_id: str) -> ActionDescriptor | None:
        return self._by_id.get(action_id)

    def all_actions(self) -> list[ActionDescriptor]:
        return list(self._by_id.values())

    def list_for(
        self,
        *,
        active_tab: str | None,
        query: str = "",
        topic: str | None = None,
    ) -> list[ActionDescriptor]:
        needle = _normalize((query or "").strip())
        visible = (
            a
            for a in self._by_id.values()
            if (a.owner_tab is None or a.owner_tab == active_tab)
            and (topic is None or a.topic == topic)
            and _action_chrome_is_available(a)
        )
        if not needle:
            out = list(visible)
            out.sort(key=_empty_list_sort_key)
            return out
        # Rank each action once — reused for both the filter and the sort key
        # below, instead of recomputing it a second time per comparison.
        scored: list[tuple[int, ActionDescriptor]] = []
        for action in visible:
            rank = _best_match_rank(action, needle)
            if rank is not None:
                scored.append((rank, action))
        scored.sort(key=lambda item: (item[0], item[1].owner_tab or "", item[1].action_id))
        return [action for _rank, action in scored]

    def find_for_widget(
        self,
        widget: object | None,
        *,
        active_tab: str | None = None,
    ) -> ActionDescriptor | None:
        """Best catalog action whose ``ActionTarget`` is ``widget`` or an ancestor."""
        if widget is None:
            return None
        chain: list[object] = []
        current = widget
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            chain.append(current)
            parent = getattr(current, "parentWidget", None)
            current = parent() if callable(parent) else None

        best: ActionDescriptor | None = None
        best_depth = 10**9
        for action in self.list_for(active_tab=active_tab):
            target = getattr(action, "target", None)
            target_widget = getattr(target, "widget", None) if target is not None else None
            if target_widget is None:
                continue
            try:
                depth = chain.index(target_widget)
            except ValueError:
                continue
            if depth < best_depth:
                best = action
                best_depth = depth
                if depth == 0:
                    break
        return best

    def topic_for_widget(
        self,
        widget: object | None,
        *,
        active_tab: str | None = None,
    ) -> str | None:
        action = self.find_for_widget(widget, active_tab=active_tab)
        return action.topic if action is not None else None


# Find Action matches Settings chrome typed in any UI language, not only the
# active one (e.g. «английский» while the app is in RU, or «theme» in EN).
_SEARCH_LANGS = ("en", "ru", "zh", "pt_BR")


def _normalize(text: str) -> str:
    """Lowercase + fold ``ё``→``е`` so «нашёл»/«нашел» are equivalent queries."""
    return text.lower().replace("ё", "е")


def _display_text(key: str, lang: str | None = None) -> str:
    """Resolve an i18n key to a display string (current lang unless overridden)."""
    if not key:
        return ""
    if lang is None:
        from ui.actions.palette.common import tr_action

        return tr_action(key, key)
    from resources.translations import tr

    text = tr(key, lang)
    return key if not text or text == key else text


def _texts_for_key(key: str) -> list[str]:
    """Key + translations in every supported language (deduped)."""
    if not key:
        return []
    out: list[str] = [key]
    seen = {_normalize(key)}
    for lang in _SEARCH_LANGS:
        text = _display_text(key, lang)
        if not text:
            continue
        needle = _normalize(text)
        if needle in seen:
            continue
        seen.add(needle)
        out.append(text)
    return out


def _empty_list_sort_key(action: ActionDescriptor) -> tuple:
    """``platform.settings`` first; owners with an explicit ``sort_key`` (e.g.
    a Settings page followed by its groups and member slots) come next in
    that order; everything else falls back to id-based ordering.
    """
    if action.action_id == "platform.settings":
        return (0, (), "")
    if action.sort_key:
        return (0, action.sort_key, action.action_id)
    if action.owner_tab is None:
        return (1, action.action_id)
    return (2, action.owner_tab or "", action.action_id)


def _action_chrome_is_available(action: ActionDescriptor) -> bool:
    """Skip toolbar slots hidden by the current UI mode.

    Actions with ``ensure_visible`` / ``resolve_widget`` stay listed (Settings,
    workspace cards). Live ``target.widget`` that was ``hide()``-n by a layout
    manager must not appear in Find Action or claim shortcuts.
    """
    target = getattr(action, "target", None)
    if target is None:
        return True
    if callable(getattr(target, "ensure_visible", None)):
        return True
    if callable(getattr(target, "resolve_widget", None)):
        return True
    widget = getattr(target, "widget", None)
    if widget is None:
        return True
    is_hidden = getattr(widget, "isHidden", None)
    if not callable(is_hidden):
        return True
    try:
        return not bool(is_hidden())
    except Exception:
        return True


# Haystacks are independent of the *active* UI language — ``_texts_for_key``
# already expands every key into all supported languages up front — so they
# are safe to cache per action id for the life of the process. Filtering
# recomputes this on every keystroke otherwise, which is the main cost of a
# large catalog; caching turns it into a one-time cost per action.
_HAYSTACK_CACHE: dict[str, tuple[str, ...]] = {}


def _invalidate_haystack_cache(action_id: str) -> None:
    _HAYSTACK_CACHE.pop(action_id, None)


def _haystacks(action: ActionDescriptor) -> tuple[str, ...]:
    cached = _HAYSTACK_CACHE.get(action.action_id)
    if cached is not None:
        return cached
    search_keys = tuple(getattr(action, "search_keys", ()) or ())
    parts = [
        action.action_id,
        action.label_key,
        action.description_key or "",
        " ".join(action.breadcrumb),
        action.topic or "",
        action.shortcut or "",
        " ".join(getattr(action, "search_terms", ()) or ()),
    ]
    for key in (
        action.label_key,
        action.description_key or "",
        *action.breadcrumb,
        *search_keys,
    ):
        if key:
            parts.extend(_texts_for_key(key))
    normalized = tuple(_normalize(part) for part in parts if part)
    _HAYSTACK_CACHE[action.action_id] = normalized
    return normalized


def _rank_token_in_text(text: str, token: str) -> int | None:
    """Lower is better: exact=0, prefix=1, substring=2."""
    if text == token:
        return 0
    if text.startswith(token) or text.rsplit(".", 1)[-1].startswith(token):
        return 1
    if token in text:
        return 2
    return None


def _best_match_rank(action: ActionDescriptor, needle: str) -> int | None:
    """Lower is better. Multi-word query: every token must match somewhere."""
    tokens = [t for t in needle.split() if t]
    if not tokens:
        return 0
    haystacks = _haystacks(action)
    total = 0
    for token in tokens:
        best: int | None = None
        for text in haystacks:
            rank = _rank_token_in_text(text, token)
            if rank is not None:
                best = rank if best is None else min(best, rank)
        if best is None:
            return None
        total += best
    return total


def action_breadcrumb_text(
    action: ActionDescriptor,
    query: str = "",
    *,
    active_tab: str | None = None,
) -> str:
    """Palette breadcrumb from the descriptor (Settings groups are own rows)."""
    del query, active_tab
    segments: list[str] = []
    for segment in action.breadcrumb or ():
        if segment:
            segments.append(_display_text(segment))
    return " ▸ ".join(segments)


_REGISTRY: ActionRegistry | None = None


def get_action_registry() -> ActionRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ActionRegistry()
    return _REGISTRY


def reset_action_registry_for_tests() -> None:
    """Clear the process singleton and haystack cache — tests only."""
    global _REGISTRY
    _REGISTRY = None
    _HAYSTACK_CACHE.clear()

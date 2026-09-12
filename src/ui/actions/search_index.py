"""Host-owned Find Action chrome index (groups + tagged controls).

Used by Settings pages and temporary dialog bridges (Video Editor, Export).
Declare each chrome group once as a ``SearchGroup``; tag widgets at build time;
bridges expand the index into ``ActionRegistry`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from sli_ui_toolkit.widgets import CustomGroupWidget

# Qt dynamic properties — generic names shared by Settings and dialogs.
PROP_GROUP = "action_search_group"
PROP_MEMBER = "action_search_member"
PROP_COMBO_OPTIONS = "action_search_combo_options"


@dataclass(frozen=True, slots=True)
class SearchGroup:
    """One chrome group (fieldset / logical cluster) and controls inside it."""

    title_key: str
    member_keys: tuple[str, ...] = ()

    @classmethod
    def of(cls, title_key: str, *member_keys: str) -> SearchGroup:
        seen: list[str] = []
        for key in member_keys:
            if key and key != title_key and key not in seen:
                seen.append(key)
        return cls(title_key=title_key, member_keys=tuple(seen))

    @property
    def keys(self) -> tuple[str, ...]:
        if not self.title_key:
            return self.member_keys
        return (self.title_key, *self.member_keys)

    def title(self, dialog) -> str:
        return _dialog_tr(dialog, self.title_key)

    def text(self, dialog, key: str) -> str:
        return _dialog_tr(dialog, key)

    def widget(self, dialog) -> CustomGroupWidget:
        w = CustomGroupWidget(self.title(dialog))
        # Find Action reveal / slot catalog key (must match SearchGroup.title_key).
        w.setProperty(PROP_GROUP, self.title_key)
        return w

    def tag_member(self, widget, member_key: str) -> None:
        """Tag a control so Find Action can pulse it instead of the whole group."""
        if widget is not None and member_key:
            widget.setProperty(PROP_MEMBER, member_key)

    def tag_combo(self, combo, control_member_key: str | None = None) -> None:
        """Tag a toolkit ``ComboBox`` row for group- or option-level reveal."""
        if combo is None:
            return
        if control_member_key:
            combo.setProperty(PROP_MEMBER, control_member_key)
        if combo.property(PROP_COMBO_OPTIONS) is None:
            combo.setProperty(PROP_COMBO_OPTIONS, {})

    def note_combo_option(self, combo, member_key: str) -> None:
        """Record that the last ``addItem`` on ``combo`` maps to ``member_key``."""
        if combo is None or not member_key:
            return
        options = combo.property(PROP_COMBO_OPTIONS)
        if not isinstance(options, dict):
            options = {}
        else:
            options = dict(options)
        count = getattr(combo, "count", lambda: 0)
        options[member_key] = int(count()) - 1
        combo.setProperty(PROP_COMBO_OPTIONS, options)

    def tag_tab_page(self, host, page, member_key: str) -> None:
        """Tag a tab page; contribute will activate ``host.setCurrentWidget(page)``."""
        self.tag_member(page, member_key)
        if page is not None and host is not None:
            setattr(page, "_action_search_tab_host", host)


@dataclass(frozen=True, slots=True)
class SearchIndex:
    """Chrome index built from ``SearchGroup``s (page- or dialog-level)."""

    groups: tuple[SearchGroup, ...] = ()

    @classmethod
    def of(cls, *groups: SearchGroup) -> SearchIndex:
        return cls(groups=tuple(groups))

    def merged(self, *others: SearchIndex | None) -> SearchIndex:
        groups = list(self.groups)
        for other in others:
            if other is None:
                continue
            groups.extend(other.groups)
        return SearchIndex(groups=tuple(groups))

    @property
    def keys(self) -> tuple[str, ...]:
        seen: list[str] = []
        for group in self.groups:
            for key in group.keys:
                if key not in seen:
                    seen.append(key)
        return tuple(seen)

    @property
    def action_groups(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """``(title_key, keys)`` per group — used by tests to assert shape."""
        return tuple(
            (group.title_key, group.keys) for group in self.groups if group.title_key
        )


def group(title_key: str, *member_keys: str) -> SearchGroup:
    """Shorthand for ``SearchGroup.of`` at module level."""
    return SearchGroup.of(title_key, *member_keys)


def combo_option_map(widget) -> dict[str, int]:
    raw = widget.property(PROP_COMBO_OPTIONS) if widget is not None else None
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, index in raw.items():
        if key and isinstance(index, int):
            out[str(key)] = index
    return out


def find_tagged_member(root, member_key: str):
    """Find a tagged control under ``root``.

    Returns ``(widget, combo_option_index_or_None)``.
    """
    if root is None or not member_key:
        return None, None

    from PySide6.QtWidgets import QWidget

    if not isinstance(root, QWidget):
        return None, None

    direct = None
    combo_hit: tuple[object, int] | None = None
    for child in root.findChildren(QWidget):
        if child.property(PROP_MEMBER) == member_key:
            direct = child
            break
        options = combo_option_map(child)
        if member_key in options:
            combo_hit = (child, options[member_key])

    if direct is not None:
        return direct, None
    if combo_hit is not None:
        return combo_hit[0], combo_hit[1]
    return None, None


def find_tagged_group(root, group_key: str):
    if root is None or not group_key:
        return None
    from PySide6.QtWidgets import QWidget

    if not isinstance(root, QWidget):
        return None
    for child in root.findChildren(QWidget):
        if child.property(PROP_GROUP) == group_key:
            return child
    return None


def _dialog_tr(dialog, key: str) -> str:
    if not key:
        return ""
    lang = getattr(dialog, "current_language", None) or "en"
    tr_fn = getattr(dialog, "tr", None)
    if callable(tr_fn):
        try:
            return tr_fn(key, lang)
        except TypeError:
            return tr_fn(key)
    tr_fn = getattr(dialog, "_tr", None)
    if callable(tr_fn):
        return tr_fn(key)
    return key

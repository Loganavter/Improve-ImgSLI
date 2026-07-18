"""Session picker cards come from a tab-package scan, not deferred blueprints."""

from __future__ import annotations

from core.session_blueprints import SessionBlueprint
from tabs.session_picker.widget import SessionPickerWidget


class _FakeContext:
    def __init__(self, blueprints: list[SessionBlueprint]):
        self._blueprints = blueprints

    def tr(self, key: str, default: str = "") -> str:
        return default or key

    def call_service(self, name: str, *args, **kwargs):
        if name == "list_session_blueprints":
            return tuple(self._blueprints)
        if name == "get_tab_icon":
            return None
        raise RuntimeError(f"unexpected service: {name}")

    def get_active_session(self):
        return None


def test_session_picker_includes_scanned_tabs_before_blueprints(qapp):
    ctx = _FakeContext(
        [
            SessionBlueprint(
                session_type="image_compare",
                plugin_name="comparison",
                title="Image Compare",
            ),
        ]
    )
    widget = SessionPickerWidget(context=ctx)
    widget.refresh()

    assert "image_compare" in widget._cards_by_type
    assert "multi_compare" in widget._cards_by_type
    assert "session_picker" not in widget._cards_by_type


def test_session_picker_does_not_rebuild_when_blueprints_arrive(qapp):
    ctx = _FakeContext(
        [
            SessionBlueprint(
                session_type="image_compare",
                plugin_name="comparison",
                title="Image Compare",
            ),
        ]
    )
    widget = SessionPickerWidget(context=ctx)
    widget.refresh()
    first_ic = widget._cards_by_type["image_compare"]
    first_mc = widget._cards_by_type["multi_compare"]

    ctx._blueprints = [
        SessionBlueprint(
            session_type="image_compare",
            plugin_name="comparison",
            title="Image Compare",
        ),
        SessionBlueprint(
            session_type="multi_compare",
            plugin_name="multi_compare",
            title="Multi Compare",
        ),
    ]
    widget.refresh()

    assert widget._cards_by_type["image_compare"] is first_ic
    assert widget._cards_by_type["multi_compare"] is first_mc


def test_session_picker_refresh_is_noop_when_already_populated(qapp):
    ctx = _FakeContext(
        [
            SessionBlueprint(
                session_type="image_compare",
                plugin_name="comparison",
                title="Image Compare",
            ),
        ]
    )
    widget = SessionPickerWidget(context=ctx)
    widget.refresh()
    first = widget._cards_by_type["image_compare"]
    widget.refresh()
    assert widget._cards_by_type["image_compare"] is first


def test_session_picker_sync_icons_on_theme_change(qapp):
    """Card icons are eager QIcons; theme switch must re-resolve them."""
    from PySide6.QtGui import QIcon, QPixmap

    light = QIcon()
    light.addPixmap(QPixmap(16, 16))
    dark = QIcon()
    dark.addPixmap(QPixmap(24, 24))
    icons = {"image_compare": light}

    class _IconContext(_FakeContext):
        def call_service(self, name: str, *args, **kwargs):
            if name == "get_tab_icon":
                return icons.get(args[0])
            return super().call_service(name, *args, **kwargs)

    ctx = _IconContext(
        [
            SessionBlueprint(
                session_type="image_compare",
                plugin_name="comparison",
                title="Image Compare",
            ),
        ]
    )
    widget = SessionPickerWidget(context=ctx)
    widget.refresh()
    card = widget._cards_by_type["image_compare"]
    icon_region = next(r for r in card._regions if r.id == "icon")
    assert icon_region.icon is light

    icons["image_compare"] = dark
    widget.on_theme_changed()

    icon_region = next(r for r in card._regions if r.id == "icon")
    assert icon_region.icon is dark


def test_session_picker_retranslate_keeps_cards_alive(qapp):
    """Language switch must not destroy create-cards (CSD opaque-paint holes)."""
    ctx = _FakeContext(
        [
            SessionBlueprint(
                session_type="image_compare",
                plugin_name="comparison",
                title="Image Compare",
            ),
        ]
    )
    widget = SessionPickerWidget(context=ctx)
    widget.resize(900, 800)
    widget.show()
    qapp.processEvents()
    widget.refresh()
    card = widget._cards_by_type["image_compare"]
    widget._retranslate()
    qapp.processEvents()
    assert widget._cards_by_type["image_compare"] is card
    assert widget.updatesEnabled() is True
    from PySide6.QtCore import Qt

    assert widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    assert widget._page_content.autoFillBackground() is True
    widget.deleteLater()

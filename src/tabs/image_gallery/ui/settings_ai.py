"""Stage 2/3 AI settings page — base_url / api_key / model (toolkit-compliant).

Returns with Stage 2 per design.md anchors: ``plugins/settings`` contribution
path for API settings (``ui/settings_ai.py`` returns with stage 2).

Uses QSettings via ``AiSettingsStore`` — no Redux path (8-file cost for a setting
nothing else needs to react to). Section is ambient (always visible) like other
per-tab settings. ``SettingsContribution`` with section ``image_gallery.ai``.

Painter pipeline only: CustomGroupWidget, CustomLineEdit, CheckBox, no setStyleSheet.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtCore import Qt

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import CheckBox, CustomGroupWidget, CustomLineEdit, Label

from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore, DEFAULT_BASE_URL

AI_GROUP = group(
    "image_gallery.settings.ai_title",
    "image_gallery.settings.enable_ai",
    "image_gallery.settings.base_url",
    "image_gallery.settings.api_key",
    "image_gallery.settings.model_name",
    "image_gallery.settings.api_key_warning",
)
SEARCH = SearchIndex.of(AI_GROUP)


def build(dialog, p):  # type: ignore[no-untyped-def]
    """Build AI settings page for Image Gallery tab."""
    dialog.page_gallery_ai, layout = dialog._create_scrollable_page()

    # Use context helper for nav rows (mirrors builtin pages)
    try:
        from plugins.settings.nav_rows import page_nav_builder, register_page_navigation

        builder = page_nav_builder(dialog, tag="settings-gallery-ai")
    except Exception:
        builder = None  # type: ignore

    store = AiSettingsStore()
    current = store.load()

    group_widget = AI_GROUP.widget(dialog)
    # Title note inside group
    warning = Label(
        AI_GROUP.text(dialog, "image_gallery.settings.api_key_warning") if hasattr(AI_GROUP, "text") else "Stored unencrypted on this device.",
        pixel_size=10,
        parent=dialog,
    )
    try:
        warning.setWordWrap(True)
        # muted color via theme token? Keep default; no setStyleSheet
    except Exception:
        pass

    # Enable AI checkbox
    dialog.gallery_ai_enabled = CheckBox(
        AI_GROUP.text(dialog, "image_gallery.settings.enable_ai") if hasattr(AI_GROUP, "text") else "Enable AI image analysis"
    )
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_enabled, "image_gallery.settings.enable_ai")
    except Exception:
        pass
    dialog.gallery_ai_enabled.setChecked(bool(current.enabled))

    # Base URL
    url_row = QHBoxLayout()
    url_row.setContentsMargins(scaled_px(5), scaled_px(4), scaled_px(5), scaled_px(4))
    url_row.setSpacing(scaled_px(8))
    url_label = Label(
        AI_GROUP.text(dialog, "image_gallery.settings.base_url") if hasattr(AI_GROUP, "text") else "API base URL",
        pixel_size=11,
        parent=dialog,
    )
    url_label.setFixedWidth(scaled_px(110))
    dialog.gallery_ai_base_url = CustomLineEdit(parent=dialog)
    dialog.gallery_ai_base_url.setText(current.base_url or DEFAULT_BASE_URL)
    dialog.gallery_ai_base_url.setPlaceholderText(DEFAULT_BASE_URL)
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_base_url, "image_gallery.settings.base_url")
    except Exception:
        pass
    url_row.addWidget(url_label)
    url_row.addWidget(dialog.gallery_ai_base_url, 1)

    # API key (echoMode password)
    key_row = QHBoxLayout()
    key_row.setContentsMargins(scaled_px(5), scaled_px(4), scaled_px(5), scaled_px(4))
    key_row.setSpacing(scaled_px(8))
    key_label = Label(
        AI_GROUP.text(dialog, "image_gallery.settings.api_key") if hasattr(AI_GROUP, "text") else "API key",
        pixel_size=11,
        parent=dialog,
    )
    key_label.setFixedWidth(scaled_px(110))
    dialog.gallery_ai_api_key = CustomLineEdit(parent=dialog)
    dialog.gallery_ai_api_key.setText(current.api_key)
    dialog.gallery_ai_api_key.setPlaceholderText("sk-…")
    try:
        dialog.gallery_ai_api_key.setEchoMode(dialog.gallery_ai_api_key.EchoMode.Password)
    except Exception:
        pass
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_api_key, "image_gallery.settings.api_key")
    except Exception:
        pass
    key_row.addWidget(key_label)
    key_row.addWidget(dialog.gallery_ai_api_key, 1)

    # Model
    model_row = QHBoxLayout()
    model_row.setContentsMargins(scaled_px(5), scaled_px(4), scaled_px(5), scaled_px(4))
    model_row.setSpacing(scaled_px(8))
    model_label = Label(
        AI_GROUP.text(dialog, "image_gallery.settings.model_name") if hasattr(AI_GROUP, "text") else "Model name",
        pixel_size=11,
        parent=dialog,
    )
    model_label.setFixedWidth(scaled_px(110))
    dialog.gallery_ai_model = CustomLineEdit(parent=dialog)
    dialog.gallery_ai_model.setText(current.model)
    dialog.gallery_ai_model.setPlaceholderText("openrouter/auto or vendor/model")
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_model, "image_gallery.settings.model_name")
    except Exception:
        pass
    model_row.addWidget(model_label)
    model_row.addWidget(dialog.gallery_ai_model, 1)

    # Assemble group rows
    if builder is not None:
        group_widget.add_widget(builder.row(dialog.gallery_ai_enabled))
        # Wrap each QHBoxLayout in a widget row for nav
        group_widget.add_widget(builder.row(url_row))
        group_widget.add_widget(builder.row(key_row))
        group_widget.add_widget(builder.row(model_row))
        group_widget.add_widget(builder.row(warning))
    else:
        group_widget.add_widget(dialog.gallery_ai_enabled)
        # fallback: add layouts via containers
        for lay in (url_row, key_row, model_row):
            from PySide6.QtWidgets import QWidget

            w = QWidget()
            w.setLayout(lay)
            group_widget.add_widget(w)
        group_widget.add_widget(warning)

    layout.addWidget(group_widget)

    # Live persistence: save on edit (QSettings sync immediately, per ai_settings_store)
    def _save_field(name, value):
        try:
            store.save_field(name, value)
        except Exception:
            pass

    try:
        dialog.gallery_ai_enabled.toggled.connect(lambda v: _save_field("enabled", bool(v)))
        dialog.gallery_ai_base_url.textChanged.connect(lambda t: _save_field("base_url", str(t)))
        dialog.gallery_ai_api_key.textChanged.connect(lambda t: _save_field("api_key", str(t)))
        dialog.gallery_ai_model.textChanged.connect(lambda t: _save_field("model", str(t)))
    except Exception:
        pass

    # Also hook dialog accept to ensure last values flushed
    orig_get_settings = getattr(dialog, "confirm_settings", None)

    # Persist via registry payload reader/seeder for consistency with tab_extras
    # Read payload from dialog widgets
    def _read_payload(_dialog):
        try:
            return {
                "enabled": bool(_dialog.gallery_ai_enabled.isChecked()),
                "base_url": str(_dialog.gallery_ai_base_url.text()).strip(),
                "api_key": str(_dialog.gallery_ai_api_key.text()),
                "model": str(_dialog.gallery_ai_model.text()).strip(),
            }
        except Exception:
            return {}

    try:
        from plugins.settings.registry import get_settings_registry

        get_settings_registry().register_payload_reader("image_gallery.ai", _read_payload)
        # Seeder not needed — AiSettingsStore is source of truth, but register for completeness
        def _seed_payload(src):
            try:
                cur = store.load()
                return {"enabled": cur.enabled, "base_url": cur.base_url, "api_key": cur.api_key, "model": cur.model}
            except Exception:
                return {}

        get_settings_registry().register_payload_seeder("image_gallery.ai", _seed_payload)
    except Exception:
        pass

    try:
        from plugins.settings.nav_rows import register_page_navigation

        register_page_navigation(dialog, dialog.page_gallery_ai, builder)
    except Exception:
        pass
    dialog.pages_stack.addWidget(dialog.page_gallery_ai)


SECTION = SettingsSection(
    section_id="image_gallery.ai",
    title_key="image_gallery.settings.ai_title",
    icon=None,  # will be resolved to gallery icon at build; None falls back to generic
    build=build,
    owner_tab="image_gallery",
    order=30,
    action_description_key="image_gallery.settings.ai_title",
    search=SEARCH,
)

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
from sli_ui_toolkit.widgets import CheckBox, ComboBox, CustomLineEdit

from plugins.settings.typography import (
    apply_settings_body,
    settings_body_label,
    settings_caption_label,
    settings_group,
)

from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group
from tabs.image_gallery.services import vlm
from tabs.image_gallery.services.ai_settings_store import (
    REASONING_EFFORTS,
    VLM_MAX_EDGES,
    AiSettingsStore,
    DEFAULT_BASE_URL,
)

# Effort picker order — maps a ComboBox index to a stored effort value.
_EFFORT_CHOICES = REASONING_EFFORTS
_EFFORT_KEYS = (
    "image_gallery.settings.effort_auto",
    "image_gallery.settings.effort_low",
    "image_gallery.settings.effort_medium",
    "image_gallery.settings.effort_high",
    "image_gallery.settings.effort_none",
)
_EFFORT_FALLBACKS = ("Auto", "Low", "Medium", "High", "None")

AI_GROUP = group(
    "image_gallery.settings.ai_title",
    "image_gallery.settings.enable_ai",
    "image_gallery.settings.base_url",
    "image_gallery.settings.api_key",
    "image_gallery.settings.model_name",
    "image_gallery.settings.ask_max_tokens",
    "image_gallery.settings.reasoning_effort",
    "image_gallery.settings.effort_auto",
    "image_gallery.settings.effort_low",
    "image_gallery.settings.effort_medium",
    "image_gallery.settings.effort_high",
    "image_gallery.settings.effort_none",
    "image_gallery.settings.vlm_max_edge",
    "image_gallery.settings.downscale_original",
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

    group_widget = settings_group(dialog, AI_GROUP)
    # Title note inside group
    warning = settings_caption_label(
        AI_GROUP.text(dialog, "image_gallery.settings.api_key_warning") if hasattr(AI_GROUP, "text") else "Stored unencrypted on this device.",
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
    apply_settings_body(dialog.gallery_ai_enabled)
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_enabled, "image_gallery.settings.enable_ai")
    except Exception:
        pass
    dialog.gallery_ai_enabled.setChecked(bool(current.enabled))

    # Base URL
    url_row = QHBoxLayout()
    url_row.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    url_row.setSpacing(scaled_px(8))
    url_label = settings_body_label(
        AI_GROUP.text(dialog, "image_gallery.settings.base_url") if hasattr(AI_GROUP, "text") else "API base URL",
        parent=dialog,
    )
    # 150px fits the longest label ("Название модели", 139px at BODY size)
    # in every UI language — narrower clips Cyrillic under the edit.
    url_label.setFixedWidth(scaled_px(150))
    dialog.gallery_ai_base_url_label = url_label
    dialog.gallery_ai_base_url = CustomLineEdit(parent=dialog)
    apply_settings_body(dialog.gallery_ai_base_url)
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
    key_row.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    key_row.setSpacing(scaled_px(8))
    key_label = settings_body_label(
        AI_GROUP.text(dialog, "image_gallery.settings.api_key") if hasattr(AI_GROUP, "text") else "API key",
        parent=dialog,
    )
    key_label.setFixedWidth(scaled_px(150))
    dialog.gallery_ai_api_key_label = key_label
    dialog.gallery_ai_api_key = CustomLineEdit(parent=dialog)
    apply_settings_body(dialog.gallery_ai_api_key)
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
    model_row.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    model_row.setSpacing(scaled_px(8))
    model_label = settings_body_label(
        AI_GROUP.text(dialog, "image_gallery.settings.model_name") if hasattr(AI_GROUP, "text") else "Model name",
        parent=dialog,
    )
    model_label.setFixedWidth(scaled_px(150))
    dialog.gallery_ai_model_label = model_label
    dialog.gallery_ai_model = CustomLineEdit(parent=dialog)
    apply_settings_body(dialog.gallery_ai_model)
    dialog.gallery_ai_model.setText(current.model)
    dialog.gallery_ai_model.setPlaceholderText("openrouter/auto or vendor/model")
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_model, "image_gallery.settings.model_name")
    except Exception:
        pass
    model_row.addWidget(model_label)
    model_row.addWidget(dialog.gallery_ai_model, 1)

    # Ask AI — answer-token budget (0/empty = auto from the scope size).
    tokens_row = QHBoxLayout()
    tokens_row.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    tokens_row.setSpacing(scaled_px(8))
    tokens_label = settings_body_label(
        AI_GROUP.text(dialog, "image_gallery.settings.ask_max_tokens") if hasattr(AI_GROUP, "text") else "Answer token budget",
        parent=dialog,
    )
    tokens_label.setFixedWidth(scaled_px(150))
    dialog.gallery_ai_ask_tokens_label = tokens_label
    dialog.gallery_ai_ask_tokens = CustomLineEdit(parent=dialog)
    apply_settings_body(dialog.gallery_ai_ask_tokens)
    if int(getattr(current, "ask_max_tokens", 0) or 0) > 0:
        dialog.gallery_ai_ask_tokens.setText(str(current.ask_max_tokens))
    dialog.gallery_ai_ask_tokens.setPlaceholderText("auto")
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_ask_tokens, "image_gallery.settings.ask_max_tokens")
    except Exception:
        pass
    tokens_row.addWidget(tokens_label)
    tokens_row.addWidget(dialog.gallery_ai_ask_tokens, 1)

    # Ask AI — reasoning effort (auto keeps a mandatory-reasoning model from
    # spending the whole budget thinking).
    effort_row = QHBoxLayout()
    effort_row.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    effort_row.setSpacing(scaled_px(8))
    effort_label = settings_body_label(
        AI_GROUP.text(dialog, "image_gallery.settings.reasoning_effort") if hasattr(AI_GROUP, "text") else "Reasoning effort",
        parent=dialog,
    )
    effort_label.setFixedWidth(scaled_px(150))
    dialog.gallery_ai_effort_label = effort_label
    dialog.gallery_ai_effort = ComboBox(dialog)
    _effort_labels = []
    for _key, _fallback in zip(_EFFORT_KEYS, _EFFORT_FALLBACKS):
        try:
            _effort_labels.append(AI_GROUP.text(dialog, _key))
        except Exception:
            _effort_labels.append(_fallback)
    try:
        dialog.gallery_ai_effort.addItems(_effort_labels)
    except Exception:
        for _label in _effort_labels:
            dialog.gallery_ai_effort.addItem(_label)
    try:
        _cur_effort = str(getattr(current, "reasoning_effort", "auto") or "auto").lower()
        dialog.gallery_ai_effort.setCurrentIndex(
            _EFFORT_CHOICES.index(_cur_effort) if _cur_effort in _EFFORT_CHOICES else 0
        )
    except Exception:
        pass
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_effort, "image_gallery.settings.reasoning_effort")
    except Exception:
        pass
    effort_row.addWidget(effort_label)
    effort_row.addWidget(dialog.gallery_ai_effort, 1)

    # Image downscale (max edge) for vision calls; 0 = original bytes.
    edge_row = QHBoxLayout()
    edge_row.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    edge_row.setSpacing(scaled_px(8))
    edge_label = settings_body_label(
        AI_GROUP.text(dialog, "image_gallery.settings.vlm_max_edge") if hasattr(AI_GROUP, "text") else "Image downscale (max edge)",
        parent=dialog,
    )
    edge_label.setFixedWidth(scaled_px(150))
    dialog.gallery_ai_edge_label = edge_label
    dialog.gallery_ai_edge = ComboBox(dialog)
    try:
        _original = AI_GROUP.text(dialog, "image_gallery.settings.downscale_original")
    except Exception:
        _original = "Original"
    dialog.gallery_ai_edge.addItems(
        [_original if px <= 0 else f"{px} px" for px in VLM_MAX_EDGES]
    )
    _cur_edge = int(getattr(current, "vlm_max_edge_px", 0) or 0)
    dialog.gallery_ai_edge.setCurrentIndex(
        VLM_MAX_EDGES.index(_cur_edge) if _cur_edge in VLM_MAX_EDGES else 0
    )
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_edge, "image_gallery.settings.vlm_max_edge")
    except Exception:
        pass
    edge_row.addWidget(edge_label)
    edge_row.addWidget(dialog.gallery_ai_edge, 1)

    # One label column for the whole group, sized to the longest translated
    # label — a fixed 150px clipped longer Cyrillic/Portuguese strings.
    try:
        from PySide6.QtGui import QFontMetrics

        _labels = [url_label, key_label, model_label, tokens_label, effort_label, edge_label]
        _need = max(
            QFontMetrics(lbl.font()).horizontalAdvance(lbl.text()) for lbl in _labels
        )
        _col = max(scaled_px(150), _need + scaled_px(10))
        for _lbl in _labels:
            _lbl.setFixedWidth(_col)
    except Exception:
        pass

    # Assemble group rows
    if builder is not None:
        group_widget.add_widget(builder.row(dialog.gallery_ai_enabled))
        # Wrap each QHBoxLayout in a widget row for nav
        group_widget.add_widget(builder.row(url_row))
        group_widget.add_widget(builder.row(key_row))
        group_widget.add_widget(builder.row(model_row))
        group_widget.add_widget(builder.row(tokens_row))
        group_widget.add_widget(builder.row(effort_row))
        group_widget.add_widget(builder.row(edge_row))
        group_widget.add_widget(builder.row(warning))
    else:
        group_widget.add_widget(dialog.gallery_ai_enabled)
        # fallback: add layouts via containers
        for lay in (url_row, key_row, model_row, tokens_row, effort_row, edge_row):
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

    def _save_ask_tokens(text):
        raw = str(text).strip()
        try:
            value = int(raw) if raw else 0
        except Exception:
            value = 0
        _save_field("ask_max_tokens", max(0, value))

    def _save_vlm_edge(index):
        px = VLM_MAX_EDGES[int(index)] if 0 <= int(index) < len(VLM_MAX_EDGES) else 0
        _save_field("vlm_max_edge_px", px)
        vlm.set_vlm_max_edge(px)

    try:
        dialog.gallery_ai_enabled.toggled.connect(lambda v: _save_field("enabled", bool(v)))
        dialog.gallery_ai_base_url.textChanged.connect(lambda t: _save_field("base_url", str(t)))
        dialog.gallery_ai_api_key.textChanged.connect(lambda t: _save_field("api_key", str(t)))
        dialog.gallery_ai_model.textChanged.connect(lambda t: _save_field("model", str(t)))
        dialog.gallery_ai_ask_tokens.textChanged.connect(_save_ask_tokens)
        dialog.gallery_ai_effort.currentIndexChanged.connect(
            lambda i: _save_field(
                "reasoning_effort",
                _EFFORT_CHOICES[i] if 0 <= int(i) < len(_EFFORT_CHOICES) else "auto",
            )
        )
        dialog.gallery_ai_edge.currentIndexChanged.connect(_save_vlm_edge)
    except Exception:
        pass

    # Also hook dialog accept to ensure last values flushed
    orig_get_settings = getattr(dialog, "confirm_settings", None)

    # Persist via registry payload reader/seeder for consistency with tab_extras
    # Read payload from dialog widgets
    def _read_payload(_dialog):
        try:
            tokens_raw = str(_dialog.gallery_ai_ask_tokens.text()).strip()
            try:
                tokens = max(0, int(tokens_raw)) if tokens_raw else 0
            except Exception:
                tokens = 0
            idx = int(_dialog.gallery_ai_effort.currentIndex())
            effort = _EFFORT_CHOICES[idx] if 0 <= idx < len(_EFFORT_CHOICES) else "auto"
            edge_idx = int(_dialog.gallery_ai_edge.currentIndex())
            edge = VLM_MAX_EDGES[edge_idx] if 0 <= edge_idx < len(VLM_MAX_EDGES) else 0
            return {
                "enabled": bool(_dialog.gallery_ai_enabled.isChecked()),
                "base_url": str(_dialog.gallery_ai_base_url.text()).strip(),
                "api_key": str(_dialog.gallery_ai_api_key.text()),
                "model": str(_dialog.gallery_ai_model.text()).strip(),
                "ask_max_tokens": tokens,
                "reasoning_effort": effort,
                "vlm_max_edge_px": edge,
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
                return {
                    "enabled": cur.enabled,
                    "base_url": cur.base_url,
                    "api_key": cur.api_key,
                    "model": cur.model,
                    "ask_max_tokens": cur.ask_max_tokens,
                    "reasoning_effort": cur.reasoning_effort,
                    "vlm_max_edge_px": cur.vlm_max_edge_px,
                }
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

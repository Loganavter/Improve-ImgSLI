"""Stage 2/3 AI settings page — provider / base_url / api_key / model.
Audit-Meta: pattern=settings-page size=exempt reason="one AI settings page builder: provider/model rows, live persistence and the Apply offer hook share the dialog widget namespace; a split would need a second ui/ module for the same page"

Returns with Stage 2 per design.md anchors: ``plugins/settings`` contribution
path for API settings (``ui/settings_ai.py`` returns with stage 2).

The page names a PROVIDER (``services/ai_providers``: openrouter / openai /
llamacpp / custom) instead of asking the user to type one free URL: a provider
owns its default endpoint, a curated fallback catalog and a default model, so a
switch can replace a model the new provider does not serve. The model picker
lists what the provider actually serves — ``GET {base_url}/models`` through
``services/ai_models.models_for`` (network → 24 h cache → curated fallback),
fetched OFF the GUI thread so an unreachable endpoint never freezes the dialog —
and the status line says where the list came from (and why it fell back).

The model value stays a text field (``CustomLineEdit``) plus a discovery combo
beside it: the toolkit ``ComboBox`` is a painter-pipeline Button-based control
with no editable text entry, so there is no "editable combo" equivalent to use
(toolkit-first rule; stock ``QComboBox`` would bypass the painter pipeline).
Picking from the combo fills the field; typing stays possible for a model the
endpoint does not list.

On Apply, a change to the analysis identity (model / base_url / profile /
effort / mode) offers to re-analyze the existing results — see
``use_cases/ai_analysis.offer_reanalysis``.

Uses QSettings via ``AiSettingsStore`` — no Redux path (8-file cost for a setting
nothing else needs to react to). Section is ambient (always visible) like other
per-tab settings. ``SettingsContribution`` with section ``image_gallery.ai``.

Painter pipeline only: CustomGroupWidget, CustomLineEdit, CheckBox, ComboBox,
Button, no setStyleSheet.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtCore import QThreadPool

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, CheckBox, ComboBox, CustomLineEdit

from plugins.settings.typography import (
    apply_settings_body,
    settings_body_label,
    settings_caption_label,
    settings_group,
)

from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group
from tabs.image_gallery.services import ai_models, ai_providers, vlm
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

#: Named discovery failures → the status line's reason text.
_REASON_KEYS = {
    ai_models.REASON_AUTH: (
        "image_gallery.settings.models_reason_auth",
        "the key was rejected",
    ),
    ai_models.REASON_NETWORK: (
        "image_gallery.settings.models_reason_network",
        "no connection",
    ),
    ai_models.REASON_HTTP: (
        "image_gallery.settings.models_reason_http",
        "the endpoint returned an error",
    ),
    ai_models.REASON_PARSE: (
        "image_gallery.settings.models_reason_parse",
        "the answer was unreadable",
    ),
    ai_models.REASON_NO_BASE_URL: (
        "image_gallery.settings.models_reason_no_base_url",
        "no base URL yet",
    ),
}

AI_GROUP = group(
    "image_gallery.settings.ai_title",
    "image_gallery.settings.enable_ai",
    "image_gallery.settings.provider",
    "image_gallery.settings.provider_openrouter",
    "image_gallery.settings.provider_openai",
    "image_gallery.settings.provider_llamacpp",
    "image_gallery.settings.provider_custom",
    "image_gallery.settings.base_url",
    "image_gallery.settings.api_key",
    "image_gallery.settings.model_name",
    "image_gallery.settings.refresh_models",
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

logger = logging.getLogger("ImproveImgSLI")


def _start_thread_task(task, on_done):
    """Run *task* off the GUI thread; deliver ``on_done(result)`` on it.

    The settings dialog must stay responsive while an endpoint is probed: a
    local llama.cpp server that is not running would otherwise freeze the page
    for the whole HTTP timeout on every open. Errors are delivered as
    ``None`` — the caller degrades to the curated fallback.
    """
    from sli_ui_toolkit.workers import GenericWorker

    worker = GenericWorker(task)
    worker.signals.result.connect(on_done)
    worker.signals.error.connect(lambda _error: on_done(None))
    QThreadPool.globalInstance().start(worker)
    return worker


def _live_gallery_owner():
    """The live gallery controller, or None (settings can open without one)."""
    try:
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        session_types = list(registry.registered_types)
    except Exception:
        return None
    for session_type in session_types:
        if "gallery" not in str(session_type):
            continue
        try:
            tab = registry.get_tab(session_type)
        except Exception:
            continue
        controller = getattr(tab, "_controller", None) if tab is not None else None
        if controller is not None:
            return controller
    return None


def _identity_snapshot(owner):
    """The analysis cache identity of *owner*'s current configuration."""
    if owner is None:
        return None
    try:
        from tabs.image_gallery.use_cases.ai_analyze import analysis_identity_for

        return dict(analysis_identity_for(owner))
    except Exception:
        return None


def _offer_reanalysis(owner, *, old_identity, new_identity, parent=None):
    """The Apply-time offer (``use_cases/ai_analysis.offer_reanalysis``)."""
    from tabs.image_gallery.use_cases.ai_analysis import offer_reanalysis

    return offer_reanalysis(
        owner,
        old_identity=old_identity,
        new_identity=new_identity,
        parent=parent,
    )


#: Test seams — replaced by the tests (no network, no app, no dialog).
MODELS_FOR = ai_models.models_for
START_TASK = _start_thread_task
GALLERY_OWNER = _live_gallery_owner
OFFER_REANALYSIS = _offer_reanalysis


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
    #: Qt workers kept alive until they report (a garbage-collected worker
    #: never delivers its result).
    dialog._gallery_ai_model_tasks = []

    def _tr(key: str, default: str) -> str:
        """Section-key lookup via the dialog translator (fail-open to *default*).

        ``AI_GROUP.text`` returns the raw key when unresolved, so fall back on
        a non-str / empty / key-echo result — placeholders always render.
        """
        try:
            val = AI_GROUP.text(dialog, key) if hasattr(AI_GROUP, "text") else default
        except Exception:
            val = default
        return val if isinstance(val, str) and val and val != key else default

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

    # Provider (above base_url: it owns the URL, the fallback catalog and the
    # default model, so it must be read first).
    provider = ai_providers.provider_by_id(current.provider_id)
    provider_row = QHBoxLayout()
    provider_row.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    provider_row.setSpacing(scaled_px(8))
    provider_label = settings_body_label(
        _tr("image_gallery.settings.provider", "Provider"), parent=dialog
    )
    provider_label.setFixedWidth(scaled_px(150))
    dialog.gallery_ai_provider_label = provider_label
    dialog.gallery_ai_provider = ComboBox(dialog)
    apply_settings_body(dialog.gallery_ai_provider)
    for _provider in ai_providers.PROVIDERS:
        try:
            dialog.gallery_ai_provider.addItem(
                _tr(_provider.label_key, _provider.id), _provider.id
            )
            AI_GROUP.note_combo_option(dialog.gallery_ai_provider, _provider.label_key)
        except Exception:
            continue
    try:
        AI_GROUP.tag_combo(dialog.gallery_ai_provider, "image_gallery.settings.provider")
    except Exception:
        pass
    try:
        _provider_index = dialog.gallery_ai_provider.findData(provider.id)
        dialog.gallery_ai_provider.setCurrentIndex(max(0, int(_provider_index)))
    except Exception:
        pass
    provider_row.addWidget(provider_label)
    provider_row.addWidget(dialog.gallery_ai_provider, 1)

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
    dialog.gallery_ai_base_url.setText(
        current.base_url or provider.base_url or DEFAULT_BASE_URL
    )
    dialog.gallery_ai_base_url.setPlaceholderText(DEFAULT_BASE_URL)
    # A preset owns its endpoint: the field is read-only unless the provider is
    # the free-form `custom` one (then the user types the URL).
    try:
        dialog.gallery_ai_base_url.setReadOnly(not ai_providers.is_custom(provider))
    except Exception:
        pass
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
    dialog.gallery_ai_api_key.setPlaceholderText(
        _tr("image_gallery.settings.api_key_placeholder", "sk-…")
    )
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

    # Model: the editable value plus the provider's discovered list beside it.
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
    dialog.gallery_ai_model.setText(current.model or provider.default_model)
    dialog.gallery_ai_model.setPlaceholderText(
        _tr("image_gallery.settings.model_placeholder", "openrouter/auto or vendor/model")
    )
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_model, "image_gallery.settings.model_name")
    except Exception:
        pass
    dialog.gallery_ai_model_list = ComboBox(dialog)
    apply_settings_body(dialog.gallery_ai_model_list)
    try:
        AI_GROUP.tag_member(dialog.gallery_ai_model_list, "image_gallery.settings.model_name")
    except Exception:
        pass
    dialog.gallery_ai_refresh = Button(
        text=_tr("image_gallery.settings.refresh_models", "Refresh list"),
        variant="surface",
        parent=dialog,
    )
    try:
        dialog.gallery_ai_refresh.setMinimumHeight(scaled_px(30))
        AI_GROUP.tag_member(dialog.gallery_ai_refresh, "image_gallery.settings.refresh_models")
    except Exception:
        pass
    model_row.addWidget(model_label)
    model_row.addWidget(dialog.gallery_ai_model, 2)
    model_row.addWidget(dialog.gallery_ai_model_list, 2)
    model_row.addWidget(dialog.gallery_ai_refresh, 0)

    # Where the list came from (network / cache / curated) + why it fell back.
    dialog.gallery_ai_models_status = settings_caption_label("", parent=dialog)
    try:
        dialog.gallery_ai_models_status.setWordWrap(True)
    except Exception:
        pass
    status_row = QHBoxLayout()
    status_row.setContentsMargins(scaled_px(150) + scaled_px(8), 0, 0, scaled_px(4))
    status_row.setSpacing(0)
    status_row.addWidget(dialog.gallery_ai_models_status, 1)

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
    dialog.gallery_ai_ask_tokens.setPlaceholderText(
        _tr("image_gallery.settings.tokens_placeholder", "auto")
    )
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

        _labels = [
            provider_label,
            url_label,
            key_label,
            model_label,
            tokens_label,
            effort_label,
            edge_label,
        ]
        _need = max(
            QFontMetrics(lbl.font()).horizontalAdvance(lbl.text()) for lbl in _labels
        )
        _col = max(scaled_px(150), _need + scaled_px(10))
        for _lbl in _labels:
            _lbl.setFixedWidth(_col)
        status_row.setContentsMargins(_col + scaled_px(8), 0, 0, scaled_px(4))
    except Exception:
        pass

    # Assemble group rows
    if builder is not None:
        group_widget.add_widget(builder.row(dialog.gallery_ai_enabled))
        # Wrap each QHBoxLayout in a widget row for nav
        group_widget.add_widget(builder.row(provider_row))
        group_widget.add_widget(builder.row(url_row))
        group_widget.add_widget(builder.row(key_row))
        group_widget.add_widget(builder.row(model_row))
        group_widget.add_widget(builder.row(status_row))
        group_widget.add_widget(builder.row(tokens_row))
        group_widget.add_widget(builder.row(effort_row))
        group_widget.add_widget(builder.row(edge_row))
        group_widget.add_widget(builder.row(warning))
    else:
        group_widget.add_widget(dialog.gallery_ai_enabled)
        # fallback: add layouts via containers
        for lay in (
            provider_row,
            url_row,
            key_row,
            model_row,
            status_row,
            tokens_row,
            effort_row,
            edge_row,
        ):
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

    # Current provider id (kept so the OLD provider's model is remembered when
    # the combo moves: the text field still holds that model at that moment).
    state = {"provider_id": provider.id}

    def _selected_provider():
        try:
            data = dialog.gallery_ai_provider.currentData()
        except Exception:
            data = None
        return ai_providers.provider_by_id(data or state["provider_id"])

    def _reason_text(reason: str) -> str:
        key, default = _REASON_KEYS.get(
            reason, ("image_gallery.settings.models_reason_http", "the endpoint failed")
        )
        return _tr(key, default)

    def _status_text(count: int, source: str, reason: str) -> str:
        if source == ai_models.SOURCE_NETWORK:
            text = _tr(
                "image_gallery.settings.models_from_network",
                "Model list loaded from the provider ({count}).",
            )
        elif source == ai_models.SOURCE_CACHE and reason:
            text = _tr(
                "image_gallery.settings.models_from_cache_stale",
                "Provider unreachable ({reason}) — showing the cached list ({count}).",
            )
        elif source == ai_models.SOURCE_CACHE:
            text = _tr(
                "image_gallery.settings.models_from_cache",
                "Model list from the local cache ({count}).",
            )
        elif not count:
            return _tr(
                "image_gallery.settings.models_none",
                "No model list — type a model name.",
            )
        else:
            text = _tr(
                "image_gallery.settings.models_from_curated",
                "Built-in fallback list ({count}) — not the provider's catalog.",
            )
        try:
            return text.format(count=count, reason=_reason_text(reason))
        except (KeyError, ValueError, IndexError):
            return text

    def _fill_model_list(models, source: str, reason: str) -> None:
        """Populate the discovery combo; the edit keeps the persisted value."""
        sync_busy["on"] = True
        try:
            dialog.gallery_ai_model_list.clear()
            for model in models:
                try:
                    dialog.gallery_ai_model_list.addItem(model, model)
                except Exception:
                    continue
            current_model = str(dialog.gallery_ai_model.text()).strip()
            index = -1
            if current_model:
                try:
                    index = int(dialog.gallery_ai_model_list.findText(current_model))
                except Exception:
                    index = -1
            if models:
                dialog.gallery_ai_model_list.setCurrentIndex(max(0, index))
        finally:
            sync_busy["on"] = False
        dialog.gallery_ai_models_status.setText(
            _status_text(len(models), source, reason)
        )

    sync_busy = {"on": False}

    def _refresh_models(*, refresh: bool = False) -> None:
        """Fetch the provider's list off the GUI thread (never blocks the page)."""
        prov = _selected_provider()
        api_key = str(dialog.gallery_ai_api_key.text())
        report: dict = {}
        dialog.gallery_ai_models_status.setText(
            _tr("image_gallery.settings.models_loading", "Loading the model list…")
        )

        def _task():
            try:
                return MODELS_FOR(
                    prov, api_key, refresh=refresh, report=report
                )
            except Exception:
                return (), ai_models.SOURCE_CURATED

        def _done(result) -> None:
            try:
                models, source = result if result else ((), ai_models.SOURCE_CURATED)
            except Exception:
                models, source = (), ai_models.SOURCE_CURATED
            try:
                _fill_model_list(
                    tuple(models or ()),
                    str(source or ai_models.SOURCE_CURATED),
                    str(report.get("reason") or ""),
                )
            except Exception:
                logger.debug("AI model list apply failed", exc_info=True)

        try:
            handle = START_TASK(_task, _done)
            if handle is not None:
                dialog._gallery_ai_model_tasks.append(handle)
        except Exception:
            _done(None)

    def _on_model_list_picked(index) -> None:
        if sync_busy["on"]:
            return
        try:
            text = str(dialog.gallery_ai_model_list.currentText() or "").strip()
        except Exception:
            text = ""
        if text:
            dialog.gallery_ai_model.setText(text)

    def _remember_current_model(text) -> None:
        _save_field("model", str(text))
        pid = state["provider_id"]
        if pid and str(text).strip():
            try:
                store.remember_model(pid, str(text))
            except Exception:
                pass

    def _apply_provider() -> None:
        prov = _selected_provider()
        # Remember the outgoing provider's model before the fields move.
        outgoing = state["provider_id"]
        outgoing_model = str(dialog.gallery_ai_model.text()).strip()
        if outgoing and outgoing_model:
            try:
                store.remember_model(outgoing, outgoing_model)
            except Exception:
                pass
        state["provider_id"] = prov.id
        target_url = prov.base_url or str(dialog.gallery_ai_base_url.text()).strip()
        if prov.base_url:
            dialog.gallery_ai_base_url.setText(prov.base_url)
        try:
            dialog.gallery_ai_base_url.setReadOnly(not ai_providers.is_custom(prov))
        except Exception:
            pass
        model = ai_providers.model_for(prov, store.model_for(prov.id))
        dialog.gallery_ai_model.setText(model)
        try:
            store.save_provider(prov.id, target_url, model)
        except Exception:
            pass
        _refresh_models(refresh=False)

    try:
        dialog.gallery_ai_enabled.toggled.connect(lambda v: _save_field("enabled", bool(v)))
        dialog.gallery_ai_base_url.textChanged.connect(lambda t: _save_field("base_url", str(t)))
        dialog.gallery_ai_api_key.textChanged.connect(lambda t: _save_field("api_key", str(t)))
        dialog.gallery_ai_model.textChanged.connect(_remember_current_model)
        dialog.gallery_ai_ask_tokens.textChanged.connect(_save_ask_tokens)
        dialog.gallery_ai_provider.currentIndexChanged.connect(
            lambda _i: _apply_provider()
        )
        dialog.gallery_ai_model_list.currentIndexChanged.connect(_on_model_list_picked)
        dialog.gallery_ai_refresh.clicked.connect(lambda: _refresh_models(refresh=True))
        dialog.gallery_ai_effort.currentIndexChanged.connect(
            lambda i: _save_field(
                "reasoning_effort",
                _EFFORT_CHOICES[i] if 0 <= int(i) < len(_EFFORT_CHOICES) else "auto",
            )
        )
        dialog.gallery_ai_edge.currentIndexChanged.connect(_save_vlm_edge)
    except Exception:
        pass

    # Initial list (cache first — ``models_for`` only calls out on a stale/empty
    # cache or an explicit refresh).
    _refresh_models(refresh=False)

    # Apply offer: a changed analysis identity (model / base_url / profile /
    # effort / mode) means the existing scorecards belong to the old
    # configuration — offer to redo them (use_cases/ai_analysis).
    apply_state = {"identity": _identity_snapshot(GALLERY_OWNER())}

    def _on_settings_confirmed() -> None:
        old_identity = apply_state.get("identity")
        if not isinstance(old_identity, dict):
            return
        owner = GALLERY_OWNER()
        new_identity = _identity_snapshot(owner)
        if owner is None or new_identity is None:
            return
        try:
            OFFER_REANALYSIS(
                owner,
                old_identity=old_identity,
                new_identity=new_identity,
                parent=dialog,
            )
        except Exception:
            logger.debug("re-analyze offer after settings change failed", exc_info=True)
        apply_state["identity"] = new_identity

    try:
        dialog.settings_confirmed.connect(_on_settings_confirmed)
    except Exception:
        pass

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
                "provider_id": _selected_provider().id,
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
                    "provider_id": cur.provider_id,
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

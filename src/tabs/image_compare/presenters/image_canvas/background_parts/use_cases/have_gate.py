"""Have gate — have1/have2 wait + live-half paint.

Extracted from ``use_cases/render_gate.py`` per ``docs/dev/CODE_PATTERNS.md``
thin owner + ``use_cases/`` and ``docs/dev/FILE_SIZE_POLICY.md`` (500L).
The orchestrator owns the sequencing, this module owns the have1/have2
wait decision and the live-half paint (preview-backed single-side
display). All functions take ``presenter`` as first argument.
"""

from __future__ import annotations

from shared.rendering.image_identity import image_uid
from tabs.image_compare.debug import ic_preview_debug as _preview_log

from .preview import _update_preview_tracking

_last_one_side_log_sig = None  # type: ignore  # throttle — owns the one-side log decision


def _peek_sources(presenter, document):
    """Resolve (pixel, preview) per slot via PipelineCache / PipelineView.

    Mirrors ``render_gate.py:131`` peek helpers — kept here as the gate's
    source-resolution preamble before geometry. Single place to swap to
    ``_peek``/``_peek_pixel``/``_peek_preview`` once background lands.
    """
    _pl = None
    _path1 = getattr(document, "image1_path", None)
    _path2 = getattr(document, "image2_path", None)
    try:
        _ctrl = getattr(presenter, "session_controller", None) or getattr(presenter, "controller", None)
        if _ctrl is None:
            try:
                from tabs.image_compare.pipeline.cache import PipelineCache as _PC  # noqa: F401

                _mw = getattr(presenter, "main_window_app", None)
                if _mw is not None:
                    _tab = getattr(getattr(_mw, "tab_registry", None), "get_tab", lambda *_a, **_kw: None)("image_compare")
                    _ctrl = getattr(_tab, "session_controller", None) if _tab else None
            except Exception:
                _ctrl = None
        _pl = getattr(_ctrl, "pipeline", None) if _ctrl is not None else None
    except Exception:
        _pl = None

    def _peek(path):
        if _pl is not None and path:
            try:
                c = _pl.peek(path)
                if c is not None and getattr(c, "is_open", True):
                    if hasattr(c, "isNull"):
                        try:
                            if not c.isNull():
                                return c
                        except Exception:
                            return c
                    else:
                        return c
            except Exception:
                pass
            try:
                p = _pl.peek_preview(path)
                if p is not None:
                    if hasattr(p, "isNull"):
                        try:
                            if not p.isNull():
                                return p
                        except Exception:
                            return p
                    else:
                        return p
            except Exception:
                pass
        return None

    def _peek_pixel(path):
        if _pl is not None and path:
            try:
                return _pl.peek(path)
            except Exception:
                return None
        return None

    def _peek_preview(path):
        if _pl is not None and path:
            try:
                return _pl.peek_preview(path)
            except Exception:
                return None
        return None

    _peeked_pixel1 = _peek_pixel(_path1)
    _peeked_pixel2 = _peek_pixel(_path2)
    _peeked_preview1 = _peek_preview(_path1)
    _peeked_preview2 = _peek_preview(_path2)
    _img_state = presenter.store.viewport.session_data.image_state
    source1 = _peeked_pixel1 or _peeked_preview1 or getattr(_img_state, "image1", None) or _peek(_path1)
    source2 = _peeked_pixel2 or _peeked_preview2 or getattr(_img_state, "image2", None) or _peek(_path2)
    return {
        "path1": _path1,
        "path2": _path2,
        "peeked_pixel1": _peeked_pixel1,
        "peeked_pixel2": _peeked_pixel2,
        "peeked_preview1": _peeked_preview1,
        "peeked_preview2": _peeked_preview2,
        "source1": source1,
        "source2": source2,
        "pipeline": _pl,
    }


def _have_gate(presenter, source1, source2, document):
    """Have1/have2 wait gate — one-side missing handling.

    Returns (have1, have2, should_return, reason). When ``should_return`` is
    True, caller should return ``False`` (deferred) — either waiting for the
    other side or having just painted the live half via
    ``display_single_image_on_label``. Delegates the live-half pick to
    ``preview`` helpers once background lands; until then keeps the existing
    ``render_flow`` live-half path inline (marked TODO).
    """
    have1 = bool(presenter.store.viewport.session_data.image_state.image1 or source1)
    have2 = bool(presenter.store.viewport.session_data.image_state.image2 or source2)
    if not have1 and not have2:
        _preview_log("update: no sources on either side - label cleared")
        presenter.widget.image_label.clear()
        presenter.current_displayed_pixmap = None
        return have1, have2, True, "no_sources"
    if not have1 or not have2:
        global _last_one_side_log_sig
        try:
            other_list_empty = len(document.image_list2) == 0 if have1 else len(document.image_list1) == 0
        except AttributeError:
            other_list_empty = False
        other_has_path = (document.image2_path is not None) if have1 else (document.image1_path is not None)
        try:
            _pending = getattr(presenter.store, "_pending_image_loads", None)  # type: ignore[attr-defined]
            _ctrl = getattr(presenter, "controller", None) or getattr(presenter, "_controller", None)
            if _ctrl is None:
                _w = getattr(presenter, "widget", None)
                _ctrl = getattr(_w, "_controller", None) if _w is not None else None
            has_pending_other = False
            if _pending:
                other_slot = 2 if have1 else 1
                has_pending_other = any(slot == other_slot for slot, _p in _pending)
            elif _ctrl is not None:
                _cp = getattr(_ctrl, "_pending_image_loads", None)
                if _cp:
                    other_slot = 2 if have1 else 1
                    has_pending_other = any(slot == other_slot for slot, _p in _cp)
            else:
                has_pending_other = False
        except Exception:
            has_pending_other = False
        if other_list_empty or other_has_path or has_pending_other:
            _one_side_sig = (have1, have2, image_uid(source1) if source1 else None, image_uid(source2) if source2 else None, other_list_empty, other_has_path, has_pending_other)
            if _one_side_sig != _last_one_side_log_sig:
                _last_one_side_log_sig = _one_side_sig
                _preview_log(
                    "update: one side missing (have1=%s have2=%s) - wait for other side (other_empty=%s other_has_path=%s pending_other=%s)",
                    have1, have2, other_list_empty, other_has_path, has_pending_other,
                )
            return have1, have2, True, "wait_other_side"
        # live-half paint — TODO(background): delegate to preview.pick_live_half
        return have1, have2, False, "live_half"
    return have1, have2, False, "dual"


def handle_have_gate(presenter, source1, source2, document, peeked) -> bool:
    """Evaluate have gate and handle live-half paint if needed.

    Returns True if the caller should early-return ``False`` (deferred /
    no sources / wait / live-half painted), False to continue to the
    background branch. Preserves the ``[ic-preview]`` throttled logs and
    ``_last_one_side_log_sig`` throttle owned by this module.
    """
    have1, have2, _should, reason = _have_gate(presenter, source1, source2, document)
    if reason == "no_sources":
        return True
    if reason == "wait_other_side":
        return True
    if reason == "live_half":
        # live-half paint — mirrors render_gate.py:400-421 / render_flow:781-802
        from shared.rendering.display_image_picker import pick_display_image as _pick

        global _last_one_side_log_sig
        _one_side_sig = (have1, have2, image_uid(source1) if source1 else None, image_uid(source2) if source2 else None)
        if _one_side_sig != _last_one_side_log_sig:
            _last_one_side_log_sig = _one_side_sig
            _preview_log("update: one side missing (have1=%s have2=%s) - display live half", have1, have2)
        image_to_show = (
            _pick(presenter.store.viewport.session_data.image_state.image1, source1, peeked["peeked_preview1"], None)
            if have1
            else _pick(presenter.store.viewport.session_data.image_state.image2, source2, peeked["peeked_preview2"], None)
        )
        presenter.view.display_single_image_on_label(image_to_show)
        try:
            slot = 1 if have1 else 2
            if image_to_show is not None:
                _update_preview_tracking(presenter, {slot: image_to_show})
        except Exception:
            pass
        return True
    return False

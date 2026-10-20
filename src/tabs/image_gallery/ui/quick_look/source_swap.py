"""Quick Look source inset → MAIN preview swap (hover / LMB press).

Task ``task-gallery-quicklook-source-screen-2026-10-12`` (follows
plan-gallery-ql-source-canvas / 964600d2): the inset already SHARES the
preview's single ``ViewportState``; this module adds the missing INTERACTION —
hovering the inset plate shows the SOURCE image in the MAIN preview, leaving
restores, and an LMB press makes the swap temporary until release.

Split out of ``source_canvas.py`` (500-line contract gate, CODE_PATTERNS.md
thin owner): the canvas/store/plate lifecycle stays there, the plate hit
target + preview swap live here. Import paths for the lifecycle are unchanged.

Constraints kept here:

- Hit target is the plate ``Button`` (``overlay._source_inset_pix``), the only
  non-transparent child of the inset block. The engine canvas/cover/clip frame
  stay ``WA_TransparentForMouseEvents`` + NoFocus and the inset stays outside
  the section graph (docs/dev/KEYBOARD_NAVIGATION.md §9) — a VIEW, not a
  control, so no focus/nav/section registration is added.
- ONE viewport: the swap calls ``set_source(..., preserve_view=True)`` on the
  main canvas, so zoom/pan are neither reset nor duplicated — wheel/pan while
  swapped keeps operating the shared state (the inset reads it too).
- No new public widget API: an installed event filter on the existing plate,
  returning False always (the plate keeps its own hover/click handling).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt


def _item_path(item):
    """``str(item.path)`` or None (fail-open)."""
    try:
        raw = getattr(item, "path", None)
        return str(raw) if raw else None
    except Exception:
        return None


def _inset_store(overlay):
    """The inset's open memoized coarse store, or None (fail-open)."""
    try:
        store = getattr(overlay, "_source_inset_store", None)
        if store is None:
            return None
        try:
            if not bool(getattr(store, "is_open", True)):
                return None
        except Exception:
            pass
        return store
    except Exception:
        return None


def _set_swap_flag(overlay, attr, value) -> None:
    try:
        setattr(overlay, attr, value)
    except Exception:
        pass


def reset_source_swap(overlay) -> None:
    """Forget the swap state without touching a canvas (populate / release).

    Every caller repopulates the preview first (``_populate`` runs
    ``populate_preview`` before ``populate_source_inset``; the release paths
    clear/replace the preview canvas themselves), so clearing the flags is
    enough: no restore is owed and none may land on the next item.
    """
    _set_swap_flag(overlay, "_source_swap_active", False)
    _set_swap_flag(overlay, "_source_swap_hover", False)
    _set_swap_flag(overlay, "_source_swap_pressed", False)
    _set_swap_flag(overlay, "_source_swap_store", None)
    _set_swap_flag(overlay, "_source_swap_path", None)


def _install_inset_store_guard(overlay, main) -> None:
    """Let the preview canvas hold the inset store WITHOUT closing it.

    ``QuickLookCanvasWidget.set_source`` closes the store it drops unless the
    host's ``_ql_is_memo`` probe says the memo cache owns it. The inset store
    lives in its own one-entry memo (``source_store_for``), outside the preview
    cache — so the probe is widened once per preview canvas: an inset-owned
    store is a memo store too. Idempotent, never raises.
    """
    try:
        if getattr(main, "_ql_inset_guard", False):
            return
        prev = getattr(main, "_ql_is_memo", None)

        def _probe(store, _ov=overlay, _prev=prev):
            try:
                if store is not None and getattr(_ov, "_source_inset_store", None) is store:
                    return True
            except Exception:
                pass
            if callable(_prev):
                try:
                    return bool(_prev(store))
                except Exception:
                    return False
            return False

        main._ql_is_memo = _probe
        main._ql_inset_guard = True
    except Exception:
        pass


def _note_ql_source(canvas, path) -> None:
    """Re-arm the demand-pyramid source for *path* (never raises)."""
    try:
        note = getattr(canvas, "note_ql_source", None)
        if callable(note) and path:
            note(str(path))
    except Exception:
        pass


def set_source_swap(overlay, active: bool) -> bool:
    """Show the SOURCE in the main preview (*active*) or restore the item.

    Pixels only: ``preserve_view=True`` leaves the SHARED ``ViewportState``
    untouched (the inset reads the same state, so both surfaces stay in
    lock-step and wheel/pan keep operating it while swapped). The source is
    rendered from the inset's already-open coarse store — a hover costs no
    decode and materializes no second store.

    Restore hands the viewed item's store back (still held in
    ``overlay._preview_store``, memo-owned so the swap never closed it); when
    the view moved during the swap (a walk) or the store was retired, the
    production preview path repopulates instead. Never raises; True means the
    preview is in the requested state.

    The tiled full-store kick is deliberately NOT re-staged by a swap (it
    re-arms on the next populate): ``note_ql_source`` keeps the demand pyramid
    alive for sharp zoom, and a hover must never start a full background
    decode of the item it just restored.
    """
    try:
        active = bool(active)
        if bool(getattr(overlay, "_source_swap_active", False)) == active:
            return True
        main = getattr(overlay, "_preview_canvas", None)
        if main is None:
            return False
        if active:
            store = _inset_store(overlay)
            src_path = getattr(overlay, "_source_inset_path", None)
            if store is None or not src_path:
                return False
            # Remember what to restore BEFORE the canvas drops the item store.
            _set_swap_flag(overlay, "_source_swap_store", getattr(overlay, "_preview_store", None))
            _set_swap_flag(
                overlay,
                "_source_swap_path",
                _item_path(getattr(overlay, "_current_item", None)),
            )
            _install_inset_store_guard(overlay, main)
            try:
                main.set_source(store, preserve_view=True)
            except Exception:
                return False
            _note_ql_source(main, src_path)
            _set_swap_flag(overlay, "_source_swap_active", True)
            return True
        cur_item = getattr(overlay, "_current_item", None)
        cur_path = _item_path(cur_item)
        store = getattr(overlay, "_source_swap_store", None)
        swap_path = getattr(overlay, "_source_swap_path", None)
        restored = False
        if store is not None and swap_path is not None and cur_path == swap_path:
            try:
                still_open = bool(getattr(store, "is_open", True))
            except Exception:
                still_open = True
            if still_open:
                try:
                    main.set_source(store, preserve_view=True)
                    _note_ql_source(main, cur_path)
                    restored = True
                except Exception:
                    restored = False
        if not restored and cur_item is not None:
            # The view moved during the swap (walk) or the held store was
            # retired: the production populate is the source of truth.
            try:
                from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                    _populate_preview_canvas,
                )

                restored = bool(
                    _populate_preview_canvas(overlay, cur_item, preserve_view=True)
                )
            except Exception:
                restored = False
        _set_swap_flag(overlay, "_source_swap_active", False)
        _set_swap_flag(overlay, "_source_swap_store", None)
        _set_swap_flag(overlay, "_source_swap_path", None)
        return restored
    except Exception:
        return False


class _InsetPlateSwapFilter(QObject):
    """Enter/Leave + LMB press/release on the source plate → preview swap.

    Watches the plate ONLY: the engine canvas, cover and rounded clip frame
    are ``WA_TransparentForMouseEvents`` (their events land on the plate, the
    parent), and the title/caption region is a different widget — hovering it
    does nothing. Returns False always: the plate keeps its own handling
    (hover wash, future click callbacks) untouched.
    """

    def __init__(self, overlay, plate) -> None:
        super().__init__(plate)
        self._overlay = overlay
        self._plate = plate

    def eventFilter(self, watched, event):  # noqa: N802 (Qt override)
        try:
            if watched is not self._plate:
                return False
            kind = event.type()
            if kind == QEvent.Type.Enter:
                _set_swap_flag(self._overlay, "_source_swap_hover", True)
                set_source_swap(self._overlay, True)
            elif kind == QEvent.Type.Leave:
                _set_swap_flag(self._overlay, "_source_swap_hover", False)
                if not bool(getattr(self._overlay, "_source_swap_pressed", False)):
                    set_source_swap(self._overlay, False)
            elif kind == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    # Press owns the swap: a later Leave must not end it.
                    _set_swap_flag(self._overlay, "_source_swap_pressed", True)
                    set_source_swap(self._overlay, True)
            elif kind == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    _set_swap_flag(self._overlay, "_source_swap_pressed", False)
                    if not bool(getattr(self._overlay, "_source_swap_hover", False)):
                        set_source_swap(self._overlay, False)
        except Exception:
            pass
        return False


def ensure_source_inset_swap(overlay) -> bool:
    """Install the plate swap filter once (idempotent, fail-open)."""
    try:
        if getattr(overlay, "_source_inset_swap_filter", None) is not None:
            return True
    except Exception:
        pass
    try:
        # Lazy: the plate accessor lives with the canvas/plate lifecycle.
        from tabs.image_gallery.ui.quick_look.source_canvas import _plate

        plate = _plate(overlay)
    except Exception:
        return False
    if plate is None:
        return False
    try:
        swap_filter = _InsetPlateSwapFilter(overlay, plate)
        plate.installEventFilter(swap_filter)
        overlay._source_inset_swap_filter = swap_filter
        return True
    except Exception:
        return False

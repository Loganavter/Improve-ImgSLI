"""QDrag delivery of gallery cards onto the workspace tab strip (Wave C).

The strip (``ui/widgets/workspace_tab_strip.py``) stays a thin owner: it
only claims the card-drag mime on enter/move and delegates drop events here
via ``set_qdrag_drop_handler``. All routing lives in this module and mirrors
``events.image_carry.ImageCarryService._try_deliver_to_workspace_tab``
exactly (same tab_bar.mapFromGlobal → tabAt → tabData → session →
``accepts_drop`` → session switch → deferred ``_schedule_pending_insert``),
because a QDrag carries the same ``(paths, global_pos)`` facts as an image
carry — only the gesture differs.

Platform-isolation note: this file is host code, so it never names a
concrete tab and never imports past ``tabs.registry`` (contracts:
``test_platform_isolation``, ``test_ui_tab_sandbox``). The card mime below
is a wire-format mirror — the single definition lives tab-side and
``test_gallery_dnd_delivery`` pins them equal. Session types are only ever
read off live session objects, never written here.

Differences from carry (all deliberate):

* a drop that lands back on the tab the drag came from (the QDrag source
  tab stays active for the whole gesture, so target == active means
  drop-back) is IGNORED, never re-routed: the strip has no per-card target
  and the origin tab owns its own drop path.
* a target tab that declines (``accepts_drop`` False) is ignored + logged.
* unknown sessions are ignored + logged.

    Wiring: ``MainWindowComposer.compose`` installs one bound handler via
    ``install_tab_strip_drop`` (single call site — it already holds
    ``main_window`` + ``store``).

    Position sourcing (Wayland correctness): ``QCursor.pos()`` is FROZEN for
    the whole ``QDrag.exec`` on this stack (proven by move-trace), so the
    drop position always comes from the drop event itself —
    ``receiver.mapToGlobal(event.position())`` is pure geometry math and
    stays correct mid-drag. Never ``QCursor`` here.
    """

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ImproveImgSLI")

#: Card-drag mime (wire mirror — the single definition lives tab-side next to
#: the card drag source; pinned equal by ``test_gallery_dnd_delivery``).
#: Checked with ``hasFormat`` only; never redefined as a second constant.
GALLERY_CARD_MIME = "application/x-imgsli-gallery-paths"


def has_card_mime(mime) -> bool:
    """True when *mime* carries gallery-card dragged paths."""
    try:
        return bool(mime is not None and mime.hasFormat(GALLERY_CARD_MIME))
    except Exception:
        return False


def parse_card_paths(mime) -> list[Path]:
    """Parse dragged card paths from the card mime (data + urls tolerant).

    Same wire rule the card drag source writes: newline-separated ``file://``
    URLs in ``data(mime)`` plus ``setUrls()``. Order-preserving, deduped.
    Never raises — corrupt payloads yield whatever parsed.
    """
    seen: set[str] = set()
    out: list[Path] = []

    def _take(candidate) -> None:
        try:
            s = str(candidate)
        except Exception:
            return
        if not s or s in seen:
            return
        seen.add(s)
        try:
            out.append(Path(s))
        except Exception:
            pass

    try:
        raw = bytes(mime.data(GALLERY_CARD_MIME))
    except Exception:
        raw = b""
    if raw:
        try:
            from PySide6.QtCore import QUrl as _QUrl

            for line in raw.decode("utf-8", "replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    local = _QUrl(line).toLocalFile()
                except Exception:
                    local = ""
                _take(local or line)
        except Exception:
            pass
    try:
        for url in mime.urls():
            try:
                if url.isLocalFile():
                    _take(url.toLocalFile())
            except Exception:
                continue
    except Exception:
        pass
    return out


def deliver_gallery_drop(main_window, store, tabs, global_pos, paths) -> bool:
    """Deliver card *paths* dropped at *global_pos* onto the tab strip.

    Returns True when a pending insert was scheduled on the target tab.
    Fail-closed everywhere else (no paths, unknown session, declining tab,
    drop-back onto the drag-source tab) with one log line on each silent
    branch — drops never vanish without a trace.
    """
    try:
        if tabs is None or store is None:
            return False
        tab_bar = getattr(tabs, "tab_bar", None)
        if tab_bar is None:
            return False
        try:
            targets = [p if isinstance(p, Path) else Path(p) for p in (paths or [])]
        except Exception:
            return False
        if not targets:
            logger.debug("TabStripDrop: no paths — ignore")
            return False
        try:
            local = tab_bar.mapFromGlobal(global_pos)
        except Exception:
            return False
        try:
            inside = bool(tab_bar.rect().contains(local))
        except Exception:
            inside = False
        if not inside:
            return False
        try:
            index = int(tab_bar.tabAt(local))
        except Exception:
            return False
        if index < 0:
            return False
        try:
            session_id = tabs.tabData(index)
        except Exception:
            session_id = None
        if not session_id:
            return False

        try:
            session = store.get_workspace_session(session_id)
        except Exception:
            session = None
        if session is None:
            logger.debug("TabStripDrop: unknown session %r — ignore", session_id)
            return False
        session_type = getattr(session, "session_type", "") or ""

        from tabs.registry import TabRegistry

        registry = TabRegistry()
        tab = registry.get_tab(session_type)
        try:
            accepted = bool(tab is not None and tab.accepts_drop(list(targets)))
        except Exception:
            accepted = False
        if not accepted:
            logger.debug(
                "TabStripDrop: tab %r declined %d paths — ignore",
                session_type, len(targets),
            )
            return False

        try:
            active_id = getattr(getattr(store, "workspace", None), "active_session_id", None)
        except Exception:
            active_id = None
        if session_id == active_id:
            # Drop-back: the QDrag source tab stays active for the whole
            # gesture, so target == active is the tab the cards came from.
            # Intra-tab moves belong to that tab's own drop path — the strip
            # has no per-card target to offer, so ignore + log.
            logger.debug(
                "TabStripDrop: drop back on the drag-source tab — ignore",
            )
            return False

        switched = _switch_session(main_window, store, tabs, session_id, index)
        if not switched:
            try:
                gone = store.get_workspace_session(session_id) is None
            except Exception:
                gone = False
            if gone:
                return False

        # Defer until tab page / controller are active after the switch —
        # same recipe as ImageCarryService._try_deliver_to_workspace_tab.
        from PySide6.QtCore import QTimer

        from events.image_carry import _schedule_pending_insert

        pending = list(targets)
        QTimer.singleShot(
            0,
            lambda st=session_type, ps=pending: _schedule_pending_insert(st, ps),
        )
        logger.debug(
            "TabStripDrop: delivered %d paths to %r (session %s)",
            len(pending), session_type, session_id,
        )
        return True
    except Exception:
        logger.exception("TabStripDrop: delivery failed")
        return False


def _switch_session(main_window, store, tabs, session_id: str, tab_index: int) -> bool:
    """Workspace-switch recipe mirrored from ``ImageCarryService._switch_session``."""
    window = main_window
    presenter = getattr(window, "presenter", None) if window is not None else None
    controller = (
        getattr(presenter, "main_controller", None) if presenter is not None else None
    )
    workspace = getattr(controller, "workspace", None) if controller else None
    if workspace is not None and hasattr(workspace, "switch_workspace_session"):
        try:
            workspace.switch_workspace_session(session_id)
            return True
        except Exception:
            logger.exception("TabStripDrop: switch_workspace_session failed")
    # Fallback: drive the tab strip (emits currentChanged → same path).
    if tabs is not None and tab_index >= 0:
        try:
            tabs.setCurrentIndex(tab_index)
            return True
        except Exception:
            logger.exception("TabStripDrop: strip fallback switch failed")
    try:
        return bool(store.switch_workspace_session(session_id))
    except Exception:
        logger.exception("TabStripDrop: store switch failed")
        return False


def install_tab_strip_drop(main_window, store) -> bool:
    """Bind the strip's drop hook to :func:`deliver_gallery_drop` (idempotent).

    Returns True when a strip with ``set_qdrag_drop_handler`` was found and
    bound. The handler takes ``(event, receiving_widget)`` — the drop
    position is derived from the event (``mapToGlobal(event.position())``),
    never from ``QCursor`` (frozen mid-drag) — and settles the event, so the
    strip widget never imports store/registry code.
    """
    try:
        ui = getattr(main_window, "ui", None)
        strip = getattr(ui, "workspace_tabs", None) if ui is not None else None
        if strip is None:
            return False
        setter = getattr(strip, "set_qdrag_drop_handler", None)
        if not callable(setter):
            return False

        def _event_global_pos(event, receiving_widget):
            try:
                local = event.position()
                try:
                    local = local.toPoint()
                except Exception:
                    pass
                return receiving_widget.mapToGlobal(local)
            except Exception:
                return None

        def _on_strip_drop(event, receiving_widget=None) -> None:
            try:
                global_pos = _event_global_pos(
                    event, receiving_widget if receiving_widget is not None else strip
                )
            except Exception:
                global_pos = None
            if global_pos is None:
                try:
                    event.ignore()
                except Exception:
                    pass
                return
            try:
                dropped = parse_card_paths(event.mimeData())
            except Exception:
                dropped = []
            try:
                delivered = deliver_gallery_drop(
                    main_window, store, strip, global_pos, dropped
                )
            except Exception:
                delivered = False
                logger.exception("TabStripDrop: handler failed")
            try:
                if delivered:
                    event.accept()
                else:
                    event.ignore()
            except Exception:
                pass

        try:
            setter(_on_strip_drop)
        except Exception:
            return False
        return True
    except Exception:
        return False

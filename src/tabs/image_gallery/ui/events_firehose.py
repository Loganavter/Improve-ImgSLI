"""Raw Qt input firehose for the gallery (DEBUGGING.md rule 5).

The causal tracer only records dispatches; hover never dispatches, so it
is invisible there by construction (rule 7 blindness). This stream taps the
event boundary instead: every mouse press/release/move plus Enter/Leave,
with receiver + position. Gated by ``IMGSLI_GALLERY_EVENTS_DEBUG``,
default off, session-only, never consumed (filter always returns False)
and never mixed into the curated ``[gallery-debug]`` stream.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject

_WATCHED_TYPES = frozenset(
    {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseMove,
        QEvent.Type.Enter,
        QEvent.Type.Leave,
    }
)


def _describe(watched) -> str:
    try:
        cls = type(watched).__name__
    except Exception:
        cls = "?"
    try:
        name = watched.objectName()
    except Exception:
        name = ""
    extra = ""
    try:
        gp = watched.property("gallery_path")
        if gp:
            extra = f" gallery={gp}"
    except Exception:
        pass
    return f"{cls}:{name}{extra}" if name or extra else cls


def _pos_of(event) -> str:
    for attr in ("globalPosition", "globalPos", "pos"):
        try:
            p = getattr(event, attr, None)
            v = p() if callable(p) else p
            if v is not None:
                try:
                    return f"({int(v.x())},{int(v.y())})"
                except Exception:
                    return str(v)
        except Exception:
            continue
    return "?"


def _top_child_at(watched, event) -> str:
    """Qt's own hit-test answer at the event point (boundary witness).

    App logs prove what the app *decided*; this asks the compositor-side
    question with Qt's own `childAt`: which child does Qt itself consider
    topmost under this move. Empty when unresolvable (non-widget receiver,
    no local position) — never fails the filter.
    """
    try:
        from PySide6.QtWidgets import QWidget

        if not isinstance(watched, QWidget):
            return ""
        local = None
        for attr in ("position", "pos"):
            try:
                v = getattr(event, attr, None)
                v = v() if callable(v) else v
                if v is not None:
                    try:
                        local = v.toPoint()
                    except Exception:
                        local = v
                    break
            except Exception:
                continue
        if local is None:
            return ""
        try:
            child = watched.childAt(local)
        except Exception:
            return ""
        if child is None or child is watched:
            return ""
        desc = _describe(child)
        # Live attribute truth (same object, same moment — no cross-time
        # math, no compositor): a hit-test-visible child that delivery
        # skips is usually WA_TransparentForMouseEvents / disabled.
        try:
            from PySide6.QtCore import Qt

            flags = ""
            try:
                if child.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents):
                    flags += "T"
            except Exception:
                pass
            try:
                if not child.isEnabled():
                    flags += "D"
            except Exception:
                pass
            try:
                if child.isHidden():
                    flags += "H"
            except Exception:
                pass
            if flags:
                desc = f"{desc}[{flags}]"
        except Exception:
            pass
        return desc
    except Exception:
        return ""


class _EventsFirehose(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        try:
            if event.type() not in _WATCHED_TYPES:
                return False
            from tabs.image_gallery.debug import gallery_event

            buttons = ""
            try:
                b = event.buttons()
                bv = int(getattr(b, "value", b))
                buttons = f" buttons={bv}" if bv else ""
            except Exception:
                pass
            # Memorialized Qt button state (QApplication, NOT the event).
            # Diverges from event.buttons() when a release never reached
            # the window (consumed upstream): physical button up, Qt still
            # thinks held -> moves grab-route to the press receiver, no
            # hit-testing, no Enter. Always logged: it is THE stuck bit.
            try:
                from PySide6.QtWidgets import QApplication as _QA2

                _mb = _QA2.mouseButtons()
                mbtns = f" mbtns={int(getattr(_mb, 'value', _mb))}"
            except Exception:
                mbtns = ""
            top = ""
            grab = ""
            if event.type() == QEvent.Type.MouseMove:
                try:
                    hit = _top_child_at(watched, event)
                    top = f" top={hit}" if hit else ""
                except Exception:
                    pass
                # Window-level hit-test verdict next to the host-level one:
                # delivery uses widgetAt's descent; childAt is the host's.
                # top=Button + wat=host pinpoints the descent level that
                # drops the card (same moment, same point — no cross-time).
                try:
                    from PySide6.QtWidgets import QApplication as _QA

                    gp = None
                    try:
                        _gv = event.globalPosition()
                        gp = _gv() if callable(_gv) else _gv
                    except Exception:
                        gp = None
                    if gp is not None:
                        try:
                            _w = _QA.widgetAt(gp.toPoint())
                        except Exception:
                            _w = None
                        if _w is not None and _w is not watched:
                            top += f" wat={_describe(_w)}"
                except Exception:
                    pass
                # A stuck mouse grab reroutes ALL mouse delivery to the
                # grabber — log it when present (empty normally).
                try:
                    from PySide6.QtWidgets import QWidget as _QW

                    g = _QW.mouseGrabber()
                    if g is not None:
                        grab = f" grab={_describe(g)}"
                except Exception:
                    pass
            gallery_event(
                "%s recv=%s pos=%s%s%s%s%s",
                event.type().name,
                _describe(watched),
                _pos_of(event),
                buttons,
                mbtns,
                top,
                grab,
            )
        except Exception:
            pass
        return False


def install_events_firehose() -> bool:
    """Install the app-wide firehose once. Returns True when active."""
    try:
        from PySide6.QtWidgets import QApplication

        from tabs.image_gallery.debug import gallery_events_enabled

        if not gallery_events_enabled():
            return False
        app = QApplication.instance()
        if app is None:
            return False
        if bool(getattr(app, "_gallery_events_firehose", False)):
            return True
        filt = _EventsFirehose(app)
        app.installEventFilter(filt)
        app._gallery_events_firehose = True  # type: ignore[attr-defined]
        app._gallery_events_filter = filt  # type: ignore[attr-defined]
        return True
    except Exception:
        return False

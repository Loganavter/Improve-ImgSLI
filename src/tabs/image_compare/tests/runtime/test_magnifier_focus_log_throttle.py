"""The magnifier button's focus log must not spam.

Owner report 2026-10-26: thousands of identical lines at ~1 ms apart —

    22:52:27,422 - [DEBUG] - [magnifier-visibility] btn_magnifier event=9
                   reason=FocusReason.MouseFocusReason
    ... (the same line ~1000x/s)

A closing window (or a popup re-focusing its anchor) hands focus back and forth,
and an unconditional ``logger.debug`` per FocusIn/FocusOut turns that into a wall
of identical text. ``focus_log.log_focus_event`` throttles per (tag, kind,
reason): one line, then silence for ``FOCUS_LOG_MIN_INTERVAL_S``; a different
kind/reason still logs, and the same one logs again after a quiet gap, so a real
later burst is not hidden.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt

from tabs.image_compare.ui import focus_log as fl

TAG = "[magnifier-visibility] btn_magnifier"
LOGGER = logging.getLogger("app")


class _Ev:
    def __init__(self, kind, reason=Qt.FocusReason.MouseFocusReason):
        self._kind = kind
        self._reason = reason

    def type(self):
        return self._kind

    def reason(self):
        return self._reason


def _setup(monkeypatch, caplog):
    monkeypatch.setattr(fl, "_STATE", {})
    caplog.set_level(logging.DEBUG, logger="app")
    return caplog


def _lines(caplog):
    return [r for r in caplog.records if "btn_magnifier event=" in r.getMessage()]


def test_repeated_focus_events_log_once(monkeypatch, caplog):
    _setup(monkeypatch, caplog)
    for _ in range(50):
        fl.log_focus_event(LOGGER, _Ev(QEvent.Type.FocusIn), TAG)
    assert len(_lines(caplog)) == 1


def test_a_different_reason_still_logs(monkeypatch, caplog):
    _setup(monkeypatch, caplog)
    fl.log_focus_event(LOGGER, _Ev(QEvent.Type.FocusIn), TAG)
    fl.log_focus_event(LOGGER, _Ev(QEvent.Type.FocusOut), TAG)
    assert len(_lines(caplog)) == 2


def test_the_same_reason_logs_again_after_the_quiet_gap(monkeypatch, caplog):
    _setup(monkeypatch, caplog)
    fl.log_focus_event(LOGGER, _Ev(QEvent.Type.FocusIn), TAG)
    sig, _ts = fl._STATE[TAG]
    monkeypatch.setitem(fl._STATE, TAG, (sig, fl.time.monotonic() - (fl.FOCUS_LOG_MIN_INTERVAL_S + 1)))
    fl.log_focus_event(LOGGER, _Ev(QEvent.Type.FocusIn), TAG)
    assert len(_lines(caplog)) == 2

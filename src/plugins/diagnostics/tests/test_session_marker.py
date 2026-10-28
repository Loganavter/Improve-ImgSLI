"""The unclean-shutdown marker: one file, three verdicts, no false alarms.

The feature exists because a session that ends abnormally leaves no trace today:
a task-manager kill, a power cut or the owner's 2026-10-28 packaged-build failure
all look like "the user opened the app again". These tests pin the three things
that make the detector usable rather than annoying:

* a **clean** exit is never reported (``mark_clean`` is the exit path's job);
* a **running instance** is never reported as a crash (the pid is alive);
* a **different boot** never trusts the pid (a recycled id would lie).

Plus the payload a report is built from: the previous log tail and, when a
faulthandler dump exists, its traceback.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from plugins.diagnostics import session_marker as marker


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "last-session.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_begin_session_claims_the_session_as_unclean(tmp_path, monkeypatch):
    path = tmp_path / "run" / "last-session.json"
    # The test process is alive, so its own pid would (correctly) read as
    # "another instance"; the marker's claim is what is under test here.
    monkeypatch.setattr("core.control.discovery.is_pid_alive", lambda pid: False)

    marker.begin_session(path=path, log_file="/x/log.txt", version="11.0.0")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["clean"] is False
    assert data["pid"] > 0
    assert data["version"] == "11.0.0"
    assert data["log_file"] == "/x/log.txt"
    assert data["started_at"], "a report needs the wall clock of the session"
    assert marker.classify(marker.read_previous(path=path)) == "unclean"


def test_mark_clean_turns_the_same_marker_into_a_clean_one(tmp_path):
    path = tmp_path / "last-session.json"
    marker.begin_session(path=path)

    assert marker.mark_clean(path=path) is True

    previous = marker.read_previous(path=path)
    assert previous is not None and previous.clean is True
    assert marker.classify(previous) == "none"


def test_no_marker_answers_none(tmp_path):
    assert marker.read_previous(path=tmp_path / "absent.json") is None
    assert marker.classify(None) == "none"


def test_a_corrupt_marker_is_not_a_crash(tmp_path):
    path = tmp_path / "last-session.json"
    path.write_text("{not json", encoding="utf-8")

    assert marker.read_previous(path=path) is None
    assert marker.classify(None) == "none"


def test_a_live_pid_is_another_instance_not_a_crash(tmp_path, monkeypatch):
    path = _write(tmp_path, {"pid": 4242, "clean": False, "boot_id": ""})
    monkeypatch.setattr(
        "core.control.discovery.is_pid_alive", lambda pid: pid == 4242
    )

    assert marker.classify(marker.read_previous(path=path)) == "concurrent"


def test_a_dead_pid_is_unclean(tmp_path, monkeypatch):
    path = _write(tmp_path, {"pid": 4242, "clean": False, "boot_id": ""})
    monkeypatch.setattr("core.control.discovery.is_pid_alive", lambda pid: False)

    assert marker.classify(marker.read_previous(path=path)) == "unclean"


def test_a_different_boot_never_trusts_the_pid(tmp_path, monkeypatch):
    path = _write(tmp_path, {"pid": 4242, "clean": False, "boot_id": "boot-a"})
    monkeypatch.setattr(marker, "boot_id", lambda: "boot-b")
    monkeypatch.setattr("core.control.discovery.is_pid_alive", lambda pid: True)

    assert marker.classify(marker.read_previous(path=path)) == "unclean", (
        "after a reboot the recorded pid can belong to an unrelated process — "
        "the boot id is what makes that case decidable"
    )


def test_an_unknown_boot_id_is_never_a_mismatch(tmp_path, monkeypatch):
    path = _write(tmp_path, {"pid": 4242, "clean": False, "boot_id": ""})
    monkeypatch.setattr(marker, "boot_id", lambda: "boot-b")
    monkeypatch.setattr("core.control.discovery.is_pid_alive", lambda pid: False)

    previous = marker.read_previous(path=path)
    assert marker.classify(previous) == "unclean", (
        "an absent boot id must not be read as a different boot (that would turn "
        "every Windows marker into a false alarm), and a dead pid decides anyway"
    )


def test_failure_payload_carries_the_log_tail_and_the_fault_dump(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("\n".join(f"line {i}" for i in range(400)), encoding="utf-8")
    dump = tmp_path / "fault-dump.log"
    dump.write_text("Fatal Python error: Segmentation fault\n  File x", encoding="utf-8")
    path = tmp_path / "last-session.json"
    marker.begin_session(path=path, log_file=log, fault_file=dump, version="11.0.0")

    payload = marker.failure_payload(marker.read_previous(path=path))

    assert payload["type"] == "UncleanShutdown"
    assert "11.0.0" in payload["message"]
    assert len(payload["log_tail"]) == marker.LOG_TAIL_LINES
    assert payload["log_tail"][-1] == "line 399"
    assert "Segmentation fault" in payload["fault_dump_tail"]


def test_failure_payload_without_files_is_still_usable(tmp_path):
    path = tmp_path / "last-session.json"
    marker.begin_session(path=path)

    payload = marker.failure_payload(marker.read_previous(path=path))

    assert payload["log_tail"] == []
    assert "fault_dump_tail" not in payload


class _FakeSettings:
    """Minimal QSettings double: one group, one key."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self._group = ""

    def beginGroup(self, name: str) -> None:  # noqa: N802 - QSettings API
        self._group = name

    def endGroup(self) -> None:  # noqa: N802
        self._group = ""

    def value(self, key: str, default=None):  # noqa: N802
        return self.values.get(f"{self._group}/{key}", default)

    def setValue(self, key: str, value) -> None:  # noqa: N802
        self.values[f"{self._group}/{key}"] = value

    def sync(self) -> None:
        pass


def test_the_opt_out_is_persisted_and_read_back():
    settings = _FakeSettings()

    assert marker.offer_is_suppressed(settings) is False
    marker.suppress_offer(settings)
    assert marker.offer_is_suppressed(settings) is True
    assert settings.values.get("diagnostics/offer_unclean_report") is False


@pytest.mark.parametrize("value,expected", [("false", True), ("0", True), (False, True), ("true", False), (True, False)])
def test_the_opt_out_understands_qsettings_string_forms(value, expected):
    settings = _FakeSettings()
    settings.values["diagnostics/offer_unclean_report"] = value

    assert marker.offer_is_suppressed(settings) is expected


def test_the_startup_path_claims_a_session_and_clears_it_on_exit():
    """Guard the WIRING, not the mechanism: a detector nobody calls detects nothing.

    The marker module works in isolation; the failure mode this pins is someone
    removing the call from ``__main__`` (or the ``mark_clean`` before ``os._exit``,
    which is the only exit the app takes).
    """
    import ast

    main_py = Path(__file__).resolve().parents[3] / "__main__.py"
    source = main_py.read_text(encoding="utf-8")

    tree = ast.parse(source)
    main_def = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    first = main_def.body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), (
        "main() must claim the session before anything else can fail"
    )
    assert getattr(first.value.func, "id", "") == "_begin_session_marker"

    assert "session_marker.read_previous()" in source
    assert "session_marker.begin_session(" in source
    assert "mark_clean()" in source, (
        "the app leaves through os._exit, which skips atexit — the clean exit has "
        "to be written explicitly before it"
    )
    assert source.index("mark_clean()") > source.index("exit_code = app.exec()")
    assert source.index("mark_clean()") < source.index("os._exit(")

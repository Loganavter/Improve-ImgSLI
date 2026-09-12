"""CLI-level tests for the OS-agnostic launcher (launcher.py).

Covers the argparse surface: command dispatch, top-level flag shim,
passthrough semantics, help layout, and exit codes. No venv/network
involvement — parsing only.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import pytest

import launcher


def build():
    return launcher.build_parser()


def test_top_level_help_lists_all_commands():
    parser, _ = build()
    help_text = parser.format_help()
    for name in (
        "install",
        "recreate",
        "delete",
        "rm-cache",
        "run",
        "test",
        "context",
        "install-desktop",
        "uninstall-desktop",
        "--enable-logging",
        "--disable-logging",
        "help",
    ):
        assert name in help_text, f"missing command in help: {name}"


def test_top_level_help_has_no_inline_examples():
    parser, _ = build()
    help_text = parser.format_help()
    assert "dump-ui-layout /tmp/layout.json" not in help_text


def test_run_help_has_the_dump_example():
    parser, commands = build()
    run_help = commands["run"].format_help()
    assert "--dump-ui-layout /tmp/layout.json" in run_help


def test_unknown_command_exits_two():
    parser, _ = build()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["foobar"])
    assert exc.value.code == 2


def test_run_flags_consumed_and_rest_passthrough():
    parser, _ = build()
    args, extras = parser.parse_known_args(
        ["run", "--debug", "--theme", "dark", "--dump-ui-layout", "/tmp/x.json"]
    )
    assert args.command == "run"
    assert args.debug is True
    assert args.theme == "dark"
    assert extras == ["--dump-ui-layout", "/tmp/x.json"]


def test_run_ui_inspector_implies_debug_flag_value():
    parser, _ = build()
    args, _ = parser.parse_known_args(["run", "--ui-inspector"])
    assert args.ui_inspector is True
    assert args.debug is False  # implication happens at action level


def test_test_passthrough_keeps_pytest_flags():
    parser, _ = build()
    args, extras = parser.parse_known_args(["test", "-q", "tests/contracts", "-k", "undo"])
    assert args.command == "test"
    assert extras == ["-q", "tests/contracts", "-k", "undo"]


def test_context_passthrough():
    parser, _ = build()
    args, extras = parser.parse_known_args(["context", "--cloc-only"])
    assert args.command == "context"
    assert extras == ["--cloc-only"]


def test_help_command_with_topic():
    parser, _ = build()
    args, _ = parser.parse_known_args(["help", "run"])
    assert args.command == "help"
    assert args.topic == "run"


def test_theme_validation_rejects_bad_value():
    parser, _ = build()
    try:
        parser.parse_known_args(["run", "--theme", "blue"])
        assert False, "expected SystemExit for invalid --theme"
    except SystemExit as exc:
        assert exc.code == 2


def test_top_level_flag_shim_maps_to_run(monkeypatch):
    seen = {}

    def fake_handler(args, extras, ui):
        seen["extras"] = extras
        return 0

    monkeypatch.setattr(launcher, "make_ui", lambda: launcher.UI(progress=False))
    monkeypatch.setattr(launcher, "ensure_venv_ready", lambda ui: None)
    monkeypatch.setitem(launcher.DISPATCH, "run", fake_handler)
    cases = (["--debug"], ["-d"], ["--theme", "dark"], ["--ui-inspector"],
             ["--dump-ui-layout", "/tmp/x.json"], ["--open-tab", "image_compare"],
             ["--run-action", "platform.settings"])
    for argv in cases:
        seen.clear()
        launcher.main(argv)
        assert "extras" in seen, f"argv {argv} did not shim to run"


def test_no_args_prints_help_and_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr(launcher.sys, "argv", ["launcher.sh"])
    code = launcher.main([])
    assert code == 0
    assert "usage:" in capsys.readouterr().out


def test_log_flags_dispatch_before_argparse(monkeypatch):
    calls = {}

    def fake_logging(enable, ui):
        calls["enable"] = enable
        return 0

    monkeypatch.setattr(launcher, "logging_action", fake_logging)
    launcher.main(["--enable-logging"])
    assert calls["enable"] is True
    launcher.main(["--disable-logging"])
    assert calls["enable"] is False

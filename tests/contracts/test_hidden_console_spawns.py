"""Console child processes must not flash a window (single-source gate).

Symptom (2026-10-24, Windows host): opening the video editor flashed a ``cmd``
window for a couple of frames. The app ships as a **windowed** executable, so it
owns no console; spawning a console-subsystem child (``ffmpeg.exe`` for the
encoder probe) makes Windows allocate one. The export path already passed
``CREATE_NO_WINDOW``; the probe on dialog open did not.

The gate (AST, no runtime):

1. every ``subprocess.Popen/run/call/check_output/check_call`` under ``src/``
   must pass ``**hidden_process_kwargs()`` (or an explicit ``creationflags=``
   for a documented exception);
2. the ``CREATE_NO_WINDOW`` value must not be spelled as an integer literal
   outside ``shared/hidden_process.py`` -- one helper, one truth;
3. developer tooling under ``src/devtools/`` is exempt: those scripts are meant
   to run from a terminal and their own children may share it.
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, parse, rel

HELPER = "src/shared/hidden_process.py"
SPAWN_FUNCS = frozenset({"Popen", "run", "call", "check_output", "check_call"})
#: Paths whose spawns may keep the console: developer tooling runs in a shell.
ALLOWED_PREFIXES = ("src/devtools/",)


def _is_subprocess_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in SPAWN_FUNCS:
        return False
    owner = func.value
    return isinstance(owner, ast.Name) and owner.id == "subprocess"


def _has_helper_kwarg(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg is None:  # **kwargs form
            value = keyword.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "hidden_process_kwargs"
            ):
                return True
    return False


def _has_explicit_creationflags(call: ast.Call) -> bool:
    return any(keyword.arg == "creationflags" for keyword in call.keywords)


def test_every_spawn_passes_the_hidden_helper():
    offenders: list[str] = []
    for path in iter_py(SRC):
        relative = rel(path)
        if relative == HELPER or relative.startswith(ALLOWED_PREFIXES):
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_subprocess_call(node)):
                continue
            if _has_helper_kwarg(node) or _has_explicit_creationflags(node):
                continue
            offenders.append(f"{relative}:{node.lineno}")

    assert not offenders, (
        "console spawn without hidden_process_kwargs():\n  "
        + "\n  ".join(offenders)
        + "\n\nOn Windows a windowed app allocates a console for a "
        "console-subsystem child -- that is the cmd flash when opening the "
        "video editor (2026-10-24). Add **hidden_process_kwargs() from "
        "shared/hidden_process.py."
    )


def test_creationflags_is_not_spelled_by_hand():
    """A literal ``creationflags=<int>`` outside the helper is the anti-pattern.

    (Deliberately narrow: the same integer is also ``SHCNE_ASSOCCHANGED`` in
    ``windows_file_association.py``, which is not a spawn flag at all -- the
    first draft of this gate flagged it.)
    """
    offenders: list[str] = []
    for path in iter_py(SRC):
        relative = rel(path)
        if relative == HELPER or relative.startswith(ALLOWED_PREFIXES):
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "creationflags":
                    continue
                if isinstance(keyword.value, ast.Constant):
                    offenders.append(f"{relative}:{node.lineno}")

    assert not offenders, (
        "creationflags spelled as a literal outside shared/hidden_process.py:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse **hidden_process_kwargs() so the flag has one home."
    )


def test_helper_exists_and_returns_empty_off_windows():
    path = SRC.parent / HELPER
    assert path.exists(), f"{HELPER} is missing: the gate has no single source"
    text = path.read_text(encoding="utf-8")
    assert "def hidden_process_kwargs(" in text
    assert 'os.name != "nt"' in text, (
        "the helper must return {} on non-Windows hosts (no console exists "
        "there, and Windows-only flags must not leak into posix spawn calls)"
    )


def test_helper_semantics_per_host(monkeypatch):
    """Posix: no flags (no console exists). Windows: CREATE_NO_WINDOW."""
    import os

    from shared.hidden_process import hidden_process_kwargs

    monkeypatch.setattr(os, "name", "posix")
    assert hidden_process_kwargs() == {}

    monkeypatch.setattr(os, "name", "nt")
    kwargs = hidden_process_kwargs()
    assert kwargs == {"creationflags": 0x08000000}, kwargs

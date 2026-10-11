"""Ownership/write guards for the Image Gallery tab (G4, tab-owned).

Dogma source: docs/dev/tabs/isolation.md — tab-owned AST dogmas live under
``src/tabs/<tab>/tests/contracts/`` (this directory), mirroring the
``tests/contracts/`` style (``iter_py``/``read``/``rel`` helpers, regex
scan over source text, no runtime).

What is guarded: the G1–G3 ownership settlement — the tab wires the
controller into the widget exactly once via
``ImageGalleryWidget.attach_controller`` (``tab.py`` create_page); nobody
else assigns ``widget._controller`` / ``widget._owner``; state flows only
through ``GalleryController`` (dispatch + mirror) or the single
``use_cases.persistence.deserialize_session`` slot-write (which mirrors
``tabs.multi_compare.use_cases.persistence`` verbatim). Selection writes
go through ``GalleryController.set_selection``; storeless fallbacks spell
writes via ``setattr``, never bare ``.state.X =`` outside
``controller.py``.

How it works: every regex hit in ``src/tabs/image_gallery/`` (excluding
``tests/``) must be a member of ``ALLOWLIST`` — a ``(relative path, line)``
pair with a reason comment. Any NEW occurrence (new file, new line, moved
line) fails until a human allowlists it with a reason. Match by file+line,
never by blanket regex exemption. ``==`` comparisons are not writes (the
``(?!=)`` guard) — only single-``=`` assignments flag.

Do NOT "fix" the allowlisted lines: they are reviewed transitional bridges
(last-resort binds, owner probes, test-required SimpleNamespace doubles).
"""

from __future__ import annotations

import re
from pathlib import Path

# Tab-owned: resolve repo root from this file's depth (5 levels below root
# per docs/dev/tabs/isolation.md), not from tests/conftest.py.
ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / "src"
SCOPE = SRC / "tabs" / "image_gallery"


def iter_py(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and "tests" not in p.parts
    ]


def rel(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return Path(str(p)).as_posix()


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# (pattern_name, compiled_regex, applies_to relpath or None for all files)
WRITE_PATTERNS: list[tuple[str, re.Pattern, str | None]] = [
    ("widget._controller write", re.compile(r"widget\._controller\s*=(?!=)"), None),
    ("widget._owner write", re.compile(r"widget\._owner\s*=(?!=)"), None),
    ("_gallery_controller ref", re.compile(r"_gallery_controller"), None),
    (
        "controller/owner attr probe loop",
        re.compile(r"for attr in \([^)]*\"_controller\""),
        None,
    ),
    ("ctrl.state write", re.compile(r"ctrl\.state\.[a-z_]+\s*=(?!=)"), None),
    # Bare ``.state.X =`` writes are the controller's own job (mirror +
    # dispatch live there); everywhere else they must go through
    # set_selection/set_source/_emit/_transact or setattr fallbacks.
    # controller.py is exempt wholesale — enforced by skipping it here.
    ("bare .state write", re.compile(r"\.state\.[a-z_]+\s*=(?!=)"), "EXCEPT controller.py"),
]

# Transitional read probes: same file+line ratchet as writes. These reads
# are the G2/G3 bridges until a universal _owner_for_triage — new probes
# fail here until allowlisted with a reason.
READ_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("owner._controller read", re.compile(r"owner\._controller")),
    ("owner._owner read", re.compile(r"owner\._owner")),
    ("overlay._owner read", re.compile(r"overlay\._owner")),
    (
        "storeless setattr fallback",
        re.compile(r"_merge_selection_setattr|setattr\(state,"),
    ),
]

# (relpath, lineno) -> reason. Line numbers are 1-based (rg --line-number).
ALLOWLIST: dict[tuple[str, int], str] = {
    # --- controller/owner attr probe loops (W4) ---
    ("src/tabs/image_gallery/use_cases/selection.py", 85): (
        "_resolve_selection_controller _controller/_owner READ probe (bridge until universal _owner_for_triage)"
    ),
    # --- owner._controller legacy reads (R1: last-resort bind, G2; protocol-first since G5) ---
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 45): (
        "owner_for_triage legacy owner._controller READ (last-resort bind, protocol-first since G5)"
    ),
    ("src/tabs/image_gallery/ui/drag_drop.py", 243): (
        "_explicit_controller legacy owner._controller READ (last-resort bind, G2)"
    ),
    ("src/tabs/image_gallery/use_cases/triage_ui.py", 47): (
        "owner_for_triage legacy owner._controller READ (last-resort bind, protocol-first since G5)"
    ),
    # --- owner._owner legacy reads (R2) ---
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 51): (
        "owner_for_triage legacy owner._owner READ (last-resort bind, protocol-first since G5)"
    ),
    ("src/tabs/image_gallery/use_cases/triage_ui.py", 53): (
        "owner_for_triage legacy owner._owner READ (last-resort bind, protocol-first since G5)"
    ),
    # --- overlay._owner fallback reads (R3: test-required SimpleNamespace doubles pass owner=None) ---
    ("src/tabs/image_gallery/ui/quick_look/meta.py", 124): (
        "overlay._owner READ fallback when owner=None (test-required SimpleNamespace doubles)"
    ),
    ("src/tabs/image_gallery/ui/quick_look/insets.py", 108): (
        "overlay._owner READ fallback when owner=None (test-required SimpleNamespace doubles)"
    ),
    # --- storeless setattr fallback (R4) ---
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 97): (
        "_merge_selection_setattr def: storeless fallback (setattr, never bare writes)"
    ),
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 107): (
        "_merge_selection_setattr storeless setattr fallback"
    ),
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 112): (
        "_merge_selection_setattr storeless setattr fallback"
    ),
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 118): (
        "_merge_selection_setattr storeless setattr fallback"
    ),
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 272): (
        "_merge_selection_setattr storeless call site"
    ),
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 274): (
        "_merge_selection_setattr storeless call site"
    ),
    ("src/tabs/image_gallery/ui/quick_look_hooks.py", 382): (
        "set_source storeless setattr fallback (never a bare state write)"
    ),
}

_CONTROLLER_REL = "src/tabs/image_gallery/controller.py"


def _scan() -> list[str]:
    violations: list[str] = []
    for path in sorted(iter_py(SCOPE)):
        r = rel(path)
        text = read(path)
        for name, rx, scope in WRITE_PATTERNS:
            if scope == "EXCEPT controller.py" and r == _CONTROLLER_REL:
                continue
            for m in rx.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                if (r, lineno) not in ALLOWLIST:
                    violations.append(f"{r}:{lineno}: [{name}] {m.group(0)!r}")
        for name, rx in READ_PATTERNS:
            for m in rx.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                if (r, lineno) not in ALLOWLIST:
                    violations.append(f"{r}:{lineno}: [{name}] {m.group(0)!r}")
    return violations


def test_gallery_ownership_no_new_writes_or_probes():
    violations = _scan()
    assert not violations, (
        "new ownership/write/probe occurrence in src/tabs/image_gallery/ "
        "(not in ALLOWLIST — add a (file, line) entry with a reason, do not "
        "broaden the regex):\n" + "\n".join(violations)
    )


def test_gallery_allowlist_is_live():
    """Every ALLOWLIST entry must still match — no dead (file, line) entries.

    Guards against allowlist rot: if a bridge line moves or is removed, this
    fails and the entry must be updated or dropped in the same change.
    """
    dead: list[str] = []
    by_file: dict[str, list[tuple[int, str]]] = {}
    for (r, lineno), _reason in ALLOWLIST.items():
        by_file.setdefault(r, []).append((lineno, r))
    for r, entries in by_file.items():
        text = read(ROOT / r)
        lines = text.splitlines()
        for lineno, _ in entries:
            line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            hit = any(rx.search(line) for _name, rx, _scope in WRITE_PATTERNS) or any(
                rx.search(line) for _name, rx in READ_PATTERNS
            )
            if not hit:
                dead.append(f"{r}:{lineno}: {line.strip()!r}")
    assert not dead, (
        "stale ALLOWLIST entries (line moved or bridge removed — update or "
        "drop the entry):\n" + "\n".join(dead)
    )

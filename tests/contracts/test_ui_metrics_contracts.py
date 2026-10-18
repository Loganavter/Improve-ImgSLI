"""P0 gate: UI-metrics change-channel shape contract.

Closes the recurring bug class "a global UI metric changes and some widget's
cached derived state is never invalidized" on the consumer side (plan
``plan-ui-metrics-systemic-2026-10-18``): ``UiFont.font_changed`` and
``UiScale.scale_changed`` are two independent process-wide signals, so every
widget that derives geometry from either must subscribe through the unified
channel — ``connect_ui_metrics`` / ``MetricsContainer`` — never to one source
signal alone.

Dogma: an app-side ``.connect(...)`` / ``.disconnect(...)`` on
``UiScale.scale_changed`` or ``UiFont.font_changed`` is a finding unless its
file is listed in ``EXEMPTIONS`` with a reason. The app's own
``FontManager.font_changed`` (a different producer, folded into the appearance
bus by wave A2) is out of scope here, as are ``src/**/tests`` trees (test code
drives the metrics deliberately; behaviour is gated by the runtime parity
harness in ``tests/runtime/test_ui_metrics_parity.py``).
"""

from __future__ import annotations

import ast

from tests.contracts._framework import SRC, parse, rel

#: Files allowed to keep a direct single-signal metrics connection, with the
#: reason. Empty after wave A1: every app-side offender (plan §B plus the two
#: reverse-asymmetry ``glass_hud`` font-only subscribers) was migrated. This
#: list is the ratchet — a new direct connection fails the gate unless the
#: author records why the unified channel does not fit.
EXEMPTIONS: dict[str, str] = {}

#: Every app-side site that was on the scale-only offender inventory (plan §B)
#: or found by the same audit in the reverse direction (font-only). Each must
#: reference the unified channel; a wholesale revert fails this test even if
#: the connect-site scan above is what catches the details.
MIGRATED_SITES = {
    "plugins/help/back_bar.py",
    "ui/main_window/csd_menu_strip.py",
    "ui/main_window/window.py",
    "ui/widgets/form_controls.py",
    "ui/widgets/glass_hud/info.py",
    "ui/widgets/glass_hud/zoom.py",
    "ui/widgets/slider_hint.py",
    "tabs/image_compare/ui/layout.py",
    "tabs/image_gallery/ui/quick_look/labels_theme.py",
    "tabs/session_picker/recent/panel.py",
    "tabs/session_picker/widget.py",
}

_SOURCE_SIGNALS = {"scale_changed", "font_changed"}


def _iter_signal_conns(tree: ast.Module):
    """(signal-attribute, is_uifont) for connect/disconnect calls on a source signal."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute) and func.attr in ("connect", "disconnect")
        ):
            continue
        signal = func.value
        if not (
            isinstance(signal, ast.Attribute) and signal.attr in _SOURCE_SIGNALS
        ):
            continue
        yield signal, signal.attr == "font_changed"


def _receiver_root_name(signal: ast.Attribute) -> str:
    node: ast.AST = signal
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _is_uifont_signal(signal: ast.Attribute) -> bool:
    """True when a ``font_changed`` receiver is the toolkit UiFont singleton.

    The app's own ``FontManager.font_changed`` shares the attribute name but
    is a different producer (wave A2 territory) — its subscribers are not
    findings of this contract.
    """
    name = _receiver_root_name(signal)
    return name == "ui_font" or "uifont" in name.lower()


def _findings() -> list[str]:
    findings: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        tree = parse(path)
        if tree is None:
            continue
        for signal, is_font in _iter_signal_conns(tree):
            if is_font and not _is_uifont_signal(signal):
                continue
            r = rel(path)
            if r in EXEMPTIONS:
                continue
            findings.append(f"{r}:{signal.lineno} ({signal.attr})")
    return findings


def test_no_single_signal_metrics_connections():
    findings = _findings()
    assert not findings, (
        "App-side widgets must subscribe to BOTH metrics axes through the "
        "unified channel (connect_ui_metrics / MetricsContainer), never to "
        "UiScale.scale_changed or UiFont.font_changed alone — a single-axis "
        "subscription leaves cached derived geometry stale when the OTHER "
        "metric changes (the class this gate closes). Offending connect/"
        "disconnect sites:\n" + "\n".join(findings)
        + "\n\nIf a site genuinely cannot use the unified channel, record it "
        "in EXEMPTIONS with a reason instead of suppressing this test."
    )


def test_offender_sites_use_unified_channel():
    """Ratchet: every migrated offender file references the unified channel.

    Catches a wholesale revert of the migration (a file whose connects were
    all re-pointed at source signals) with a per-file message.
    """
    missing: list[str] = []
    for rel_path in sorted(MIGRATED_SITES):
        tree = parse(SRC / rel_path)
        assert tree is not None, f"cannot parse migrated site {rel_path}"
        uses_unified = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "connect_ui_metrics"
            ):
                uses_unified = True
                break
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = base.id if isinstance(base, ast.Name) else ""
                    if base_name.endswith("MetricsContainer"):
                        uses_unified = True
                        break
            if uses_unified:
                break
        if not uses_unified:
            missing.append(rel_path)
    assert not missing, (
        "These migrated offender files no longer reference the unified "
        "metrics channel (connect_ui_metrics / MetricsContainer) — the "
        "migration was reverted or lost:\n" + "\n".join(missing)
    )

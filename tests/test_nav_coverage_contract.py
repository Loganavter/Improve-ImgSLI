"""App-wide keyboard-coverage contract: every interactive control is nav-owned.

Requirement
-----------
For every window this contract registers (built from the real classes, shown
offscreen), every **interactive** control must be owned by a section of the
app-wide toolkit ``NavigationManager`` graph — or be listed in
``tests/nav_coverage_allowlist.py`` with a written reason.

The app's keyboard cursor is the section graph, not Qt focus: an arrow key is
routed to the section whose ``owns()`` accepts the focused widget, and a
control no section claims is unreachable by the app's own keyboard model even
if Qt would let ``Tab`` land on it. This module therefore judges ownership with
the live registry (``NavigationManager._sections``), never by widget type,
focus policy, or a copy of production call sites.

Interactive predicate (deliberately conservative)
-------------------------------------------------
A widget counts when it is a descendant of the audited window, currently
``isVisibleTo(window)`` and ``isEnabled()``, and either

* ``focusPolicy()`` is ``Qt.FocusPolicy.StrongFocus`` or ``ClickFocus`` — Qt
  would place focus there from Tab or a click; or
* it is a toolkit ``sli_ui_toolkit.widgets.Button`` — toolkit buttons can fire
  on click even when they declare ``NoFocus`` (the Quick Look ‹/› circles and
  SOURCE inset), so focus policy alone would silently miss a control a mouse
  can drive.

No widget is excluded for being a container, scroll viewport, label or CSD
title-bar chrome: those are exactly the controls earlier audits found unowned
(an ``OverlayScrollArea`` viewport, a click-focus body label, title-bar window
controls). Child top-levels (menus/popups) are separate surfaces, not interior
controls, and are never counted as part of the parent.

Coverage / exemptions
---------------------
Windows skipped or excused live only in ``tests/nav_coverage_allowlist.py``.
The whole-window form (``window:<Class>``) is honoured only while the window
registers no section at all; per-control entries must match a current orphan.
Every entry carries a reason, and entries that match nothing are reported as
stale (ratchet): the list cannot rot into a wall of dead keys.

Falsification story
-------------------
``test_contract_flags_and_names_a_synthetic_orphan`` builds a synthetic
registered window with one ``StrongFocus`` child outside every row and requires
the audit to flag and name it; the sibling test registers a section that owns
that child and requires the same window to pass. The companion tests pin the
two other halves of the predicate: a ``NoFocus`` toolkit ``Button`` is still
audited (click-only controls are not silently skipped), and a whole-window
exemption stops applying the moment the window registers a section.

Runs offscreen only — no Xvfb; the supervisor runs the live proof.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.widgets import Button

try:  # collected as part of the ``tests`` package (repo root on sys.path)
    from tests.nav_coverage_allowlist import NAV_COVERAGE_ALLOWLIST, WINDOW_PREFIX
except ImportError:  # pytest prepend mode: ``tests/`` is on sys.path
    from nav_coverage_allowlist import NAV_COVERAGE_ALLOWLIST, WINDOW_PREFIX

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Predicate + registry access
# ---------------------------------------------------------------------------


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _ensure_qapp():
    """Every builder constructs real dialogs — a QApplication must exist first."""
    return _app()


def _pump(rounds: int = 3) -> None:
    app = _app()
    for _ in range(rounds):
        app.processEvents()


def _manager():
    from sli_ui_toolkit.managers import NavigationManager

    return NavigationManager.get_instance()


def _section_pairs() -> list[tuple[object, object]]:
    """Live ``(owner, section)`` pairs, preferring a public accessor if added."""
    manager = _manager()
    accessor = getattr(manager, "sections", None)
    if callable(accessor):
        try:
            return list(accessor())
        except Exception:
            return []
    try:
        return list(getattr(manager, "_sections", None) or ())
    except Exception:
        return []


def registered_sections_of(window: QWidget) -> list[object]:
    """Sections registered for *window*'s own subtree.

    A section belongs to the window when its owner is the window itself or a
    descendant of it (dialog rows, overlay sections, a dialog title bar). A
    section registered on an ancestor belongs to that ancestor's window and is
    deliberately not borrowed here.
    """
    out: list[object] = []
    for owner, spec in _section_pairs():
        try:
            if owner is window or (
                isinstance(owner, QWidget) and window.isAncestorOf(owner)
            ):
                out.append(spec)
        except RuntimeError:  # C++ owner already destroyed mid-iteration
            continue
    return out


def _is_interactive(window: QWidget, widget: QWidget) -> bool:
    """The conservative predicate documented in the module docstring."""
    try:
        if widget.isWindow():
            return False  # separate surface, not an interior control
        if not widget.isVisibleTo(window) or not widget.isEnabled():
            return False
        policy = widget.focusPolicy()
        if policy in (Qt.FocusPolicy.StrongFocus, Qt.FocusPolicy.ClickFocus):
            return True
        return isinstance(widget, Button)
    except RuntimeError:
        return False


def _owned(sections: list[object], widget: QWidget) -> bool:
    for spec in sections:
        try:
            if callable(getattr(spec, "owns", None)) and spec.owns(widget):
                return True
        except Exception:
            continue
    return False


def _control_id(widget: QWidget) -> str:
    name = widget.objectName()
    return f"{type(widget).__name__}#{name}" if name else type(widget).__name__


def _chain(widget: QWidget, window: QWidget, *, max_depth: int = 12) -> str:
    """File-ish identifier: class/objectName of the control plus parent chain."""
    parts: list[str] = []
    cur: QWidget | None = widget
    while cur is not None and len(parts) < max_depth:
        parts.append(_control_id(cur))
        if cur is window:
            break
        cur = cur.parentWidget()
    return " < ".join(parts)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@dataclass
class WindowAudit:
    window_name: str
    interactive: int = 0
    owned: int = 0
    exempt: list[tuple[str, str, str]] = field(default_factory=list)  # label, key, reason
    violations: list[str] = field(default_factory=list)
    live_keys: set[str] = field(default_factory=set)


def audit_window(window: QWidget, allowlist: dict[str, str]) -> WindowAudit:
    """Audit one real window. Pure read: never mutates the registry or widgets."""
    window_name = type(window).__name__
    sections = registered_sections_of(window)
    window_key = f"{WINDOW_PREFIX}{window_name}"
    whole_reason = allowlist.get(window_key)
    # A whole-window exemption is honoured only while the window still has no
    # section at all — the ratchet that expires it once a follow-up lands.
    honour_whole_window = whole_reason is not None and not sections
    audit = WindowAudit(window_name=window_name)

    for widget in window.findChildren(QWidget):
        if not _is_interactive(window, widget):
            continue
        audit.interactive += 1
        if _owned(sections, widget):
            audit.owned += 1
            continue

        matched: str | None = None
        name = widget.objectName()
        candidates = [f"{window_name}:{name}"] if name else []
        candidates.append(f"{window_name}:{type(widget).__name__}")
        for key in candidates:
            if key in allowlist:
                matched = key
                break
        if matched is not None:
            audit.exempt.append((_control_id(widget), matched, allowlist[matched]))
            audit.live_keys.add(matched)
            continue
        if honour_whole_window:
            audit.exempt.append((_control_id(widget), window_key, whole_reason or ""))
            audit.live_keys.add(window_key)
            continue

        suggested = candidates[0]
        audit.violations.append(
            f"[{window_name}] {_chain(widget, window)} "
            f"(focusPolicy={widget.focusPolicy().name}) has no navigation owner; "
            f'if deliberate add "{suggested}" to tests/nav_coverage_allowlist.py '
            "with a written reason"
        )
    return audit


# ---------------------------------------------------------------------------
# Windows under contract (real classes, real registration)
# ---------------------------------------------------------------------------


def _add_i18n(plugin: str) -> None:
    from resources.translations import add_i18n_root

    add_i18n_root(_REPO_ROOT / "src" / "plugins" / plugin / "resources" / "i18n")


def _settings_args() -> dict:
    return dict(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_compare",
    )


def _build_settings(_tmp_path: Path) -> QWidget:
    _add_i18n("settings")
    from plugins.settings.dialog import SettingsDialog

    dialog = SettingsDialog(**_settings_args())
    dialog.show()
    _pump()
    return dialog


def _build_settings_keyboard(_tmp_path: Path) -> QWidget:
    _add_i18n("settings")
    from plugins.settings.dialog import SettingsDialog

    dialog = SettingsDialog(**_settings_args())
    dialog.show()
    _pump()
    dialog.select_section("builtin.keyboard")
    _pump(6)
    return dialog


def _build_help(_tmp_path: Path) -> QWidget:
    from plugins.help.dialog import HelpDialog

    dialog = HelpDialog("en", "Improve ImgSLI")
    dialog.show()
    _pump()
    return dialog


def _build_image_properties(_tmp_path: Path) -> QWidget:
    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import (
        ImageProperties,
        ImagePropertyRow,
        ImagePropertySection,
    )

    properties = ImageProperties(
        title="Properties",
        sections=tuple(
            ImagePropertySection(
                f"section_{i}",
                f"Section {i}",
                (ImagePropertyRow(f"row_{i}", "Name", f"value_{i}.png"),),
            )
            for i in range(2)
        ),
    )
    dialog = ImagePropertiesDialog(properties, current_language="en")
    dialog.show()
    _pump()
    return dialog


def _build_export(_tmp_path: Path) -> QWidget:
    _add_i18n("export")
    from domain.types import Color
    from plugins.export.dialog import ExportDialog
    from plugins.export.models import ExportDialogState

    state = ExportDialogState(
        current_language="en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=True,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
        virtual_canvas_active=True,
    )
    dialog = ExportDialog(dialog_state=state, suggested_filename="out")
    dialog.show()
    _pump()
    return dialog


def _build_color_picker(tmp_path: Path) -> QWidget:
    from ui.widgets.color import ColorPickerDialog, RecentColorsStore

    store = RecentColorsStore(
        QSettings(str(tmp_path / "nav_coverage_colors.ini"), QSettings.Format.IniFormat)
    )
    # 12 recents: the count the audit and the shipped picker both exercise.
    for i in range(12):
        store.add(f"#{16 + i:02X}{240 - i * 9:02X}{40 + i * 11:02X}")
    dialog = ColorPickerDialog(
        QColor("#101010"), None, show_alpha=True, recents_store=store
    )
    dialog.show()
    _pump()
    return dialog


def _build_clean_review(tmp_path: Path) -> QWidget:
    from tabs.image_gallery.tests.test_clean_review_parity import _make_owner
    from tabs.image_gallery.ui.clean_review import CleanReviewOverlay

    parent = QWidget()
    parent.resize(1280, 800)
    parent.show()
    owner = _make_owner(
        tmp_path,
        [str(tmp_path / f"rejected_{i}.jpg") for i in range(9)],
        folder=str(tmp_path),
    )
    overlay = CleanReviewOverlay(parent, owner=owner)
    overlay._nav_coverage_parent = parent  # strong ref: the overlay dies with it
    overlay._populate(owner)
    overlay.show_for(owner)
    _pump()
    return overlay


def _build_quick_look(tmp_path: Path) -> QWidget:
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.tests.test_quicklook_strip import _real_png, _show
    from tabs.image_gallery.ui.quick_look import QuickLookOverlay

    parent = QWidget()
    parent.resize(1280, 800)
    parent.show()
    overlay = QuickLookOverlay(parent)
    overlay._parity_test_parent = parent  # strong ref keeps the C++ tree alive
    paths = [_real_png(tmp_path, f"quicklook_{i}.png") for i in range(4)]
    items = [GalleryItem(path=p, mtime_ns=i + 1, rank=i + 1) for i, p in enumerate(paths)]
    # ``_show`` stamps the triage badges and builds the overlay's owner
    # namespace itself; the ring opens on the third item.
    _show(overlay, items[2], items)
    _pump()
    return overlay


def _build_unified_picker(_tmp_path: Path) -> QWidget:
    from ui.widgets.unified_list_picker import UnifiedListPicker

    host = QWidget()
    host.resize(900, 700)
    left_anchor = QWidget(host)
    left_anchor.setGeometry(50, 200, 220, 34)
    right_anchor = QWidget(host)
    right_anchor.setGeometry(450, 200, 220, 34)
    host.show()
    _pump()
    picker = UnifiedListPicker.create_double_list(
        host,
        left_anchor,
        right_anchor,
        left_items=["Alpha", "Beta", "Gamma", "Delta"],
        right_items=["One", "Two", "Three"],
    )
    picker.set_list_anchors(left_anchor, right_anchor)
    picker._nav_coverage_host = host  # strong ref: the picker dies with it
    picker.showAsSingle(1, left_anchor)
    _pump()
    picker.switchToDoubleMode()
    _pump(5)
    return picker


def _build_message_dialog(_tmp_path: Path) -> QWidget:
    from shared_toolkit.ui.message_dialog import AppMessageDialog, MessageKind

    dialog = AppMessageDialog(
        None,
        kind=MessageKind.WARNING,
        title="Watch out",
        text="Something happened.",
        checkbox_text="Remember",
        dont_ask_text="Do not ask again",
        cancel_text="Cancel",
    )
    dialog.show()
    _pump()
    return dialog


def _build_text_input(_tmp_path: Path) -> QWidget:
    from shared_toolkit.ui.text_input_dialog import AppTextInputDialog

    dialog = AppTextInputDialog(None, title="Rename", prompt="New name", text="old")
    dialog.show()
    _pump()
    return dialog


def _build_diagnostics(_tmp_path: Path) -> QWidget:
    from plugins.diagnostics.dialog import DiagnosticsDialog
    from plugins.diagnostics.report import DiagnosticsReport

    report = DiagnosticsReport(
        payload={"app": {"version": "test"}}, text="diagnostics line\n" * 5
    )
    dialog = DiagnosticsDialog(report, current_language="en")
    dialog.show()
    _pump()
    return dialog


def _build_video_editor(_tmp_path: Path) -> QWidget:
    from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog

    class _FakeExportController:
        store = None

    dialog = VideoEditorDialog([], _FakeExportController(), None)
    dialog.show()
    _pump()
    return dialog


@dataclass(frozen=True)
class WindowCase:
    name: str
    build: Callable[[Path], QWidget]


def _window_cases() -> list[WindowCase]:
    return [
        WindowCase("SettingsDialog", _build_settings),
        WindowCase("SettingsDialog/keyboard", _build_settings_keyboard),
        WindowCase("HelpDialog", _build_help),
        WindowCase("ImagePropertiesDialog", _build_image_properties),
        WindowCase("ExportDialog", _build_export),
        WindowCase("ColorPickerDialog", _build_color_picker),
        WindowCase("CleanReviewOverlay", _build_clean_review),
        WindowCase("QuickLookOverlay", _build_quick_look),
        WindowCase("UnifiedListPicker", _build_unified_picker),
        WindowCase("AppMessageDialog", _build_message_dialog),
        WindowCase("AppTextInputDialog", _build_text_input),
        WindowCase("DiagnosticsDialog", _build_diagnostics),
        WindowCase("VideoEditorDialog", _build_video_editor),
    ]


def _close(window: QWidget) -> None:
    try:
        window.close()
    except RuntimeError:
        pass
    try:
        window.deleteLater()
    except RuntimeError:
        pass
    _pump()


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_every_registered_window_control_is_owned_or_exempt(tmp_path: Path) -> None:
    """Every interactive control in every registered window has a nav owner."""
    allowlist = dict(NAV_COVERAGE_ALLOWLIST)
    audits: list[WindowAudit] = []
    violations: list[str] = []
    build_failed = False

    for case in _window_cases():
        window: QWidget | None = None
        try:
            window = case.build(tmp_path)
            _pump()
            assert window.isVisible(), (
                f"{case.name}: the window did not become visible offscreen — "
                "the audit would be vacuous"
            )
            audit = audit_window(window, allowlist)
            assert audit.interactive > 0, (
                f"{case.name}: the interactive predicate found no controls — "
                "the audit would be vacuous"
            )
            audits.append(audit)
            violations.extend(audit.violations)
            print(
                f"[nav-coverage] {case.name}: interactive={audit.interactive} "
                f"owned={audit.owned} exempt={len(audit.exempt)}",
                flush=True,
            )
        except Exception as exc:  # a build failure must not masquerade as green
            build_failed = True
            violations.append(
                f"[{case.name}] could not be audited: {type(exc).__name__}: {exc}"
            )
        finally:
            if window is not None:
                print(f"[nav-coverage] closing {case.name}", flush=True)
                _close(window)

    used_keys: set[str] = set()
    for audit in audits:
        used_keys |= audit.live_keys
    # A build failure leaves legitimate entries unmatched; report the build
    # failure alone instead of drowning it in false "stale" noise.
    stale = [] if build_failed else sorted(set(allowlist) - used_keys)

    problems: list[str] = []
    if violations:
        problems.append(
            "interactive controls with no navigation owner and no exemption:\n  "
            + "\n  ".join(violations)
        )
    if stale:
        problems.append(
            "stale allowlist entries (matched no current orphan — remove them):\n  "
            + "\n  ".join(f'"{key}": {allowlist[key]}' for key in stale)
        )
    assert not problems, (
        "Keyboard-coverage contract violated.\n\n" + "\n\n".join(problems)
    )


def test_allowlist_entries_are_reasoned_and_well_formed() -> None:
    """Every exemption states why; no blank or placeholder reason survives."""
    for key, reason in NAV_COVERAGE_ALLOWLIST.items():
        prefix, sep, ident = key.partition(":")
        assert sep and prefix and ident, f"malformed allowlist key: {key!r}"
        assert isinstance(reason, str), f"{key!r}: reason must be a string"
        text = reason.strip()
        assert len(text) >= 40, (
            f"{key!r}: reason is too short to be a written justification: "
            f"{text!r}"
        )
        lowered = text.lower()
        assert "todo" not in lowered and "fixme" not in lowered, (
            f"{key!r}: a placeholder is not a reason: {text!r}"
        )
        if prefix == WINDOW_PREFIX:
            assert ident[:1].isupper(), (
                f"{key!r}: a whole-window entry names a WindowClass, got {ident!r}"
            )
        elif ":" in ident:
            raise AssertionError(
                f"{key!r}: use one ':' between window and control identifier"
            )


# ---------------------------------------------------------------------------
# Falsification: the audit must flag a synthetic orphan and pass when owned
# ---------------------------------------------------------------------------


class _SyntheticWindow(QWidget):
    """A registered window with no production sections of its own."""


class _OwnsOne:
    """Minimal NavigationSection double owning exactly one widget."""

    def __init__(self, target: QWidget) -> None:
        self._target = target

    def owns(self, widget: QWidget) -> bool:
        return widget is self._target

    def navigate(self, key: int, widget: QWidget) -> bool:
        return False

    def focus_first(self, ref_x=None, *, reason: Qt.FocusReason) -> bool:
        self._target.setFocus(reason)
        return True

    def focus_last(self, ref_x=None, *, reason: Qt.FocusReason) -> bool:
        self._target.setFocus(reason)
        return True


def _synthetic_window() -> tuple[_SyntheticWindow, QWidget]:
    window = _SyntheticWindow()
    window.setObjectName("nav_coverage_synthetic")
    child = QWidget(window)
    child.setObjectName("synthetic_focus_target")
    child.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    window.resize(240, 120)
    window.show()
    _pump()
    return window, child


def test_contract_flags_and_names_a_synthetic_orphan() -> None:
    """A StrongFocus child outside every row is flagged and named."""
    window, _child = _synthetic_window()
    try:
        audit = audit_window(window, {})
        assert audit.violations, (
            "a StrongFocus child outside every row must be flagged"
        )
        assert any("synthetic_focus_target" in line for line in audit.violations), (
            "the violation must name the control (objectName + parent chain): "
            f"{audit.violations}"
        )
    finally:
        _close(window)


def test_contract_accepts_the_same_window_when_a_section_owns_the_control() -> None:
    """The identical widget tree passes once a section claims the control."""
    window, child = _synthetic_window()
    section = _OwnsOne(child)
    manager = _manager()
    manager.register(window, section)
    try:
        audit = audit_window(window, {})
        assert not audit.violations, (
            "a section owning the control must make the audit pass: "
            f"{audit.violations}"
        )
        assert audit.owned == 1
    finally:
        manager.unregister(window)
        _close(window)


def test_predicate_includes_a_nofocus_toolkit_button() -> None:
    """Click-only toolkit Buttons count even though Qt cannot focus them."""
    window = _SyntheticWindow()
    button = Button(parent=window)
    button.setObjectName("synthetic_click_only")
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    window.resize(240, 120)
    window.show()
    _pump()
    try:
        audit = audit_window(window, {})
        assert any("synthetic_click_only" in line for line in audit.violations), (
            "a toolkit Button must be audited even with NoFocus: "
            f"{audit.violations}"
        )
    finally:
        _close(window)


def test_whole_window_exemption_ratchets_once_a_section_appears() -> None:
    """``window:<Class>`` excuses a section-less window, then expires."""
    window, child = _synthetic_window()
    # A second focusable control the section below deliberately does NOT own:
    # once the window gains a section, the whole-window shortcut must stop and
    # the remaining orphan must be reported (and the key go stale).
    other = QWidget(window)
    other.setObjectName("synthetic_unowned_after_section")
    other.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    other.show()
    _pump()
    key = f"{WINDOW_PREFIX}_SyntheticWindow"
    allowlist = {key: "synthetic window deliberately has no section at all"}
    try:
        audit = audit_window(window, allowlist)
        assert not audit.violations
        assert key in audit.live_keys

        manager = _manager()
        section = _OwnsOne(child)
        manager.register(window, section)
        try:
            after = audit_window(window, allowlist)
            assert after.violations, (
                "a whole-window exemption must stop applying once the window "
                "registers a section (the ratchet)"
            )
            assert any(
                "synthetic_unowned_after_section" in line
                for line in after.violations
            ), after.violations
            assert key not in after.live_keys
        finally:
            manager.unregister(window)
    finally:
        _close(window)

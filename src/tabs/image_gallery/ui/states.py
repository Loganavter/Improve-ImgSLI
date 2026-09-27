"""Empty / scanning / ready state surface for the gallery.

S0 uses ``DropZoneLabel`` + ``DragDropOverlay`` per the toolkit mapping.
Thin-owner style: plain functions could drive the state from the controller,
but the widget itself exposes ``set_state("empty"|"scanning"|"ready", n)``.
"""

from __future__ import annotations

from sli_ui_toolkit.managers import scaled_px

import time

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import DragDropOverlay, DropZoneLabel, Label, LoadingSpinner


class GalleryEmptyState(QWidget):
    """S0 empty state plus scanning/ready handling.

    Contains a ``DropZoneLabel`` (drag target) and a
    ``DragDropOverlay`` (window overlay painter for S0). Also shows a
    ``LoadingSpinner`` + count label during scanning.

    Signals:
        fileDropped(str) — path dropped onto the zone.
        openRequested — legacy (Open Folder button removed; never emitted).
    """

    fileDropped = Signal(str)
    openRequested = Signal()

    # Single-flight window for open requests (legacy — Open Folder button
    # removed; kept so rapid programmatic _request_open calls still collapse).
    _OPEN_SINGLE_FLIGHT_S = 0.6

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        translate: Callable[[str, str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GalleryEmptyState")
        self._tr = translate
        self._state: str = "empty"
        self._last_open_emit: float = 0.0

        def _tr(key: str, default: str) -> str:
            if translate is None:
                return default
            try:
                return translate(key, default)
            except Exception:
                return default

        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled_px(32), scaled_px(32), scaled_px(32), scaled_px(32))
        layout.setSpacing(scaled_px(16))
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_text = _tr("image_gallery.empty_state", "Drop folder or images here")
        self._default_empty_text = empty_text
        # DropZoneLabel is the S0 drop surface — make it prominent, like session_picker empty.
        # W12 W-C: expanding zone that fills available space — no fixed
        # minimum height (toolkit default 80px floor applies); the layout
        # stretch below gives it the free vertical space.
        self._drop_label = DropZoneLabel(empty_text, self)
        self._drop_label.setObjectName("gallery_empty_drop_zone")
        self._drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            self._drop_label.setPixelSize(16)
        except Exception:
            pass
        # Make it expand to fill width AND height while keeping centered
        try:
            from PySide6.QtWidgets import QSizePolicy as _QSP
            self._drop_label.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Expanding)
        except Exception:
            pass

        # No hint label, no Open Folder button — drop-only zone.
        # Zone click does NOT open the folder dialog.

        # Scanning row: spinner + "Scanning… n"
        self._spinner = LoadingSpinner(self)
        self._spinner.setObjectName("gallery_scanning_spinner")
        self._spinner.hide()
        self._scanning_label = Label("", pixel_size=16)
        self._scanning_label.setObjectName("gallery_scanning_label")
        self._scanning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scanning_label.hide()

        # Add with stretch to center vertically
        layout.addStretch(1)
        layout.addWidget(self._drop_label, 1)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._scanning_label)
        layout.addStretch(1)

        # Drag overlay for window-level highlight (S0). For offscreen/tests keep
        # parent as self to avoid window-level ownership that breaks qtbot teardown
        # (window -> overlay -> widget double-delete). Visual highlight still works
        # when shown via overlay parented to self.
        try:
            self._overlay = DragDropOverlay(self)
            self._overlay.hide()
        except Exception:
            self._overlay = None  # type: ignore[assignment]

        # Wire drop zone signals.
        try:
            self._drop_label.file_dropped.connect(self.fileDropped.emit)
        except Exception:
            pass
        try:
            self._drop_label.drop_zone_drag_active.connect(self._on_drag_active)
        except Exception:
            pass

        self._ensure_overlay_parent()

    # -- open single-flight -------------------------------------------------

    def _request_open(self) -> None:
        """Emit ``openRequested`` at most once per single-flight window.

        Legacy — Open Folder button removed, kept for compat (e.g. toolbar
        still emits ``folder_pick_requested`` directly).
        """
        now = time.monotonic()
        if now - self._last_open_emit < self._OPEN_SINGLE_FLIGHT_S:
            return
        self._last_open_emit = now
        try:
            self.openRequested.emit()
        except Exception:
            pass

    # -- overlay helpers --------------------------------------------------

    def _ensure_overlay_parent(self) -> None:
        # No-op: keep overlay parented to self to keep teardown deterministic.
        return

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)

    def _on_drag_active(self, active: bool) -> None:
        # S0 single drop zone — rely on DropZoneLabel's own drag_active paint
        # (dashed accent border + fill). Don't show the two-half DragDropOverlay
        # (which is for compare's left/right slots) — it creates the two huge
        # blue squares seen in the screenshot vs the expected single dashed zone.
        if self._overlay is not None:
            try:
                self._overlay.set_overlay_state(False, self.geometry())
                self._overlay.hide()
            except Exception:
                pass
        # DropZoneLabel already updates its own _drag_active via dragEnter/Leave
        # and repaints with accent fill; no extra overlay needed.

    # -- empty message ------------------------------------------------------

    def set_empty_message(self, text: str) -> None:
        """Swap the drop-zone message (e.g. view emptied by removals — files stay on disk)."""
        try:
            self._drop_label.setText(text)
        except Exception:
            pass

    def restore_empty_message(self) -> None:
        """Restore the default pick-a-folder message (pristine empty, nothing ever opened)."""
        try:
            self._drop_label.setText(self._default_empty_text)
        except Exception:
            pass

    # -- state machine ----------------------------------------------------

    def set_state(self, state: str, n: int = 0, total: int | None = None) -> None:
        """Switch between ``empty`` / ``scanning`` / ``ready``.

        * ``empty``  — S0: drop zone visible, spinner hidden.
        * ``scanning`` — S1: spinner + ``Scanning n/N`` only, drop zone hidden
          (drops still land via the whole-widget drop handling).
        * ``ready``  — S2: hide the whole widget (grid owns content).
        """
        state = str(state).lower()
        self._state = state
        if state == "empty":
            self.show()
            self._drop_label.show()
            self._spinner.hide()
            try:
                self._spinner.stop()
            except Exception:
                pass
            self._scanning_label.hide()
            self._scanning_label.setText("")
            if self._overlay is not None:
                try:
                    self._overlay.set_overlay_state(False, self.geometry())
                except Exception:
                    pass
        elif state == "scanning":
            self.show()
            # Drop zone stays hidden while scanning — spinner + count only.
            self._drop_label.hide()
            self._spinner.show()
            try:
                self._spinner.start()
            except Exception:
                pass
            self._scanning_label.show()
            # Scanning text — S1 spinner n/N (A1 parity). Fallback to n if total missing.
            if total is not None:
                try:
                    t_i = int(total)
                    n_i = int(n)
                    default = f"Scanning {n_i}/{t_i}" if t_i > 0 else f"Scanning {n_i}"
                except Exception:
                    default = f"Scanning {int(n)}"
            else:
                default = f"Scanning {int(n)}"
            # Keep ellipsis-style fallback for legacy translations: scanning ellipsis → n/N
            if self._tr is not None:
                try:
                    txt = self._tr("image_gallery.scanning", default)
                    # If translation is missing and returns key, fallback to default with count.
                    if txt == "image_gallery.scanning":
                        txt = default
                    # Support placeholder style in translation json: "{n}/{total}" or "{n}"
                    if "{n}" in txt or "{total}" in txt:
                        try:
                            txt = txt.replace("{n}", str(int(n))).replace("{total}", str(int(total) if total is not None else ""))
                        except Exception:
                            pass
                except Exception:
                    txt = default
            else:
                txt = default
            self._scanning_label.setText(txt)
        elif state == "ready":
            # Content ready — hide empty state entirely.
            if self._overlay is not None:
                try:
                    self._overlay.set_overlay_state(False, self.geometry())
                except Exception:
                    pass
            try:
                self._spinner.stop()
            except Exception:
                pass
            self.hide()
        else:
            # Unknown state — treat as empty.
            self.show()
            self._drop_label.show()

    @property
    def current_state(self) -> str:
        return self._state

    # Re-export sub-widgets for controller/tests.
    @property
    def overlay(self) -> DragDropOverlay | None:
        return self._overlay

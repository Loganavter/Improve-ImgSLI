"""Shared window-edge padding for workspace control rows.

Both workspace tabs (``image_compare``, ``multi_compare``) and plugins
(``settings``, ``help``, …) build control rows / footers that must line up
flush with each other from the window edge. Keep the single design-px value
here instead of each consumer picking its own inset; all callers resolve it
through ``control_edge_padding()`` so it scales with ``UiScale``.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

CONTROL_EDGE_PADDING_PX = 8


def control_edge_padding() -> int:
    """Horizontal window-edge padding for control rows, in live (scaled) px."""
    return scaled_px(CONTROL_EDGE_PADDING_PX)


def sidebar_header_host(widget: QWidget, *, pad: int | None = None) -> QWidget:
    """Wrap a ``SidebarDialogShell`` ``sidebar_header`` with edge insets.

    The shell pins the header flush inside its margin-free sidebar column,
    while the nav list below already carries its own row insets — so a bare
    search field spans the column edge-to-edge, touching the window edge on
    the left and the splitter divider on the right. Wrapping the header gives
    it the same breathing room without moving the nav list. Returns the host
    to pass as ``sidebar_header=``.
    """
    inset = control_edge_padding() if pad is None else pad
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(inset, inset, inset, 0)
    layout.setSpacing(0)
    layout.addWidget(widget)
    return host

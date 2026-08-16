"""Compat shim: slider hint flyout moved to the shared app widget layer.

The magnifier-panel sliders are now ``ValueSlider`` (see
``ui/widgets/slider_hint.py``), which embeds the hint flyout itself, so
``widget.py`` no longer wires a ``SliderHintController`` externally. Keep
the old import path working for anything still referencing it.
"""

from __future__ import annotations

from ui.widgets.slider_hint import (
    SliderHintController,
    SliderHintFlyout,
    ValueSlider,
    _percent_text,
)

__all__ = [
    "SliderHintController",
    "SliderHintFlyout",
    "ValueSlider",
    "_percent_text",
]
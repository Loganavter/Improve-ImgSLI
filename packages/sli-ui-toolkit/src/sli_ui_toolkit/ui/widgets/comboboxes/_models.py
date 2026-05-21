from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

@dataclass
class _ComboItem:
    text: str
    data: Any = None
    normalized_text: str = ""

    def __post_init__(self) -> None:
        self.normalized_text = normalize_for_search(self.text)

"""The settings page no longer warns that the AI key is "stored unencrypted".

The warning was true: the key lived in the ``QSettings`` INI as plain text.
It was removed together with the storage change (the key now goes through
``core.secret_store``) — the caption and its locale key went away in the same
change. The storage half is gallery-owned
(``src/tabs/image_gallery/tests/plugins/test_ai_key_storage.py``); this file
only pins the host settings page.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from plugins.settings.dialog import SettingsDialog
from sli_ui_toolkit.managers import UiScale


@pytest.fixture(autouse=True)
def _scale_one():
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


def test_the_settings_page_no_longer_warns_about_unencrypted_storage(
    qapp: QApplication,
):
    dialog = SettingsDialog("en", "dark", 60, 10, 200, False, True)
    dialog.show()
    qapp.processEvents()
    try:
        captions = [
            child.text()
            for child in dialog.findChildren(QWidget)
            if hasattr(child, "text") and callable(getattr(child, "text", None))
        ]
        joined = " ".join(str(c) for c in captions).casefold()
        assert "незашифрован" not in joined
        assert "unencrypted" not in joined
    finally:
        dialog.close()

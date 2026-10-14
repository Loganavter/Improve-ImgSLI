"""Gallery page must hand the toolkit a ``(key, language) -> str`` translator.

``install_translator`` fans out ``(key, language)``; ``TabContext._tr`` is a
``(key, default)`` resolver that ignores the language. The page must bind
``TabContext._tr_lang`` so an explicit language is honored.
"""

from __future__ import annotations

from pathlib import Path

from resources.translations import add_i18n_root

from tabs.contract import TabContext
from tabs.image_gallery.widget import ImageGalleryWidget


def _register_gallery_i18n() -> None:
    repo = Path(__file__).resolve().parents[4]
    add_i18n_root(repo / "src" / "tabs" / "image_gallery" / "resources" / "i18n")


def test_tab_context_tr_lang_honors_explicit_language() -> None:
    _register_gallery_i18n()
    ctx = TabContext()
    assert ctx._tr_lang("image_gallery.badge.source", "ru") == "ИСТОЧНИК"
    assert ctx._tr_lang("no.such.key.xyz", "ru") == "no.such.key.xyz"


def test_gallery_page_binds_conforming_translator(qtbot, monkeypatch) -> None:
    _register_gallery_i18n()
    import sli_ui_toolkit.i18n as toolkit_i18n

    captured: dict = {}
    real_install = toolkit_i18n.install_translator

    def _spy(root, tr_func, *args, **kwargs):
        captured["tr"] = tr_func
        return real_install(root, tr_func, *args, **kwargs)

    monkeypatch.setattr(toolkit_i18n, "install_translator", _spy)

    ctx = TabContext()
    w = ImageGalleryWidget(context=ctx)
    qtbot.addWidget(w)

    translator = captured.get("tr")
    assert callable(translator), "install_translator was not given a callable"
    assert translator("image_gallery.badge.source", "ru") == "ИСТОЧНИК"
    assert translator("image_gallery.badge.source", "en") != "ИСТОЧНИК"

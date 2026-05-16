"""Tests for the toolkit i18n system (TranslationManager)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "packages",
        "sli-ui-toolkit",
        "src",
    ),
)

from sli_ui_toolkit.i18n import TranslationManager, _deep_merge, _resolve_dotted_key

def _make_i18n_tree(tmp: Path, lang: str, data: dict) -> None:
    lang_dir = tmp / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    (lang_dir / "strings.json").write_text(json.dumps(data), encoding="utf-8")

def _fresh_manager(i18n_root: Path) -> TranslationManager:
    mgr = TranslationManager()
    TranslationManager._instance = None
    mgr = TranslationManager()
    mgr.set_i18n_root(i18n_root)
    return mgr

class TestDeepMerge:
    def test_simple_merge(self):
        base = {"a": 1}
        _deep_merge(base, {"b": 2}, "test", warn_on_override=False)
        assert base == {"a": 1, "b": 2}

    def test_nested_merge(self):
        base = {"ui": {"button": "ok"}}
        _deep_merge(base, {"ui": {"label": "hi"}}, "test", warn_on_override=False)
        assert base == {"ui": {"button": "ok", "label": "hi"}}

    def test_override(self):
        base = {"a": "old"}
        _deep_merge(base, {"a": "new"}, "test", warn_on_override=False)
        assert base == {"a": "new"}

class TestResolveDottedKey:
    def test_flat_key(self):
        assert _resolve_dotted_key({"hello": "world"}, "hello") == "world"

    def test_nested_key(self):
        data = {"ui": {"button": {"ok": "OK"}}}
        assert _resolve_dotted_key(data, "ui.button.ok") == "OK"

    def test_missing_key_returns_key(self):
        assert _resolve_dotted_key({}, "missing.key") == "missing.key"

class TestTranslationManager:
    def test_loads_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_i18n_tree(root, "en", {"greeting": "Hello"})
            mgr = _fresh_manager(root)
            mgr.load_language("en")
            assert mgr.get("greeting") == "Hello"

    def test_loads_language_with_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_i18n_tree(root, "en", {"greeting": "Hello", "farewell": "Bye"})
            _make_i18n_tree(root, "ru", {"greeting": "Привет"})
            mgr = _fresh_manager(root)
            mgr.load_language("ru")
            assert mgr.get("greeting") == "Привет"
            assert mgr.get("farewell") == "Bye"

    def test_missing_key_returns_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_i18n_tree(root, "en", {"a": "b"})
            mgr = _fresh_manager(root)
            mgr.load_language("en")
            assert mgr.get("nonexistent") == "nonexistent"

    def test_format_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_i18n_tree(root, "en", {"msg": "Hello {0}!"})
            mgr = _fresh_manager(root)
            mgr.load_language("en")
            assert mgr.get("msg", "World") == "Hello World!"

    def test_caching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_i18n_tree(root, "en", {"k": "v"})
            mgr = _fresh_manager(root)
            mgr.load_language("en")
            mgr.load_language("en")
            assert len(mgr._cache) == 1

    def test_no_root_returns_empty(self):
        mgr = TranslationManager()
        TranslationManager._instance = None
        mgr = TranslationManager()
        mgr.load_language("en")
        assert mgr.get("anything") == "anything"

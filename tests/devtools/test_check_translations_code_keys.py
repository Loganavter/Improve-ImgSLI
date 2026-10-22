"""Falsifiable fixtures for the code-key mode of the translations checker.

The checker under test is ``src/devtools/check_translations.py --code-keys``.
It answers a question the parity check cannot: *does the key a widget asks for
exist in a catalog at all?* The owner report that motivated it (2026-10-22) was
a switch whose state text fell back to English because the widget requested
``common.switch.switch_on`` while the catalog had ``common.switch.off`` — parity
was green, the UI was half-translated.

Each test builds a throwaway tree and runs the real CLI entry point, so a
regression that makes the scanner a silent no-op fails here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "src" / "devtools" / "check_translations.py"


def _load_checker():
    """Load the checker from its path (registering it for dataclass/annotations)."""
    spec = importlib.util.spec_from_file_location("check_translations_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checker():
    return _load_checker()


def _tree(tmp_path: Path, code: str, catalog: dict | None = None) -> tuple[Path, Path]:
    src = tmp_path / "src"
    root = src / "resources" / "i18n"
    (root / "en").mkdir(parents=True)
    (root / "en" / "common.json").write_text(
        json.dumps(catalog if catalog is not None else {"common": {"ok": "OK"}}),
        encoding="utf-8",
    )
    (src / "feature.py").write_text(code, encoding="utf-8")
    return root, src


def _run(checker, root: Path, src: Path, allowlist: Path | None = None) -> int:
    argv = ["--root", str(root), "--code-keys", "--code-src", str(src), "--strict"]
    argv += ["--code-allowlist", str(allowlist)] if allowlist else []
    return checker.main(argv)


def test_a_present_literal_key_passes(checker, tmp_path, capsys):
    root, src = _tree(tmp_path, 'from x import tr\nTEXT = tr("common.ok")\n')

    assert _run(checker, root, src) == 0
    assert "code keys OK" in capsys.readouterr().out


def test_a_missing_literal_key_fails(checker, tmp_path, capsys):
    root, src = _tree(tmp_path, 'from x import tr\nTEXT = tr("common.missing")\n')

    assert _run(checker, root, src) == 1
    out = capsys.readouterr().out
    assert "MISSING   common.missing" in out
    assert "feature.py:2" in out


def test_the_switch_key_shape_is_caught(checker, tmp_path, capsys):
    """The exact 2026-10-22 shape: catalog has ``off``, code asks ``switch_on``."""
    root, src = _tree(
        tmp_path,
        'from x import tr\nTEXT = tr("common.switch.switch_on", default="On")\n',
        {"common": {"switch": {"off": "Выкл"}}},
    )

    assert _run(checker, root, src) == 1
    assert "common.switch.switch_on" in capsys.readouterr().out


def test_the_allowlist_waives_a_dynamic_key(checker, tmp_path, capsys):
    root, src = _tree(tmp_path, 'from x import tr\nTEXT = tr("dynamic.key")\n')
    allow = tmp_path / "allow.txt"
    allow.write_text("dynamic.key  # built at runtime from a feature prefix\n", encoding="utf-8")

    assert _run(checker, root, src, allow) == 0
    out = capsys.readouterr().out
    assert "allowed   dynamic.key" in out
    assert "built at runtime" in out


def test_only_literal_first_arguments_are_scanned(checker, tmp_path):
    """A key held in a variable is not a literal and must not be reported."""
    root, src = _tree(
        tmp_path,
        'from x import tr\nKEY = "common.ok"\nA = tr(KEY)\nB = tr(f"common.{KEY}")\n',
    )

    assert _run(checker, root, src) == 0

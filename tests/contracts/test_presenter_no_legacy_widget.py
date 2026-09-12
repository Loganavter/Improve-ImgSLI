"""MainWindowPresenter is tab-independent: no legacy image_compare widget.

Dogma source: docs/dev/presenter-decoupling-plan.md (Stages 1-5). The host
``MainWindowPresenter`` used to be hard-wired to the image_compare tab's page
widget (``presenter.widget``), which meant removing that tab broke app
bootstrap. After the decoupling the presenter takes no ``widget=`` parameter,
``MainWindowComposer`` no longer reads ``window.image_compare_widget``, and
platform presenter code never accesses a ``.widget`` attribute at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import SRC, read, rel

HOST_ROOTS = (
    SRC / "ui" / "presenters" / "main_window",
    SRC / "ui" / "main_window",
)

PRESENTER_INIT = SRC / "ui" / "presenters" / "main_window" / "presenter.py"
COMPOSER = SRC / "ui" / "main_window" / "composer.py"


def _iter_host_py_files() -> list[Path]:
    files: list[Path] = []
    for root in HOST_ROOTS:
        if not root.is_dir():
            continue
        files.extend(
            p for p in root.rglob("*.py") if "__pycache__" not in p.parts
        )
    return sorted(files)


def test_presenter_init_takes_no_widget_parameter():
    tree = ast.parse(read(PRESENTER_INIT))
    init = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    arg_names = [arg.arg for arg in init.args.args]
    assert "widget" not in arg_names


def test_composer_does_not_read_or_pass_the_legacy_widget():
    text = read(COMPOSER)
    assert "widget=" not in text
    assert "image_compare_widget" not in text


def test_host_presenter_code_has_no_widget_attribute_access():
    offenders: list[str] = []
    for py in _iter_host_py_files():
        tree = ast.parse(read(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "widget":
                offenders.append(f"{rel(py)}:{node.lineno}: ...{node.attr}")
    assert not offenders, (
        "Platform presenter code still reaches a '.widget' attribute — the "
        "image_compare page must be driven through tab-owned services, not a "
        "widget cached on the host presenter:\n  - " + "\n  - ".join(offenders)
    )

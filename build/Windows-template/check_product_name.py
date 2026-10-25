#!/usr/bin/env python3
"""Fail the build when the product name half-landed in the packaging layer.

``src/core/log_names.py`` (``APP_NAME``) is the one spelling of the product
name. ``product_name.py`` derives the Windows artifact names from it, and the
Inno script repeats them as literals (Inno's preprocessor cannot import
Python). This script is the gate that keeps those three in agreement:

* ``MyAppExeName`` is ``<APP_NAME>.exe``;
* ``MyAppSetupName`` starts with ``<APP_NAME>_Setup_v``;
* the installer copies from ``dist\\<APP_NAME>\\``;
* the installer declares a fixed ``AppId`` (no implicit AppName-derived id);
* the spec file is ``<APP_NAME>.spec``;
* ``build_windows.py`` (and the spec) contain no literal product name and no
  pre-rename name — ``SETUP_EXE``/``DIST_DIR``/``BUNDLE_EXE``/``dist_exe()``
  must be derived, not spelled.

Run from anywhere: ``python build/Windows-template/check_product_name.py``.
Exit 0 prints ``product-name consistency OK``.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import uuid
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent
if str(TEMPLATE_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_DIR))

from product_name import (  # noqa: E402  (needs TEMPLATE_DIR on sys.path)
    APP_NAME,
    APP_VERSION,
    BUNDLE_EXE,
    BUNDLE_EXE_NAME,
    DIST_DIR,
    INNO_PATH,
    SETUP_EXE,
    SPEC_PATH,
)
from core.log_names import LEGACY_LOGGER_NAME  # noqa: E402  (product_name added src/)

BUILD_WINDOWS_PATH = TEMPLATE_DIR / "build_windows.py"

#: Names the product carried before the rename, reduced to one comparison token
#: so every pre-rename spelling matches after normalisation (underscore, hyphen,
#: space, lowercase-kebab). The values live in ``src/core/log_names.py`` as
#: ``LEGACY_*``.
LEGACY_NAME = LEGACY_LOGGER_NAME

#: Brand asset file names that legitimately contain the product token without
#: being the product identity (the project-file icon next to ``icon.ico``).
_ALLOWED_ASSET_LITERALS = frozenset({"blinktable-file.ico"})

#: Module-level names in build_windows.py whose values must be derived from the
#: imported product-name constants instead of being spelled out.
DERIVED_ASSIGNMENTS = ("SPEC_PATH", "SETUP_EXE", "DIST_DIR", "BUNDLE_EXE")
DERIVED_FUNCTIONS = ("dist_exe",)

_failures: list[str] = []


def _fail(message: str) -> None:
    _failures.append(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _iss_defines(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r'^#define\s+(\w+)\s+"([^"]*)"\s*$', text, re.MULTILINE
        )
    }


def _app_id(text: str) -> str | None:
    match = re.search(r"^AppId=(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


_PRODUCT_TOKENS = tuple({_normalise(APP_NAME), _normalise(LEGACY_NAME)})


def _spells_product_name(literal: str) -> bool:
    if literal in _ALLOWED_ASSET_LITERALS:
        return False
    normalised = _normalise(literal)
    return any(token and token in normalised for token in _PRODUCT_TOKENS)


def _spelled_literals(path: Path) -> list[str]:
    """String literals in ``path`` that spell a product name."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sorted(
        {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _spells_product_name(node.value)
        }
    )


def _derives_without_product_literal(path: Path) -> list[str]:
    """Return names in ``path`` that spell a product name instead of deriving it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []

    def _spells_name(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and _spells_product_name(child.value)
            for child in ast.walk(node)
        )

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = {
                target.id for target in node.targets if isinstance(target, ast.Name)
            }
            if targets & set(DERIVED_ASSIGNMENTS) and _spells_name(node.value):
                offenders.append(sorted(targets & set(DERIVED_ASSIGNMENTS))[0])
        elif isinstance(node, ast.FunctionDef) and node.name in DERIVED_FUNCTIONS:
            if _spells_name(node):
                offenders.append(node.name)

    return offenders


def _check_inno(text: str) -> None:
    defines = _iss_defines(text)

    _require(
        defines.get("MyAppName") == APP_NAME,
        f"inno_setup_6.iss: MyAppName={defines.get('MyAppName')!r} != APP_NAME={APP_NAME!r}",
    )
    _require(
        defines.get("MyAppExeName") == f"{APP_NAME}.exe",
        f"inno_setup_6.iss: MyAppExeName={defines.get('MyAppExeName')!r} "
        f"!= {APP_NAME}.exe",
    )
    setup_name = defines.get("MyAppSetupName", "")
    _require(
        setup_name.startswith(f"{APP_NAME}_Setup_v"),
        f"inno_setup_6.iss: MyAppSetupName={setup_name!r} "
        f"does not start with {APP_NAME}_Setup_v",
    )
    _require(
        defines.get("MyAppVersion") == APP_VERSION,
        f"inno_setup_6.iss: MyAppVersion={defines.get('MyAppVersion')!r} "
        f"!= {APP_VERSION!r}",
    )

    source_dirs = set(re.findall(r'^Source:\s*"\.\.\\\.\.\\dist\\([^\\"]+)\\', text, re.MULTILINE))
    _require(
        source_dirs == {APP_NAME},
        f"inno_setup_6.iss: [Files] dist source dir(s) {sorted(source_dirs)} "
        f"must be exactly {APP_NAME}",
    )

    app_id = _app_id(text)
    if app_id is None:
        _fail(
            "inno_setup_6.iss: no AppId — Inno would derive it from AppName, so a "
            "renamed build installs as a second application instead of upgrading"
        )
    else:
        guid = app_id.lstrip("{").rstrip("}")
        try:
            uuid.UUID(guid)
        except ValueError:
            _fail(f"inno_setup_6.iss: AppId={app_id!r} is not a GUID")


def _check_derived_scripts() -> None:
    _require(
        SPEC_PATH.is_file(),
        f"missing spec file {SPEC_PATH.name} (the spec must be named <APP_NAME>.spec)",
    )

    for path in (SPEC_PATH, BUILD_WINDOWS_PATH):
        if not path.is_file():
            continue
        for literal in _spelled_literals(path):
            _fail(
                f"{path.name}: spells a product name in {literal!r} — import it "
                "from product_name.py instead"
            )

    if not BUILD_WINDOWS_PATH.is_file():
        return

    for name in _derives_without_product_literal(BUILD_WINDOWS_PATH):
        _fail(
            f"build_windows.py: {name} spells a product name instead of deriving it "
            f"from product_name (APP_NAME={APP_NAME!r})"
        )

    spec = importlib.util.spec_from_file_location(
        "build_windows_product_name_check", BUILD_WINDOWS_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected_setup = SETUP_EXE
    _require(
        Path(module.SETUP_EXE) == expected_setup,
        f"build_windows.py: SETUP_EXE={module.SETUP_EXE!r} != {expected_setup!r}",
    )
    _require(
        Path(module.DIST_DIR) == DIST_DIR,
        f"build_windows.py: DIST_DIR={module.DIST_DIR!r} != {DIST_DIR!r}",
    )
    _require(
        Path(module.dist_exe()) == DIST_DIR / BUNDLE_EXE_NAME,
        f"build_windows.py: dist_exe()={module.dist_exe()!r} "
        f"!= {DIST_DIR / BUNDLE_EXE_NAME!r}",
    )
    _require(
        Path(module.SPEC_PATH) == SPEC_PATH,
        f"build_windows.py: SPEC_PATH={module.SPEC_PATH!r} != {SPEC_PATH!r}",
    )
    # BUNDLE_EXE is imported by build_windows.py; assert it is the same artifact.
    _require(Path(BUNDLE_EXE) == DIST_DIR / BUNDLE_EXE_NAME, "product_name BUNDLE_EXE drift")


def main() -> int:
    _check_inno(INNO_PATH.read_text(encoding="utf-8"))
    _check_derived_scripts()

    if _failures:
        for message in _failures:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    print(f"product: {APP_NAME} {APP_VERSION}")
    print(f"bundle: {DIST_DIR / BUNDLE_EXE_NAME}")
    print(f"setup:  {SETUP_EXE}")
    print("product-name consistency OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

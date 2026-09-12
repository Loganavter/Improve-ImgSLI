"""Tab-owned icon assets — each tab resolves icons from its own resources/."""

from __future__ import annotations

import importlib
from enum import Enum
from pathlib import Path

import pytest

from ._framework import ROOT, rel

TABS = ROOT / "src" / "tabs"


def _tab_packages() -> list[Path]:
    if not TABS.is_dir():
        return []
    return sorted(
        d
        for d in TABS.iterdir()
        if d.is_dir() and not d.name.startswith("_") and d.name != "__pycache__"
    )


TAB_PKGS = _tab_packages()
TAB_IDS = [d.name for d in TAB_PKGS]


@pytest.mark.parametrize("pkg", TAB_PKGS, ids=TAB_IDS)
def test_tab_icons_module_resolves_from_local_resources(pkg: Path):
    icons_py = pkg / "icons.py"
    if not icons_py.is_file():
        pytest.skip(f"{pkg.name} has no icons.py")

    mod = importlib.import_module(f"tabs.{pkg.name}.icons")
    icon_enum = getattr(mod, "Icon", None)
    get_icon = getattr(mod, "get_icon", None)
    assert isinstance(icon_enum, type) and issubclass(icon_enum, Enum)
    assert callable(get_icon)

    icons_root = pkg / "resources" / "icons"
    assert icons_root.is_dir(), f"{rel(icons_py)}: missing {rel(icons_root)}"

    missing: list[str] = []
    for member in icon_enum:
        filename = member.value
        for theme in ("light", "dark"):
            path = icons_root / theme / filename
            if not path.is_file():
                missing.append(str(rel(path)))
        icon = get_icon(member)
        assert not icon.isNull(), f"{pkg.name}.{member.name} resolved to null icon"

    assert not missing, "Missing tab icon assets:\n  - " + "\n  - ".join(missing)

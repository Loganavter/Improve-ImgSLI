"""Every build target must ship the versions `requirements-gui.txt` pins.

Owner report 2026-10-28: «надо проверить что во всех билд сборках у нас те же
рекваеремменты что в requirements-gui.txt». The audit found real drift in the
Flatpak template (pillow 11.2.1 vs 12.1.1, Markdown 3.8.1 vs 3.8) and a stale
helper listing that still named scikit-image 0.25.2 while the module tree built
0.26.0.

The packagings answer the question in two different ways, and both must keep
answering it the same way:

* **pip-installed targets** (Windows PyInstaller build, the CI jobs) install
  ``requirements-gui.txt`` itself — there is nothing to drift, but the wiring is
  asserted here so a future "pip install -r build/…" cannot quietly replace it.
* **the Flatpak module tree** vendors wheels/sdists, so each module restates a
  version. Those restatements are compared against the source of truth.
* **the AUR package** depends on distro packages (unpinned by design — the
  distro decides), so only the package *set* is compared.

Red-before: with the pinned versions this file compares, the previous tree failed
on pillow (11.2.1 != 12.1.1) and Markdown (3.8.1 != 3.8).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "requirements-gui.txt"
FLATPAK_MODULES = REPO_ROOT / "build/Flatpak-template/python3-modules.json"
FLATPAK_REQUIREMENTS = REPO_ROOT / "build/Flatpak-template/requirements.txt"
AUR_PKGBUILD = REPO_ROOT / "build/AUR-template/PKGBUILD"
WINDOWS_BUILDER = REPO_ROOT / "build/Windows-template/build_windows.py"

#: ``requirements-gui.txt`` name -> Flatpak module name.
FLATPAK_MODULES_BY_PACKAGE = {
    "markdown": "python3-Markdown",
    "pillow": "python3-pillow",
    "numpy": "python3-numpy",
    "pyside6-essentials": "python3-PySide6-Essentials",
    "shiboken6": "python3-shiboken6",
    "sli-ui-toolkit": "python3-sli-ui-toolkit",
    "scikit-image": "python3-scikit-image",
    "imagecodecs": "python3-imagecodecs",
    "pyvips": "python3-pyvips",
    "torch": "python3-torch",
    "torchvision": "python3-torchvision",
    "piq": "python3-piq",
}

#: ``requirements-gui.txt`` name -> AUR package name (distro versions, unpinned).
AUR_PACKAGES = {
    "markdown": "python-markdown",
    "pillow": "python-pillow",
    "numpy": "python-numpy",
    "pyside6-essentials": "pyside6",
    "sli-ui-toolkit": "python-sli-ui-toolkit",
    "scikit-image": "python-scikit-image",
    "imagecodecs": "python-imagecodecs",
    "pyvips": "python-pyvips",
    "torch": "python-pytorch",
    "torchvision": "python-torchvision",
    # piq ships as a vendored wheel from the AUR source list, see PKGBUILD
}

#: Packages whose Flatpak module deliberately differs in *version* from the pin.
VERSION_EXEMPT: dict[str, str] = {}

#: Editable-only in the dev requirements (``-e ../sli-ui-toolkit``): the Flatpak
#: vendors the released tarball, so only "a version is stated" is checked.
EDITABLE_ONLY = {"sli-ui-toolkit"}


def _parse_requirements(path: Path) -> dict[str, tuple[str, str]]:
    """``name -> (operator, version)`` for every pinned line."""
    out: dict[str, tuple[str, str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"([A-Za-z0-9_.\-]+)(\[[^\]]+\])?\s*(==|>=|<=|~=|>|<)\s*([^,;]+)", line)
        if not match:
            continue
        name = match.group(1).lower()
        version = match.group(4).strip().split(",")[0].strip()
        out[name] = (match.group(3), version)
    return out


def _flatpak_pins() -> dict[str, dict[str, str]]:
    """Module name -> {package: version} from its ``pip3 install`` command.

    A module may pin several packages (pyvips also installs cffi), so the
    comparison has to look up the mapped package, not "the first ==version".
    """
    data = json.loads(FLATPAK_MODULES.read_text(encoding="utf-8"))
    pins: dict[str, dict[str, str]] = {}
    for module in data["modules"]:
        found: dict[str, str] = {}
        for command in module.get("build-commands", []):
            for name, version in re.findall(r'"([A-Za-z0-9_.\-]+)==([^"]+)"', command):
                found[name.lower().replace("_", "-")] = version
        pins[module["name"]] = found
    return pins


def _version_satisfies(version: str, operator: str, wanted: str) -> bool:
    def parts(value: str) -> tuple[int, ...]:
        return tuple(int(p) for p in re.findall(r"\d+", value.split("+")[0]))

    have, want = parts(version), parts(wanted)
    size = max(len(have), len(want))
    have += (0,) * (size - len(have))
    want += (0,) * (size - len(want))
    if operator == "==":
        return version == wanted
    if operator == ">=":
        return have >= want
    if operator == ">":
        return have > want
    if operator == "<=":
        return have <= want
    if operator == "<":
        return have < want
    return True


def test_flatpak_modules_match_requirements_gui():
    requirements = _parse_requirements(REQUIREMENTS)
    flatpak = _flatpak_pins()
    problems: list[str] = []
    for name, (operator, version) in sorted(requirements.items()):
        if name in VERSION_EXEMPT:
            continue
        module = FLATPAK_MODULES_BY_PACKAGE.get(name)
        if module is None:
            problems.append(f"{name}: no Flatpak module mapped (add it to the map or the template)")
            continue
        pinned = (flatpak.get(module) or {}).get(name)
        if pinned is None:
            problems.append(f"{name}: module {module} states no ==version")
            continue
        if name in EDITABLE_ONLY:
            continue
        if not _version_satisfies(pinned, operator, version):
            problems.append(
                f"{name}: requirements-gui.txt wants {operator}{version}, "
                f"Flatpak module {module} builds {pinned}"
            )
    assert not problems, "build requirements drifted:\n  " + "\n  ".join(problems)


def test_flatpak_helper_listing_matches_the_module_tree():
    """`build/Flatpak-template/requirements.txt` is the human copy of the pins."""
    helper = _parse_requirements(FLATPAK_REQUIREMENTS)
    flatpak = _flatpak_pins()
    problems: list[str] = []
    for name, (operator, version) in sorted(helper.items()):
        module = FLATPAK_MODULES_BY_PACKAGE.get(name)
        if module is None or module not in flatpak:
            continue
        module_pins = flatpak.get(module) or {}
        built = module_pins.get(name)
        if operator == "==" and built is not None and built != version:
            problems.append(
                f"{name}: helper listing says {version}, module builds {built}"
            )
    assert not problems, "the Flatpak helper listing is stale:\n  " + "\n  ".join(problems)


def test_pip_targets_install_the_same_file():
    """Windows packaging and CI must install requirements-gui.txt, not a copy."""
    text = WINDOWS_BUILDER.read_text(encoding="utf-8")
    assert "requirements-gui.txt" in text, (
        "the Windows builder must install requirements-gui.txt (a separate list "
        "is a second source of truth)"
    )
    for workflow in (REPO_ROOT / ".github/workflows").glob("*.yml"):
        body = workflow.read_text(encoding="utf-8")
        if "pip install" not in body:
            continue
        assert "requirements-gui.txt" in body, (
            f"{workflow.name} installs something else than requirements-gui.txt"
        )


def test_aur_declares_every_runtime_dependency():
    """The AUR package takes distro versions but must name the same package set."""
    body = AUR_PKGBUILD.read_text(encoding="utf-8")
    # Strip comments first: the block carries a ``(vendored below)`` note that
    # would otherwise terminate the depends list.
    plain = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
    depends = plain.split("depends=(", 1)[1].split(")", 1)[0]
    requirements = _parse_requirements(REQUIREMENTS)
    missing = [
        aur
        for name, aur in sorted(AUR_PACKAGES.items())
        if name in requirements and aur not in depends
    ]
    assert not missing, f"AUR PKGBUILD does not depend on: {missing}"

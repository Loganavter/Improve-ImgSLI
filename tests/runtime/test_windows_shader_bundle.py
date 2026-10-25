"""Windows packaging must ship QRhi *.qsb next to tab Python packages."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


def _load_validator():
    path = Path(__file__).resolve().parents[2] / "build" / "ci" / "validate_windows_shaders.py"
    spec = importlib.util.spec_from_file_location("validate_windows_shaders", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_has_base_canvas_qsb() -> None:
    repo = Path(__file__).resolve().parents[2]
    mod = _load_validator()
    rels = {str(p).replace("\\", "/") for p in mod.expected_qsb_relpaths(repo)}
    assert "tabs/image_compare/canvas/shaders/base_array.vert.qsb" in rels
    assert "tabs/image_compare/canvas/shaders/base_array.frag.qsb" in rels


def test_missing_shaders_detects_absent_bundle(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    empty_bundle = tmp_path / "Improve_ImgSLI"
    empty_bundle.mkdir()
    mod = _load_validator()
    missing = mod.missing_shaders(repo_root=repo, bundle_root=empty_bundle)
    assert "tabs/image_compare/canvas/shaders/base_array.vert.qsb" in missing


# The spec collects *.qsb per source root because PyInstaller's resource
# collection does not walk directories that are not Python packages
# (`src/engine/gpu/shaders/` has no `__init__.py`). A root added to the tree
# without a matching `collect_tree(...)` line ships no shaders for its passes,
# and only the Windows bundle gate (`build/ci/validate_windows_shaders.py`)
# sees it — so the wiring is asserted here, not in a bundle-less unit test.
_SPEC_SRC_QSB_COLLECTION = re.compile(
    r'collect_tree\(\s*REPO_ROOT\s*/\s*"src"\s*/\s*"([^"]+)"\s*,\s*"([^"]+)"[^)]*?'
    r'include_suffixes=\{[^}]*"\.qsb"',
    re.DOTALL,
)


def _spec_path(repo: Path) -> Path:
    """PyInstaller spec path, from the packaging helper (never spelled here).

    The spec is named after the product name, so the name is imported from
    ``build/Windows-template/product_name.py`` (which reads
    ``src/core/log_names.py:APP_NAME``) instead of being repeated — otherwise a
    rename leaves this gate reading a file that no longer exists.
    """
    module_path = repo / "build" / "Windows-template" / "product_name.py"
    spec = importlib.util.spec_from_file_location("product_name", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return Path(module.SPEC_PATH)


def _spec_qsb_destinations(repo: Path) -> dict[str, str]:
    spec_text = _spec_path(repo).read_text(encoding="utf-8")
    return {src_root: dest for src_root, dest in _SPEC_SRC_QSB_COLLECTION.findall(spec_text)}


def test_windows_spec_collects_qsb_from_every_src_root() -> None:
    """Every `src/<root>` holding *.qsb must be collected into the bundle.

    Red-before (2026-10-24): `src/engine/gpu/shaders/` arrived after the spec
    learned to collect `src/tabs` + `src/ui`; the Windows bundle shipped 26 of
    33 shaders and failed `validate_windows_shaders.py`, leaving the glass
    panel, mip-cascade and slot-array passes without shaders at runtime.
    """
    repo = Path(__file__).resolve().parents[2]
    src = repo / "src"
    roots = {path.relative_to(src).parts[0] for path in src.rglob("*.qsb")}
    assert roots, "no *.qsb under src/ — the check would pass vacuously"

    destinations = _spec_qsb_destinations(repo)
    missing = sorted(roots - set(destinations))
    assert not missing, (
        f"{_spec_path(repo).name} collects no *.qsb for src root(s) {missing}; add "
        "collect_tree(REPO_ROOT / 'src' / '<root>', '<root>', include_suffixes={'.qsb'})"
    )
    misplaced = {root: destinations[root] for root in sorted(roots) if destinations[root] != root}
    assert not misplaced, (
        f"*.qsb must land at the module path of its source root, got {misplaced}"
    )

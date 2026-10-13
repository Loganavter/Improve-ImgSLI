"""B1: loadable-image admission policy (plan-cross-cutting-policy-2026-10-13).

One table-of-cases test on the owner (``shared.image_extensions``) plus the
``has_image_urls`` non-local gate. Entry points rely on the predicates; per
``CODE_PATTERNS.md`` ("one home for a cross-cutting policy") we pin the
rules here, not each call site's copy.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _url(*, local: bool, path: str):
    return SimpleNamespace(
        isLocalFile=lambda: local, toLocalFile=lambda: path
    )


def _mime(urls):
    return SimpleNamespace(
        hasUrls=lambda: bool(urls), urls=lambda: list(urls)
    )


def test_is_loadable_image_path_table(tmp_path: Path):
    """Accepted/rejected/dir/missing/symlink semantics of the predicate."""
    from shared.image_extensions import is_loadable_image_path

    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert is_loadable_image_path(img) is True
    # Case-insensitive suffix; str input (not just Path).
    upper = tmp_path / "b.JPG"
    upper.write_bytes(b"fake-jpeg")
    assert is_loadable_image_path(str(upper)) is True
    jxl = tmp_path / "c.jxl"
    jxl.write_bytes(b"fake-jxl")
    assert is_loadable_image_path(jxl) is True

    # Rejected suffix still rejected when the file exists.
    txt = tmp_path / "d.txt"
    txt.write_text("nope")
    assert is_loadable_image_path(txt) is False
    # No suffix at all.
    nosuffix = tmp_path / "README"
    nosuffix.write_text("nope")
    assert is_loadable_image_path(nosuffix) is False
    # Missing file with an accepted suffix.
    assert is_loadable_image_path(tmp_path / "ghost.png") is False
    # Directories never count — even when named like an image.
    assert is_loadable_image_path(tmp_path) is False
    img_dir = tmp_path / "e.png"
    img_dir.mkdir()
    assert is_loadable_image_path(img_dir) is False

    # Symlinks: resolving to a real file counts; broken ones do not.
    try:
        link = tmp_path / "link.png"
        link.symlink_to(img)
        assert is_loadable_image_path(link) is True
        broken = tmp_path / "broken.png"
        broken.symlink_to(tmp_path / "never-created.png")
        assert is_loadable_image_path(broken) is False
    except OSError:
        pytest.skip("symlinks unsupported on this filesystem")


def test_has_image_urls_rejects_non_local():
    """``has_image_urls`` gates on ``QUrl.isLocalFile()`` (B1 defect fix).

    Remote URLs must not pass even when the trailing path has an image
    suffix — loaders only read local files (``toLocalFile()`` is ``""``
    for remote URLs).
    """
    from shared.image_extensions import has_image_urls

    assert has_image_urls(_mime([])) is False
    assert has_image_urls(None) is False
    assert (
        has_image_urls(_mime([_url(local=True, path="/tmp/a.png")]))
        is True
    )
    # The fixed defect: remote image-looking URL alone → rejected.
    assert (
        has_image_urls(
            _mime([_url(local=False, path="http://host/a.png")])
        )
        is False
    )
    # Mixed: remote image + local text → still rejected.
    assert (
        has_image_urls(
            _mime(
                [
                    _url(local=False, path="http://host/a.png"),
                    _url(local=True, path="/tmp/b.txt"),
                ]
            )
        )
        is False
    )
    # Mixed: remote text + local image → accepted via the local file.
    assert (
        has_image_urls(
            _mime(
                [
                    _url(local=False, path="http://host/b.txt"),
                    _url(local=True, path="/tmp/a.png"),
                ]
            )
        )
        is True
    )
    # Empty local path (what Qt returns for unresolvable URLs) → rejected.
    assert has_image_urls(_mime([_url(local=True, path="")])) is False

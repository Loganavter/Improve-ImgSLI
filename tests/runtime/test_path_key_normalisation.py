"""One filesystem-path key per file: ``normpath`` + ``normcase`` everywhere.

Falsification story (pre-fix tree, where the key builders used
``os.path.normpath`` alone): with ``os.path.normcase`` simulated as the
folding a Windows / case-insensitive mount performs, the two spellings of one
file produced two keys — two decodes for one file, a crop/preview entry
written under one spelling invisible to the other — and produced a different
key from the ``fs_path_key`` builders the caches now use. Every assertion
marked ``pre-fix red`` fails on that tree; ``POSIX`` assertions are the
guard rails that the change did not start equating genuinely different files.

The simulation is a monkeypatched ``os.path.normcase`` (``str.lower``) rather
than a Windows host: POSIX ``normcase`` is the identity, so the failing
behaviour cannot be reproduced on this machine otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from shared.fs_paths import fs_path_key

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The four key builders that must funnel through the one helper.
_KEY_FILES = (
    "src/tabs/_shared/loading_pipeline.py",
    "src/tabs/image_compare/pipeline/cache.py",
    "src/tabs/multi_compare/pipeline/cache.py",
    "src/tabs/image_compare/state/reducers.py",
)


@pytest.fixture
def case_insensitive(monkeypatch):
    """Simulate a case-folding filesystem (Windows / APFS default / SMB)."""
    monkeypatch.setattr(os.path, "normcase", str.lower)
    return None


# --- the helper -------------------------------------------------------------


def test_folds_case_only_when_the_platform_does(case_insensitive):
    """One key under folding; two keys on a case-sensitive filesystem."""
    # POSIX (no fixture) semantics are asserted in the next test; here the
    # platform folds, so the two spellings are one file.
    assert fs_path_key("/a/x.png") == fs_path_key("/A/x.png")
    assert fs_path_key(r"C:\A\x.png") == fs_path_key(r"c:\a\x.png")


def test_case_sensitive_filesystem_keeps_files_distinct():
    """``normcase`` is the identity on POSIX — exact case is identity."""
    assert fs_path_key("/a/x.png") != fs_path_key("/A/x.png")


def test_heals_textual_variants_and_path_objects():
    assert fs_path_key("/a/./x.png") == fs_path_key("/a/x.png")
    assert fs_path_key("/a/b/../x.png") == fs_path_key("/a/x.png")
    assert fs_path_key(Path("/a/x.png")) == fs_path_key("/a/x.png") == "/a/x.png"
    assert fs_path_key(os.fsencode("/a/x.png")) == "/a/x.png"


def test_never_raises_on_a_non_path_value():
    """Key builders are hot-path: a bad value must be a key, not a crash."""
    weird = object()
    assert isinstance(fs_path_key(weird), str)
    assert fs_path_key(weird) == fs_path_key(weird)
    assert isinstance(fs_path_key(None), str)


# --- the key builders -------------------------------------------------------


def test_every_builder_uses_the_helper(monkeypatch):
    """(e) All four builders route through ``fs_path_key`` (call counter)."""
    from tabs._shared import loading_pipeline
    from tabs.image_compare.pipeline import cache as ic_cache
    from tabs.multi_compare.pipeline import cache as mc_cache

    calls: list[str] = []
    real = loading_pipeline.fs_path_key

    def _counted(path):
        calls.append(str(path))
        return real(path)

    monkeypatch.setattr(loading_pipeline, "fs_path_key", _counted)

    loading_pipeline.cache_key_for_path("/tmp/one.png")
    assert calls, "seam key builder bypassed fs_path_key"
    per_builder = len(calls)

    ic_cache._pixel_key("/tmp/one.png")
    assert len(calls) > per_builder, "_pixel_key bypassed fs_path_key"
    per_builder = len(calls)

    ic_cache._preview_key("/tmp/one.png")
    assert len(calls) > per_builder, "_preview_key bypassed fs_path_key"
    per_builder = len(calls)

    mc_cache.cache_key_for_path("/tmp/one.png")
    assert len(calls) > per_builder, "MC cache_key_for_path bypassed fs_path_key"


def test_key_builders_agree_on_one_spelling(case_insensitive):
    """(a) The IC tiers and the MC key fold to the SAME key, not two."""
    from tabs._shared.loading_pipeline import cache_key_for_path
    from tabs.image_compare.pipeline.cache import _pixel_key, _preview_key
    from tabs.multi_compare.pipeline.cache import (
        cache_key_for_path as mc_cache_key_for_path,
    )

    upper = r"C:\A\x.png"
    lower = r"c:\a\x.png"
    assert cache_key_for_path(upper) == cache_key_for_path(lower)
    assert _pixel_key(upper)[0] == _pixel_key(lower)[0]
    assert _preview_key(upper)[0] == _preview_key(lower)[0]
    assert mc_cache_key_for_path(upper) == mc_cache_key_for_path(lower)


def test_two_genuinely_different_files_stay_different(tmp_path):
    """(b) Distinct files never collapse — even at equal size."""
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.write_bytes(b"same-bytes")
    second.write_bytes(b"same-bytes")

    from tabs._shared.loading_pipeline import cache_key_for_path

    assert cache_key_for_path(first) != cache_key_for_path(second)
    assert fs_path_key(first) != fs_path_key(second)

    # A case-differing pair is two files on a case-sensitive filesystem.
    third = tmp_path / "A.png"
    third.write_bytes(b"same-bytes")
    assert cache_key_for_path(third) != cache_key_for_path(first)


def test_path_object_and_its_str_form_are_one_key(tmp_path):
    """(c) ``Path`` and ``str`` of the same file map to one key."""
    target = tmp_path / "pic.png"
    target.write_bytes(b"payload")

    from tabs._shared.loading_pipeline import cache_key_for_path
    from tabs.multi_compare.pipeline.cache import (
        cache_key_for_path as mc_cache_key_for_path,
    )

    assert cache_key_for_path(target) == cache_key_for_path(str(target))
    assert mc_cache_key_for_path(target) == mc_cache_key_for_path(str(target))


# --- migration: an old-format key is never silently reused ------------------


def test_old_format_key_is_not_reused_for_a_new_lookup(tmp_path, case_insensitive):
    """(d) A ``normpath``-only (pre-fix) key cannot answer a new lookup.

    The old key is built exactly as the pre-fix builders did it
    (``os.path.normpath`` only) for the *other* spelling of a real file, with
    the real file's mtime/size, so the only difference left is the spelling:
    the new lookup must miss, and a control write through the new builder must
    then hit from both spellings.
    """
    from tabs.image_compare.pipeline.cache import PipelineCache, _pixel_key

    target = tmp_path / "a.png"
    target.write_bytes(b"payload")
    other_spelling = str(tmp_path / "A.PNG")
    st = os.stat(target)

    old_key = (os.path.normpath(other_spelling), st.st_mtime_ns, st.st_size, False)
    new_key = _pixel_key(str(target), None, None)
    assert old_key != new_key, "old-format key must not equal the new key"

    cache = PipelineCache()
    sentinel = object()
    cache._pixel[old_key] = sentinel
    try:
        assert cache.get_pixel(other_spelling) is None
        assert cache.get_pixel(str(target)) is None
    finally:
        cache.clear()

    cache.put_pixel(str(target), None, sentinel)
    try:
        assert cache.get_pixel(str(target)) is sentinel
        assert cache.get_pixel(other_spelling) is sentinel
    finally:
        cache.clear()


# --- source-level guard -----------------------------------------------------


def test_no_key_file_keeps_a_normpath_only_key_builder():
    """A second implementation creeping back is the regression this guards."""
    for rel in _KEY_FILES:
        source = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "fs_path_key" in source, f"{rel} does not use the shared helper"
        assert "os.path.normpath(" not in source, (
            f"{rel} still builds a normpath-only key (bypasses fs_path_key)"
        )

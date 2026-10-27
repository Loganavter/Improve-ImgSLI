"""Content identity: the caches must recognise a file by its BYTES.

The defect (owner, 2026-10-27 ``content-identity``): every gallery cache keyed on
``sha256(path:mtime_ns)``, so (a) a file rewritten with its mtime preserved —
archive extraction, ``cp -p``, some editors — served the PREVIOUS bytes'
thumbnail / scorecard, and (b) the same picture under another name paid for the
analysis twice.

The contract asserted here, red before ``content_digest`` existed:

* the same path with the same ``mtime_ns`` but different bytes has a DIFFERENT
  digest — and therefore a different ``thumbnail_cache.cache_key_for`` (this is
  the exact case the old ``path:mtime`` key could not see; ``os.utime`` restores
  the mtime so the two writes are indistinguishable by stat alone);
* a byte-identical copy under another name has the SAME digest and the SAME
  thumbnail cache key (a copy is a HIT, not a second render / a second paid
  analysis);
* an unchanged file answers from the index and does NOT open the file again
  (spy on the module's ``open`` seam — a timing check would be a guess; the
  contract is "no read", so the test asserts exactly that);
* the index is on disk (a simulated fresh process still answers without a read)
  and bounded;
* an unreadable file answers ``""`` and logs it as such — never a fabricated
  digest that another unreadable file could share.

The index trusts ``(size, mtime_ns, ctime_ns)``. ``ctime`` is what makes the
first contract hold when the mtime is restored — the "same size, same mtime,
same ctime, different bytes" residue is documented in the module docstring as
the boundary no stat-based index can cross without reading every file.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path

import pytest

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.services import content_digest
from tabs.image_gallery.services.thumbnail_cache import cache_key_for

_PAYLOAD = b"\x89PNG\r\n\x1a\n" + base64.b64encode(b"frame-number-one")
#: Same LENGTH as ``_PAYLOAD``, so the cheap size filter cannot be what
#: distinguishes them — the digest has to do that work.
_OTHER_PAYLOAD = _PAYLOAD[:-1] + b"2"
_MTIME_NS = 1_700_000_000_000_000_000


@pytest.fixture(autouse=True)
def _isolated_index(tmp_path, monkeypatch):
    """One throwaway index per test: never the owner's real cache file."""
    import services.io.project_package as project_package

    monkeypatch.setattr(
        project_package,
        "cache_kind_dir",
        lambda kind: tmp_path / "cache-root" / kind,
        raising=True,
    )
    content_digest._reset_state(drop_disk=True)
    yield
    content_digest._reset_state(drop_disk=True)


def _write(path: Path, data: bytes, *, mtime_ns: int = _MTIME_NS) -> Path:
    path.write_bytes(data)
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


# ---------------------------------------------------------------------------
# the two owner-visible defects
# ---------------------------------------------------------------------------


def test_a_rewrite_that_restores_the_mtime_changes_the_digest(tmp_path) -> None:
    """Same path, same ``mtime_ns``, same SIZE, different bytes -> new digest.

    This is the unzip / ``cp -p`` case: the stat identity the old key used is
    identical across the two writes, so only the bytes can tell them apart.
    """
    path = _write(tmp_path / "frame.png", _PAYLOAD)
    first = content_digest.file_digest(path)
    stat_before = os.stat(path)

    _write(path, _OTHER_PAYLOAD)  # same length, mtime restored to the same value
    stat_after = os.stat(path)
    second = content_digest.file_digest(path)

    assert stat_after.st_size == stat_before.st_size
    assert stat_after.st_mtime_ns == stat_before.st_mtime_ns
    assert first != second, (
        "a rewrite with a restored mtime kept the old digest — the cache would "
        "serve the previous bytes' result"
    )


def test_the_thumbnail_key_follows_the_content_not_the_mtime(tmp_path) -> None:
    """The key the gallery actually uses must change on that rewrite.

    ``cache_key_for(path, mtime_ns)`` is the pre-content call shape: it is the
    one ``ai_cache`` / the thumbnail pipeline already make, so the fix must reach
    it without a new parameter at every call site.
    """
    path = _write(tmp_path / "frame.png", _PAYLOAD)
    key_before = cache_key_for(path, _MTIME_NS)

    _write(path, _OTHER_PAYLOAD)
    key_after = cache_key_for(path, _MTIME_NS)

    assert key_before != key_after, (
        "cache_key_for(path, mtime) is still blind to a content change — the "
        "gallery would serve the old thumbnail/scorecard"
    )


def test_a_copy_under_another_name_shares_the_digest_and_the_key(tmp_path) -> None:
    """Identical bytes + identical mtime under a new name -> one identity.

    Not merely "equal hashes": the assertion is that the second file is served
    the FIRST file's cache entry, which is what stops the duplicate paid read.
    """
    original = _write(tmp_path / "a.png", _PAYLOAD)
    copy = _write(tmp_path / "b.png", _PAYLOAD)  # a cp -p style copy

    assert content_digest.file_digest(original) == content_digest.file_digest(copy)
    assert cache_key_for(original, _MTIME_NS) == cache_key_for(copy, _MTIME_NS)


# ---------------------------------------------------------------------------
# the index: identity by content must not become "read every file, every open"
# ---------------------------------------------------------------------------


class _NoReadOpen:
    """``open`` replacement that fails the test if the file is read again."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, *args, **kwargs):  # pragma: no cover - should not run
        self.calls.append(str(args[0]) if args else "")
        raise AssertionError(f"the digest index re-read the file: {self.calls}")


def test_an_unchanged_file_is_answered_without_reading_it_again(tmp_path, monkeypatch) -> None:
    path = _write(tmp_path / "frame.png", _PAYLOAD)
    first = content_digest.file_digest(path)
    assert first

    spy = _NoReadOpen()
    monkeypatch.setattr(content_digest, "_open", spy)
    second = content_digest.file_digest(path)

    assert second == first
    assert spy.calls == [], "an unchanged file was read again"
    stats = content_digest.index_stats()
    assert stats["hits"] >= 1 and stats["misses"] == 1


def test_the_index_survives_a_restart_without_reading_the_file(tmp_path, monkeypatch) -> None:
    """The disk index is what keeps a 5000-image folder from being re-read."""
    path = _write(tmp_path / "frame.png", _PAYLOAD)
    expected = content_digest.file_digest(path)
    content_digest._persist(force=True)

    # A fresh process: in-memory state gone, the file on disk still there.
    content_digest._reset_state()
    assert content_digest.index_path().is_file()

    spy = _NoReadOpen()
    monkeypatch.setattr(content_digest, "_open", spy)
    assert content_digest.file_digest(path) == expected
    assert spy.calls == [], "the persisted index was not consulted"


def test_the_index_is_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(content_digest, "INDEX_LIMIT", 3)
    for index in range(6):
        _write(tmp_path / f"frame_{index}.png", _PAYLOAD + bytes([index]))
        content_digest.file_digest(tmp_path / f"frame_{index}.png")
    assert content_digest.index_stats()["entries"] <= 3


def test_forget_drops_the_entry(tmp_path) -> None:
    path = _write(tmp_path / "frame.png", _PAYLOAD)
    first = content_digest.file_digest(path)
    content_digest.forget(path)
    assert content_digest.index_stats()["entries"] == 0
    # Re-read (not re-used): a forgotten path is a miss, and the answer is the
    # same bytes' digest.
    assert content_digest.file_digest(path) == first
    assert content_digest.index_stats()["misses"] == 2


# ---------------------------------------------------------------------------
# failure behaviour + the declared vocabulary
# ---------------------------------------------------------------------------


def test_a_missing_file_answers_empty_and_raises_nothing(tmp_path) -> None:
    assert content_digest.file_digest(tmp_path / "gone.png") == ""
    assert content_digest.file_digest("") == ""


def test_an_unreadable_file_says_so_instead_of_inventing_a_digest(
    tmp_path, caplog
) -> None:
    """A directory stats fine but cannot be read: the answer is ``""`` + a line."""
    directory = tmp_path / "a-directory"
    directory.mkdir()

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        digest = content_digest.file_digest(directory)

    assert digest == ""
    assert "no content digest" in caplog.text


def test_a_content_change_logs_one_line_naming_the_file(tmp_path, caplog) -> None:
    path = _write(tmp_path / "frame.png", _PAYLOAD)
    content_digest.file_digest(path)
    _write(path, _OTHER_PAYLOAD)

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        content_digest.file_digest(path)

    lines = [
        record.getMessage()
        for record in caplog.records
        if "content changed" in record.getMessage()
    ]
    assert len(lines) == 1, caplog.text
    assert "frame.png" in lines[0]
    assert "entries dropped" in lines[0]


def test_the_digest_is_short_and_matches_hashlib(tmp_path) -> None:
    """Fixed vocabulary: blake2b truncated to ``DIGEST_HEX`` hex chars."""
    assert content_digest.DIGEST_HEX == 32
    data = b"known answer"
    expected = hashlib.blake2b(data).hexdigest()[: content_digest.DIGEST_HEX]
    assert content_digest.digest_of_bytes(data) == expected
    # The in-memory twin and the file reader can never drift apart: callers
    # compare one against the other.
    path = _write(tmp_path / "frame.bin", data)
    assert content_digest.file_digest(path) == expected


# ---------------------------------------------------------------------------
# every gallery cache, one identity
# ---------------------------------------------------------------------------


def test_a_content_change_reaches_every_gallery_cache_key(tmp_path) -> None:
    """The four keyed stores must agree on "what file is this".

    Each one is asked through its own public key function, in the call shape the
    production path uses, so a store that keeps a stale key is caught here
    instead of by a wrong thumbnail/scorecard/rank in the gallery.
    """
    from types import SimpleNamespace

    from tabs.image_gallery.services import jev_cache, vlm_cache

    def _item(path: Path) -> SimpleNamespace:
        return SimpleNamespace(path=path, mtime_ns=_MTIME_NS)

    first = _write(tmp_path / "frame.png", _PAYLOAD)
    other = _write(tmp_path / "other.png", b"\x89PNG\r\n\x1a\nother-frame")
    stale = {
        "thumbnail": cache_key_for(first, _MTIME_NS),
        "vlm": vlm_cache._brief_key(first, _MTIME_NS, other, _MTIME_NS),
        "jev": jev_cache.rank_cache_key([_item(first), _item(other)], {}),
    }

    _write(first, _OTHER_PAYLOAD)  # same path, same size, mtime restored
    fresh = {
        "thumbnail": cache_key_for(first, _MTIME_NS),
        "vlm": vlm_cache._brief_key(first, _MTIME_NS, other, _MTIME_NS),
        "jev": jev_cache.rank_cache_key([_item(first), _item(other)], {}),
    }

    assert all(stale[name] != fresh[name] for name in stale), (
        f"a store kept its key across a content change: {stale} vs {fresh}"
    )


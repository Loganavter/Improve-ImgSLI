"""Target bug: the project extract cache trusts an extracted member's *size*
only, so a same-length corruption is served forever.

Bug row: "Corrupted project extract-cache files are reused forever"
(``docs/bugs/README.md`` → ``docs/dev/KNOWN_BUGS.md`` review wave 2, W4).

Observed at the branch base (``c52ab867``): ``extract_media`` reuses an
existing member when ``target.stat().st_size == info.file_size``. A cached
member whose bytes were damaged in place (same length) therefore passes the
check on every later open, and the project keeps loading the corrupted bytes
instead of the archive member. The fix validates the member's content against
the ZIP entry's CRC32 before reusing it.
"""

from __future__ import annotations

import zlib
import zipfile
from pathlib import Path

import pytest

from core.evidence.journal import record_evidence, reset_journal, verdict
from services.io.project_package import extract_media

MEMBER = "media/asset-0001/photo.bin"
PAYLOAD = bytes(range(256)) * 16  # 4096 deterministic bytes


@pytest.fixture(autouse=True)
def _fresh_journal():
    reset_journal()
    yield
    reset_journal()


def _write_package(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MEMBER, PAYLOAD)


def _served_member(package: Path, cache: Path) -> bytes:
    mapping = extract_media(package, cache)
    return Path(mapping[MEMBER]).read_bytes()


def test_extract_cache_reuse_repro_and_fix(tmp_path: Path) -> None:
    package = tmp_path / "project.imgsli"
    cache = tmp_path / "cache"
    _write_package(package)

    # Sanity: first extraction must be faithful to the archive.
    assert _served_member(package, cache) == PAYLOAD

    # Poison the cache entry in place: same length, one flipped byte. This is
    # the corruption class the row names - the size-only reuse check cannot
    # see it, so every later open serves the damaged bytes.
    cached = Path(extract_media(package, cache)[MEMBER])
    corrupted = bytearray(cached.read_bytes())
    corrupted[len(corrupted) // 2] ^= 0xFF
    cached.write_bytes(bytes(corrupted))
    assert len(corrupted) == len(PAYLOAD)

    served = _served_member(package, cache)
    bug_present = served != PAYLOAD
    signal = (
        f"member={MEMBER} size={len(served)} "
        f"archive_crc={zlib.crc32(PAYLOAD):#010x} "
        f"served_crc={zlib.crc32(served):#010x} "
        f"mismatch_bytes={sum(a != b for a, b in zip(served, PAYLOAD))}"
    )
    ids = ("services/io/project_package.py::extract_media", f"zip_member:{MEMBER}")

    if bug_present:
        record_evidence(
            "bug.extract_cache_reuse",
            kind="target_bug",
            verdict="reproduced",
            signal=signal,
            reason="size-only reuse served a corrupted cache member instead of re-extracting it",
            ids=ids,
            area="services.io.project_package",
        )
        pytest.fail(f"reproduced: {signal}")

    record_evidence(
        "bug.extract_cache_reuse",
        kind="target_bug",
        verdict="fixed",
        signal=signal,
        reason="corrupted cache member was re-extracted; served bytes match the archive",
        ids=ids,
        area="services.io.project_package",
    )
    assert verdict(None, "bug.extract_cache_reuse").verdict == "fixed"

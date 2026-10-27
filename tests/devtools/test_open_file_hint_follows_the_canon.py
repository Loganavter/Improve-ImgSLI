"""``open_file``'s refusal must read the canon, not a fourth copy of it.

Found live on 2026-10-28 (leased instance, control socket): refusing a ``.pdf``
answered with "images: png, jpg, jpeg, bmp, tiff, tif, webp, jxl" — the canon had
already grown to 49 suffixes. The hint is the fourth place that spelled the
admission list by hand (canon, dialog filters, mime table, this string), so it is
pinned here against the canon itself, plus the group-C reason.
"""

from __future__ import annotations

from pathlib import Path

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS, REJECTED_SUFFIXES


def _hint(path: Path) -> str:
    from core.control.live_verbs import _unsupported_file_hint

    return _unsupported_file_hint(path)


def test_every_accepted_suffix_is_named_in_the_hint():
    hint = _hint(Path("probe.zzz"))
    for suffix in ACCEPTED_IMAGE_EXTENSIONS:
        assert suffix.lstrip(".") in hint, (
            f"{suffix} is accepted but the refusal hint does not name it — the "
            "hint has drifted from the canon again"
        )


def test_a_group_c_suffix_explains_itself():
    hint = _hint(Path("probe.pdf"))
    assert REJECTED_SUFFIXES[".pdf"] in hint, (
        "a refused group-C format must be answered with its recorded reason, "
        "not with a generic 'unsupported'"
    )
    assert ".pdf" in hint


def test_an_unknown_suffix_falls_back_to_the_canon_list():
    hint = _hint(Path("probe.not-an-image"))
    assert "accepted images:" in hint
    assert len(hint) > 40

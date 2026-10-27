"""Capability gate: every accepted suffix must be readable by a real decoder.

``shared.image_extensions.ACCEPTED_IMAGE_EXTENSIONS`` is a *claim* about the
installed decoders. It had already drifted once: ``.avif`` decoded fine
(Pillow and libvips both read it) while the static list -- which drives DnD,
file-dialog filters and the gallery folder scan -- still bounced the file, so
the same image opened when passed programmatically and was rejected by every
entry point. Adding a suffix by hand is therefore never enough: this gate
fails unless a decoder on *this* machine actually reads it.

Rule per suffix:

* **Pillow-backed** (the main path -- ``tiled_pixel_store``,
  ``pyramid_pixel_store`` and the preview loaders all decode through it): the
  suffix must appear in ``PIL.Image.registered_extensions()``.
* **Alternative backend**: a suffix Pillow has no plugin for (``.jxl``:
  decoded by libvips/``imagecodecs``) is allowed only through
  :data:`NON_PILLOW_ALLOWLIST`, which names the reason and whose claim is
  re-checked here (``pyvips.get_suffixes()``). The allowlist is
  **shrink-only**: a stale entry -- Pillow registers the suffix now, so the
  entry is no longer needed -- fails just as loudly as a missing one.
* Anything else fails. That is the "the list cannot drift again" property.

The final test feeds :func:`unsupported_suffixes` a suffix no backend has, so
a checker that accepted everything (or was never wired to the real set) would
be caught instead of passing by accident.
"""

from __future__ import annotations

import pytest

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS

#: suffix -> why Pillow cannot read it + which backend keeps it acceptable.
#: SHRINK-ONLY: delete an entry the moment Pillow registers the suffix. Never
#: add a suffix here to turn a red gate green -- that is exactly the drift
#: this gate exists to stop; an entry is only valid for a format another
#: decoder really reads on this machine, and the alternative backend is
#: re-probed below.
NON_PILLOW_ALLOWLIST: dict[str, str] = {
    ".jxl": (
        "No Pillow JXL plugin in any supported build; libvips (libjxl) or "
        "imagecodecs decodes it -- see JXL_SUPPORTED in "
        "shared/image_processing/progressive_loader.py."
    ),
}


def pillow_suffixes() -> frozenset[str]:
    """Suffixes this Pillow build can actually *open* (not merely register).

    ``Image.registered_extensions()`` is not the oracle: it lists the
    WRITE-ONLY ``.pdf`` (and ``.palm``) plugin, so a gate built on registration
    alone would bless a suffix that raises ``UnidentifiedImageError`` on open.
    The measured split (format-audit 2026-10-28): 70 registered extensions, 67
    with a reader in ``Image.OPEN``.
    """
    from PIL import Image

    Image.init()
    opening = set(getattr(Image, "OPEN", ()))
    readable: set[str] = set()
    for ext, fmt in Image.registered_extensions().items():
        if fmt in opening:
            readable.add(ext.lower())
    return frozenset(readable)


def vips_suffixes() -> frozenset[str]:
    """Lowercased suffixes the installed libvips build lists (empty if absent)."""
    try:
        import pyvips

        return frozenset(s.lower() for s in pyvips.get_suffixes())
    except Exception:
        return frozenset()


def unsupported_suffixes(suffixes) -> dict[str, str]:
    """Map each suffix no installed decoder can read to its failure reason.

    Pillow is the primary backend; an allowlisted suffix must additionally be
    listed by the alternative backend the entry points at. An empty mapping
    means every suffix is backed by a real decoder.
    """
    pillow = pillow_suffixes()
    vips = vips_suffixes()
    failures: dict[str, str] = {}
    for suffix in sorted(suffixes):
        if suffix in pillow:
            continue
        reason = NON_PILLOW_ALLOWLIST.get(suffix)
        if reason is None:
            failures[suffix] = (
                "not registered by Pillow and not in NON_PILLOW_ALLOWLIST"
            )
            continue
        if suffix not in vips:
            failures[suffix] = (
                "allowlisted, but the alternative backend (libvips) does not "
                "list this suffix either"
            )
    return failures


def test_every_accepted_suffix_has_a_decoder():
    """The list may only contain formats an installed decoder actually reads."""
    failures = unsupported_suffixes(ACCEPTED_IMAGE_EXTENSIONS)
    assert failures == {}, (
        "ACCEPTED_IMAGE_EXTENSIONS contains suffix(es) no installed decoder "
        f"reads: {failures}. Drop the suffix, or -- only for a format a "
        "non-Pillow backend really decodes here -- add a justified "
        "NON_PILLOW_ALLOWLIST entry. Do not add a decoder-less suffix to make "
        "DnD/dialogs quieter: the file would be admitted and then fail on load."
    )


def test_allowlist_entries_name_accepted_suffixes():
    """An allowlist entry for a non-accepted suffix is dead weight."""
    assert set(NON_PILLOW_ALLOWLIST) <= set(ACCEPTED_IMAGE_EXTENSIONS), (
        "NON_PILLOW_ALLOWLIST names suffixes that are not accepted: "
        f"{sorted(set(NON_PILLOW_ALLOWLIST) - set(ACCEPTED_IMAGE_EXTENSIONS))}"
    )


@pytest.mark.parametrize("suffix, reason", sorted(NON_PILLOW_ALLOWLIST.items()))
def test_allowlist_entries_are_justified_and_shrink_only(suffix: str, reason: str):
    """Each entry needs a real reason and must disappear once Pillow covers it."""
    assert suffix not in pillow_suffixes(), (
        f"stale NON_PILLOW_ALLOWLIST entry {suffix!r}: Pillow registers this "
        "suffix now, so the entry is no longer needed -- delete it (the list "
        "is shrink-only; a stale exemption is how a gate rots)."
    )
    assert len(reason.strip()) >= 30, (
        f"NON_PILLOW_ALLOWLIST[{suffix!r}] must name the backend that reads "
        "the format and why Pillow cannot; a bare 'needed' is a rubber stamp."
    )


def test_avifs_stays_excluded_until_animation_is_supported():
    """``.avifs`` (AVIF image sequence) is a product decision, not a gap.

    Pillow decodes ``.avifs``, so :func:`test_every_accepted_suffix_has_a_decoder`
    would happily allow it -- but every accepted suffix is also a promise that
    the *viewer* shows the file, and the viewer has no animation support. The
    exclusion is recorded here so a future list completion has to make the
    decision explicitly (and change this test) instead of drifting into
    "first frame or a half-loaded card" behavior.
    """
    assert ".avifs" not in ACCEPTED_IMAGE_EXTENSIONS


def test_gate_rejects_a_suffix_no_backend_has():
    """Falsification: the checker must fail on a decoder-less suffix.

    Without this, a gate that silently accepted everything would stay green
    forever. ``.png`` is included as the known-good control: it must pass, so
    the failure below is attributable to the bogus suffix alone.
    """
    bogus = ".definitely-not-an-image-format"
    assert bogus not in pillow_suffixes()
    assert bogus not in vips_suffixes()
    assert ".png" in pillow_suffixes()

    failures = unsupported_suffixes({".png", bogus})
    assert set(failures) == {bogus}, failures

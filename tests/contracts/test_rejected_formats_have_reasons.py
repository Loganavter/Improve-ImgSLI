"""Group C gate: every refused format carries a reason, and no overlap.

The canon in ``shared/image_extensions`` has two lists that must never grow
into each other: :data:`ACCEPTED_IMAGE_EXTENSIONS` (a claim about the installed
decoders, proven by ``test_accepted_formats_match_decoders.py``) and
:data:`REJECTED_SUFFIXES` (a product policy: formats a user will really try
that we refuse on purpose). A suffix in both would make the verdict depend on
which entry point asked -- the drift class this module family exists to stop.

A refusal also has to be *explainable*. "Could not load the image" for a PDF is
indistinguishable from a corrupt PNG, so each refused suffix names why: a page
needs rasterizing, a RAW needs demosaicing, HDF5 is not a frame, a video is not
a still. ``rejection_reason`` is the one accessor for that text (the toast that
renders it goes through i18n in a follow-up pass; the data is what is pinned
here).

The last test is a falsification: the accessor must say ``None`` for an
accepted suffix and for a suffix nobody listed, so a bug that returns "some
reason" for everything -- or a table accidentally keyed by accepted formats --
cannot pass by accident.
"""

from __future__ import annotations

import pytest

from shared.image_extensions import (
    ACCEPTED_IMAGE_EXTENSIONS,
    REJECTED_SUFFIXES,
    rejection_reason,
)

#: The audit's group C, spelled out: a future "complete the list" edit that
#: drops one of these from the refusal table must say so here too.
POLICY_REFUSALS = frozenset(
    {
        ".pdf",
        ".ps",
        ".eps",
        ".h5",
        ".hdf",
        ".fits",
        ".fit",
        ".grib",
        ".bufr",
        ".iim",
        ".wmf",
        ".emf",
        ".pcd",
        ".mpeg",
        ".mpg",
        ".palm",
        ".heic",
        ".heif",
        ".svg",
        ".exr",
        # Camera RAW family (the audit lists cr2/nef/arw/dng "...").
        ".cr2",
        ".cr3",
        ".nef",
        ".arw",
        ".dng",
        ".orf",
        ".raf",
        ".rw2",
        ".srw",
        ".pef",
    }
)


def test_refused_and_accepted_suffixes_never_overlap():
    """One suffix, one verdict -- whichever entry point asks."""
    overlap = sorted(set(REJECTED_SUFFIXES) & set(ACCEPTED_IMAGE_EXTENSIONS))
    assert overlap == [], (
        "these suffixes are both accepted and refused, so DnD, dialogs and the "
        f"folder scan would disagree: {overlap}"
    )


def test_every_refusal_names_a_reason():
    """A bare suffix in the refusal table is a silent "no" -- the defect."""
    assert REJECTED_SUFFIXES, "the refusal table is empty"
    empty = sorted(suffix for suffix, reason in REJECTED_SUFFIXES.items() if not reason.strip())
    assert empty == [], f"refused suffixes with no reason: {empty}"


def test_refusal_reasons_are_explanations_not_labels():
    """A reason has to say *what* the format is, not just "unsupported"."""
    too_short = {
        suffix: reason
        for suffix, reason in REJECTED_SUFFIXES.items()
        if len(reason.strip()) < 30
    }
    assert too_short == {}, (
        "these refusals are too terse to explain anything to a user: "
        f"{too_short}"
    )
    multiline = sorted(
        suffix for suffix, reason in REJECTED_SUFFIXES.items() if "\n" in reason
    )
    assert multiline == [], (
        "a refusal is rendered on one toast/hint line, so a multi-line reason "
        f"would be truncated: {multiline}"
    )


def test_policy_refusals_are_all_present():
    """Group C is the audit's list; shrinking it is a visible decision."""
    missing = sorted(POLICY_REFUSALS - set(REJECTED_SUFFIXES))
    assert missing == [], (
        "these group-C formats are neither accepted nor explained as refused, "
        f"so a user gets a generic load failure: {missing}"
    )


@pytest.mark.parametrize("suffix", sorted(REJECTED_SUFFIXES))
def test_rejection_reason_answers_for_every_refused_suffix(suffix):
    """The accessor is what a toast will call, so it must answer the table."""
    assert rejection_reason(f"sample{suffix}") == REJECTED_SUFFIXES[suffix]
    assert rejection_reason(f"sample{suffix.upper()}") == REJECTED_SUFFIXES[suffix]


@pytest.mark.parametrize("suffix", sorted(ACCEPTED_IMAGE_EXTENSIONS))
def test_rejection_reason_is_silent_for_accepted_suffixes(suffix):
    """An accepted file must never produce a refusal sentence."""
    assert rejection_reason(f"sample{suffix}") is None


def test_rejection_reason_is_silent_for_unknown_suffixes():
    """Falsification: "not in the canon" is not the same as "refused format".

    ``.txt`` is what the dialog's "All files" section still hands back; a
    refusal sentence about PDFs there would be worse than the generic error.
    """
    assert rejection_reason("notes.txt") is None
    assert rejection_reason("archive.zip") is None
    assert rejection_reason("snapshot.png") is None

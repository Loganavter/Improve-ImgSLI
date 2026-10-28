"""i18n hardcode cleanup (image_gallery): keys resolve per locale + no raw literals.

Falsification (pre-fix) — each assertion below fails on the parent commit:

* ``ui/clean_review.py`` handed ``"Moved N files to _rejected/"``, a
  ``ToastAction("Undo")`` and a ``"+N more / scrollable strip"`` tile (plus its
  tooltip) straight to the toast/Button/``setToolTip`` — English in every locale.
* ``use_cases/dialog.py`` built the QFileDialog filter and titles from the
  literals ``"Images ("``, ``"All files (*)"``, ``"Pick folder or image"`` and
  ``"Pick folder"``.
* ``controller.py`` raised a raw ``"Could not assemble the ask context."`` and
  the Ask AI badge appended a raw ``" · cached"``.
* ``ui/card/regions.py`` looked ``"gallery.card.unreadable"`` up in the WRONG
  namespace — ``gallery.card.*`` is the THEME-TOKEN namespace
  (``gallery.card.unreadable.plate``) — so the lookup always missed and the row
  silently fell back to English.
* ``ui/card/visuals.py`` emitted ``"defects: " + …`` (its ``verdict.upper()``
  pill was deleted later, plan-gallery-ai-judgement P4/D4);
  ``ui/card/factory.py`` + ``ui/list/card.py`` emitted ``f"VLM tie-break: {vlm_err}"``;
  ``ui/quick_look/metrics/rows.py`` emitted ``"— · not measured"`` /
  ``"#{rank} of {total}"`` / ``"rejected tail ≤ …"``; ``ui/quick_look/meta.py``
  emitted the whole ``local_brief_fallback`` English prose plus ``"AI brief…"``;
  ``ui/quick_look/artifacts.py`` appended the band note WITHOUT ``_ql_text``;
  ``ui/quick_look/insets.py`` named the role ``"source"`` in English.

Two layers, deliberately different evidence:

1. ``test_cleanup_keys_are_localized`` / ``..._placeholders_match_en`` assert on
   the RESOLVED STRING per locale (content identity, mirroring
   ``test_gallery_i18n_localization.py``): empty, raw-key, English-fallback or
   a dropped ``{n}`` all fail.
2. ``test_pre_fix_hardcodes_are_gone`` pins the pre-fix SOURCE FORMS out of the
   owned files, so the fix cannot silently regress to a literal. The banned
   fragments are the interpolated forms (``f"+{overflow} more"``) and the
   non-translated call shapes — the EN *defaults* of ``_tr`` calls
   (``"+{n} more"``) are deliberately not banned.

Plus behavioural tests that the translator seam actually drives the rendered
string (``analysis_tooltip_lines`` / ``local_brief_fallback`` / the artifact band
note / the unreadable card row) — pre-fix those helpers took no translator.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

NON_EN_LOCALES = ("ru", "zh", "pt_BR")

_TAB = Path(__file__).resolve().parents[1]

#: Keys this cleanup added — every locale must carry a real translation.
NEW_KEYS = (
    "image_gallery.clean_review.moved_toast",
    "image_gallery.clean_review.undo",
    "image_gallery.clean_review.more_tile",
    "image_gallery.clean_review.more_tile_sub",
    "image_gallery.clean_review.more_tooltip",
    "image_gallery.toolbar.filter_images",
    "image_gallery.toolbar.filter_all_files",
    "image_gallery.toolbar.pick_title",
    "image_gallery.toolbar.pick_folder",
    "image_gallery.ask_ai.error_context",
    "image_gallery.ask_ai.cached",
    "image_gallery.card.unreadable",
    "image_gallery.card.reset_metrics_cache",
    "image_gallery.card.tooltip.defects",
    "image_gallery.card.tooltip.vlm_tiebreak",
    "image_gallery.quick_look.ai_brief_pending",
    "image_gallery.quick_look.not_measured",
    "image_gallery.quick_look.rank_of",
    "image_gallery.quick_look.rejected_tail",
    "image_gallery.quick_look.source_fallback",
    "image_gallery.quick_look.brief_ssim_vs",
    "image_gallery.quick_look.brief_ssim",
    "image_gallery.quick_look.brief_detail_vs",
    "image_gallery.quick_look.brief_detail",
    "image_gallery.quick_look.brief_banding",
    "image_gallery.quick_look.brief_flagged",
    "image_gallery.quick_look.brief_vs",
    "image_gallery.quick_look.brief_vs_bare",
)

#: Keys whose value carries ``{...}`` placeholders — the NAME SET must match EN
#: (reordering is allowed); a dropped ``{n}`` would hide the count/rank.
PLACEHOLDER_KEYS = (
    "image_gallery.clean_review.moved_toast",
    "image_gallery.clean_review.more_tile",
    "image_gallery.clean_review.more_tooltip",
    "image_gallery.card.tooltip.defects",
    "image_gallery.card.tooltip.vlm_tiebreak",
    "image_gallery.quick_look.rank_of",
    "image_gallery.quick_look.rejected_tail",
    "image_gallery.quick_look.brief_ssim_vs",
    "image_gallery.quick_look.brief_ssim",
    "image_gallery.quick_look.brief_detail_vs",
    "image_gallery.quick_look.brief_detail",
    "image_gallery.quick_look.brief_banding",
    "image_gallery.quick_look.brief_flagged",
    "image_gallery.quick_look.brief_vs",
    "image_gallery.quick_look.brief_vs_bare",
)

#: relpath -> pre-fix source forms that must not survive. Interpolated f-strings
#: and un-translated call shapes only; EN ``_tr`` defaults are not listed.
_PRE_FIX_FORMS: dict[str, tuple[str, ...]] = {
    "ui/clean_review/__init__.py": (
        'f"Moved {len(moves)} files to _rejected/"',
        'actions=[ToastAction("Undo"',
    ),
    "ui/clean_review/populate.py": (
        'ButtonRow(text=f"+{overflow} more"',
        'ButtonRow(text="scrollable strip"',
        'f"{overflow} more rejected file(s)"',
    ),
    "use_cases/dialog.py": (
        'filt += ");;All files (*)"',
        'filt = "Images ("',
        'QFileDialog(base, "Pick folder or image"',
        'getExistingDirectory(base, "Pick folder"',
    ),
    "controller.py": (
        '_show_ask_ai_error("Could not assemble the ask context.")',
    ),
    "ui/ask_ai.py": (
        'badge += " · cached"',
    ),
    "ui/card/visuals.py": (
        'out.append("defects: " + ", ".join(kinds))',
    ),
    "ui/card/factory.py": (
        'parts.append(f"VLM tie-break: {vlm_err}")',
    ),
    "ui/list/card.py": (
        'parts.append(f"VLM tie-break: {vlm_err}")',
    ),
    "ui/quick_look/artifacts.py": (
        "_note = _fb(aid, score)",
    ),
    "ui/quick_look/metrics/rows.py": (
        '"— · not measured", 0.0, _muted_color()',
        'f"#{rank} of {len(overlay._series_items)}"',
        'f"rejected tail ≤ {min(tail):.2f}"',
    ),
    "ui/quick_look/meta.py": (
        'f"SSIM {ssim_a:.2f} vs {ssim_b:.2f}"',
        'f"detail {int(hf_a * 100):+d}% vs {int(hf_b * 100):+d}%"',
        'f"#{other_rank} shows banding"',
        'f"vs #{other_rank}: {head}"',
        'brief = "AI brief…"',
    ),
}


#: Values that are legitimately identical in every locale: an acronym/units
#: label that no locale spells differently. Kept explicit (not a blanket
#: exemption) so a genuinely untranslated key still fails the check below.
IDENTICAL_BY_DESIGN = {
    "image_gallery.quick_look.brief_ssim",  # "SSIM {a}" — SSIM is an acronym
}


def _register_all_i18n_roots() -> None:
    from resources.translations import add_i18n_root

    repo = Path(__file__).resolve().parents[4]
    roots = sorted((repo / "src").rglob("resources/i18n"))
    assert roots, "no i18n roots discovered under src/"
    for root in roots:
        add_i18n_root(root)


# -- 1. keys resolve per locale ----------------------------------------------


@pytest.mark.parametrize("language", NON_EN_LOCALES)
def test_cleanup_keys_are_localized(language: str) -> None:
    _register_all_i18n_roots()
    from resources.translations import tr

    problems: list[str] = []
    for key in NEW_KEYS:
        en_value = tr(key, language="en")
        assert en_value and en_value != key, f"{key}: missing from the en reference"
        value = tr(key, language=language)
        if not value or value == key:
            problems.append(f"{key} [{language}]: unresolved -> {value!r}")
        elif value == en_value and key not in IDENTICAL_BY_DESIGN:
            problems.append(f"{key} [{language}]: English fallback -> {value!r}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("language", ("en", *NON_EN_LOCALES))
def test_cleanup_key_placeholders_match_en(language: str) -> None:
    """Every ``{name}`` EN declares must survive in the locale value."""
    _register_all_i18n_roots()
    from resources.translations import tr

    problems: list[str] = []
    for key in PLACEHOLDER_KEYS:
        en_names = set(re.findall(r"\{(\w+)\}", tr(key, language="en")))
        names = set(re.findall(r"\{(\w+)\}", tr(key, language=language)))
        if names != en_names:
            problems.append(
                f"{key} [{language}]: placeholders {sorted(names)} != en {sorted(en_names)}"
            )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("language", ("en", *NON_EN_LOCALES))
def test_dialog_filter_labels_keep_ascii_parens(language: str) -> None:
    """Qt parses QFileDialog filter groups with ASCII ``(`` / ``)``.

    A localized value that swapped in full-width ``（）`` (zh) would be read as
    part of the group label and break the trailing group's boundary — the
    "All files" group would silently lose its ``*`` pattern.
    """
    _register_all_i18n_roots()
    from resources.translations import tr

    for key in (
        "image_gallery.toolbar.filter_images",
        "image_gallery.toolbar.filter_all_files",
    ):
        value = tr(key, language=language)
        assert "(" not in value or "（" not in value, (
            f"{key} [{language}]: mixed ASCII/full-width parens in a Qt filter label: {value!r}"
        )
        assert "（" not in value and "）" not in value, (
            f"{key} [{language}]: full-width parens break Qt filter parsing: {value!r}"
        )


# -- 2. the pre-fix source forms are gone -------------------------------------


@pytest.mark.parametrize("rel", sorted(_PRE_FIX_FORMS))
def test_pre_fix_hardcodes_are_gone(rel: str) -> None:
    src = (_TAB / rel).read_text(encoding="utf-8")
    survivors = [form for form in _PRE_FIX_FORMS[rel] if form in src]
    assert not survivors, (
        f"{rel}: hardcoded user-visible prose is back: {survivors} — "
        f"route it through the tab translator"
    )


def test_wrong_namespace_key_is_gone() -> None:
    """``gallery.card.unreadable`` collided with the theme-token namespace."""
    src = (_TAB / "ui/card/regions.py").read_text(encoding="utf-8")
    assert '"gallery.card.unreadable"' not in src
    assert '"image_gallery.card.unreadable"' in src


# -- 3. the translator seam drives the rendered string -----------------------


def test_analysis_tooltip_lines_follows_translator() -> None:
    """Defect wording is a function of the injected translator.

    Content identity: with a marker translator the lines must BE the marker
    output. Pre-fix ``analysis_tooltip_lines`` took no translator and always
    returned frozen English (``"defects: " + ...``). The ``KEEP``/``REJECT``
    pill that used to open the list was deleted (plan-gallery-ai-judgement
    P4/D4): the model's reason is now the plain first line.
    """
    from tabs.image_gallery.ui.card.visuals import analysis_tooltip_lines

    analysis = SimpleNamespace(
        reason="soft",
        defects=(
            SimpleNamespace(kind="over_smoothing"),
            SimpleNamespace(kind="chroma_fringing"),
        ),
    )
    assert analysis_tooltip_lines(analysis) == [
        "soft",
        "defects: over smoothing, chroma fringing",
    ]

    marked = analysis_tooltip_lines(analysis, lambda k, d: f"<{k.rsplit('.', 1)[-1]}>")
    assert marked == ["soft", "<defects>"]


def test_vlm_tiebreak_tooltip_line_follows_translator() -> None:
    from tabs.image_gallery.ui.card.visuals import vlm_tiebreak_tooltip_line

    assert vlm_tiebreak_tooltip_line(None, "boom") == "VLM tie-break: boom"
    assert (
        vlm_tiebreak_tooltip_line(lambda k, d: "Тай-брейк VLM: {err}", "boom")
        == "Тай-брейк VLM: boom"
    )


def test_card_unreadable_row_uses_gallery_namespace() -> None:
    """The unreadable card row resolves ``image_gallery.card.unreadable``."""
    from tabs.image_gallery.ui.card.regions import _text_rows

    item = SimpleNamespace(
        name="broken.png",
        rejected=False,
        thumbnail_status=SimpleNamespace(value="error"),
        analysis_error=None,
        analysis=None,
        mode=None,
    )
    seen: list[str] = []

    def _tr(key: str, default: str) -> str:
        seen.append(key)
        return "не читается"

    rows = _text_rows(item, _tr, mode=None)
    assert "image_gallery.card.unreadable" in seen, seen
    assert not [k for k in seen if k.startswith("gallery.card.")], seen
    assert rows[1].text == "не читается", [r.text for r in rows]


def test_local_brief_fallback_follows_translator() -> None:
    """Every prose fragment of the local brief goes through the overlay ``_tr``.

    Pre-fix ``local_brief_fallback(item, series_items)`` had no translator
    parameter at all — the whole ``"vs #N: SSIM … vs …"`` sentence was frozen
    English and the test below raised ``TypeError``.
    """
    from tabs.image_gallery.ui.quick_look.meta import local_brief_fallback

    viewing = SimpleNamespace(
        path="/tmp/brief/v.png", rank=1, metrics={"ssim": 0.95, "hf_ratio": 0.18}, artifacts={}
    )
    other = SimpleNamespace(
        path="/tmp/brief/o.png", rank=2, metrics={"ssim": 0.91, "hf_ratio": -0.31}, artifacts={}
    )
    assert local_brief_fallback(viewing, [viewing, other]).startswith("vs #2:")

    seen: list[str] = []

    def _tr(key: str, default: str) -> str:
        seen.append(key)
        return default

    local_brief_fallback(viewing, [viewing, other], SimpleNamespace(_tr=_tr))
    assert seen == [
        "image_gallery.quick_look.brief_ssim_vs",
        "image_gallery.quick_look.brief_detail_vs",
        "image_gallery.quick_look.brief_vs",
    ], seen


def test_artifact_band_note_reuses_metric_note_keys() -> None:
    """The artifact row note resolves ``metric_note.<aid>.<band>``, no new key."""
    from tabs.image_gallery.ui.quick_look.metrics import _metric_note

    seen: list[str] = []

    def _tr(key: str, default: str) -> str:
        seen.append(key)
        return "переходы"

    assert _metric_note(SimpleNamespace(_tr=_tr), "banding", 15) == "переходы"
    assert seen == ["image_gallery.metric_note.banding.bad"], seen


def test_ask_ai_cached_suffix_is_injected() -> None:
    """The status badge's cached suffix arrives via ``set_texts(cached=…)``."""
    import inspect

    from tabs.image_gallery.ui.ask_ai import AskAiFlyout

    assert "cached" in inspect.signature(AskAiFlyout.set_texts).parameters
    src = (_TAB / "ui/ask_ai.py").read_text(encoding="utf-8")
    assert "_cached_suffix" in src
    ctrl = (_TAB / "controller.py").read_text(encoding="utf-8")
    assert '"image_gallery.ask_ai.cached"' in ctrl


def test_dialog_pick_titles_follow_owner_translator() -> None:
    """``pick_folder_dialog`` resolves its titles through the owner widget."""
    from tabs.image_gallery.use_cases import dialog as dlg_mod

    seen: list[str] = []
    calls: list[tuple] = []

    class _FakeDialog:
        FileMode = SimpleNamespace(ExistingFiles="ef")

        def __init__(self, *args, **kwargs):
            calls.append(args)

        def setFileMode(self, mode) -> None:
            return None

        def exec(self) -> int:
            return 0

        @staticmethod
        def getExistingDirectory(base, title, start_dir):  # noqa: N802
            seen.append(("dir", title))
            return ""

    owner = SimpleNamespace(window=lambda: None, _tr_ui=lambda k, d: seen.append((k, d)) or "RU")

    orig = dlg_mod.QFileDialog
    dlg_mod.QFileDialog = _FakeDialog
    try:
        dlg_mod.pick_folder_dialog(owner, start_dir="")
    finally:
        dlg_mod.QFileDialog = orig

    assert calls and calls[0][1] == "RU", calls
    assert ("image_gallery.toolbar.pick_title", "Pick folder or image") in seen, seen
    assert ("image_gallery.toolbar.pick_folder", "Pick folder") in seen, seen
    filt = calls[0][3]
    assert ");;" in filt, filt
    assert filt.split(");;")[1] == "RU", filt

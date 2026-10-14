"""Quick Look SOURCE pill localization (i18n).

Falsification (pre-fix): the Quick Look source inset hardcoded the string
``"SOURCE"`` — both the pill label (``overlay_build.build_overlay_ui``) and
the populated caption (``insets.populate_source_inset``, ``f"SOURCE · …"``).
The grid card badge already localized through ``image_gallery.badge.source``
(``ui/card/visuals.py``); the Quick Look pill stayed English in every
non-EN locale. These assert the *visible* pill/caption resolves through the
overlay translator per locale (content identity, not "a method exists").
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.ui.quick_look import QuickLookOverlay

_KEEP_ALIVE: list[QWidget] = []


def _item(name: str, **kwargs) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, **kwargs)


def _owner(items, source) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            mode=Mode.FIDELITY,
            source_path=source,
            series=[list(items)],
            items=list(items),
        )
    )


def _open(qtbot, translate):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    source = _item("src.png")
    viewed = _item("view.png")
    overlay = QuickLookOverlay(parent, translate=translate)
    qtbot.addWidget(overlay)
    overlay.show_for(viewed, _owner([source, viewed], source.path))
    _KEEP_ALIVE.append(parent)
    return overlay, source


def _pill_text(overlay) -> str:
    """Full (un-elided) pill text — the Label elides the painted display."""
    lbl = overlay._source_inset_label
    try:
        return lbl.get_original_text()
    except Exception:
        return lbl.text()


def test_source_pill_uses_translator_key(qtbot) -> None:
    overlay, _src = _open(qtbot, lambda k, d: f"T[{k}]")
    text = _pill_text(overlay)
    assert text.startswith("T[image_gallery.badge.source]"), text


@pytest.mark.parametrize("language", ("ru", "zh", "pt_BR"))
def test_source_badge_localized_per_locale(qtbot, language: str) -> None:
    from resources.translations import add_i18n_root, tr

    repo = Path(__file__).resolve().parents[4]
    for root in sorted((repo / "src").rglob("resources/i18n")):
        add_i18n_root(root)

    localized = tr("image_gallery.badge.source", language=language)
    assert localized and localized != "image_gallery.badge.source", localized
    assert localized != "SOURCE", f"{language}: not actually localized ({localized!r})"

    overlay, _src = _open(qtbot, lambda k, d, _l=language: tr(k, language=_l))
    text = _pill_text(overlay)
    assert text.startswith(localized), f"{language}: {text!r} does not start with {localized!r}"
    assert not text.startswith("SOURCE"), f"{language}: raw English pill {text!r}"


def test_source_badge_fail_open_without_translator(qtbot) -> None:
    overlay, _src = _open(qtbot, None)
    # No translator wired -> raw EN default, never a crash / empty pill.
    assert _pill_text(overlay).startswith("SOURCE")


def test_filmstrip_source_pill_localized() -> None:
    """The filmstrip SOURCE pill (raw ``item.badge``) localizes too."""
    from types import SimpleNamespace

    from tabs.image_gallery.services.rank_badge import KIND_SOURCE
    from tabs.image_gallery.ui.quick_look.strip import _strip_rank_text_and_style

    item = SimpleNamespace(badge="SOURCE", badge_kind=KIND_SOURCE, rejected=False)
    overlay = SimpleNamespace(_tr=lambda k, d: f"T[{k}]")
    spec = _strip_rank_text_and_style(item, overlay)
    assert spec is not None and spec[0] == "T[image_gallery.badge.source]"
    # Rank pills (#N) are not keyed — untouched.
    rank = SimpleNamespace(badge="#3", badge_kind="rank", rejected=False)
    assert _strip_rank_text_and_style(rank, overlay)[0] == "#3"
    # Fail-open when no translator is wired.
    assert _strip_rank_text_and_style(item)[0] == "SOURCE"


def test_list_inline_source_badge_localized() -> None:
    """The list row's inline SOURCE badge localizes via the list translator."""
    from types import SimpleNamespace

    from tabs.image_gallery.services.rank_badge import KIND_SOURCE
    from tabs.image_gallery.ui.list.regions import _badges_text, _list_text_rows

    item = SimpleNamespace(
        badge="SOURCE",
        badge_kind=KIND_SOURCE,
        is_best=False,
        rejected=False,
        name="a.png",
    )
    tr = lambda k, d: f"T[{k}]"  # noqa: E731
    assert _badges_text(item, tr) == "T[image_gallery.badge.source]"
    assert _list_text_rows(item, tr)[0].text == "a.png T[image_gallery.badge.source]"
    # Fail-open to the raw stamped string without a translator.
    assert _badges_text(item) == "SOURCE"


@pytest.mark.parametrize("language", ("ru", "zh", "pt_BR"))
def test_filmstrip_and_list_source_badge_localized_per_locale(language: str) -> None:
    from types import SimpleNamespace

    from resources.translations import add_i18n_root, tr

    from tabs.image_gallery.services.rank_badge import KIND_SOURCE
    from tabs.image_gallery.ui.list.regions import _badges_text
    from tabs.image_gallery.ui.quick_look.strip import _strip_rank_text_and_style

    repo = Path(__file__).resolve().parents[4]
    for root in sorted((repo / "src").rglob("resources/i18n")):
        add_i18n_root(root)

    localized = tr("image_gallery.badge.source", language=language)
    item = SimpleNamespace(badge="SOURCE", badge_kind=KIND_SOURCE, rejected=False)
    tr_fn = lambda k, d, _l=language: tr(k, language=_l)  # noqa: E731
    assert _strip_rank_text_and_style(item, SimpleNamespace(_tr=tr_fn))[0] == localized
    assert _badges_text(item, tr_fn) == localized

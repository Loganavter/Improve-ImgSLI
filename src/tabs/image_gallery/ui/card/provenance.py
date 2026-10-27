"""Per-card provenance marker: who analyzed THIS card — the AI or the detectors.

Owner request 2026-10-22: in grid mode a small marker sits at the card's
bottom-left; list rows carry it on the thumbnail. The decision (ai/local/empty)
lives in ``analysis.read.analysis_source`` — the UI never reads raw metrics.

Both surfaces use ONE painter helper so the marker cannot drift between them.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainterPath

from sli_ui_toolkit.managers import scaled_px, ui_font

_MARK_PAD = 4.0
_MARK_FONT_PX = 10


def _colors() -> tuple[QColor, QColor]:
    from tabs.image_gallery.ui.card.dots import _accent_color, _token_color

    bg = QColor(_token_color("gallery.card.background", "#383838"))
    bg.setAlpha(210)
    return bg, QColor(_accent_color())


def accent_for(is_ai: bool) -> QColor:
    """The accent used for the AI token (kept here so both surfaces agree)."""
    _bg, accent = _colors()
    return accent


def _label_color() -> QColor:
    """Readable secondary text on the card (NOT the 120-alpha dot neutral).

    Owner 2026-10-22: the first marker used the muted dot colour and read as
    washed-out; the caption uses the same token as the stats strip text at full
    alpha, so it carries contrast in both themes.
    """
    from tabs.image_gallery.ui.card.dots import _token_color

    col = QColor(_token_color("gallery.stats.text", "#dfdfdf"))
    col.setAlpha(255)
    return col


def marker_text(item, translate=None, *, domain=None, requested: bool = False) -> str:
    """Localized short token naming who analyzed this card ("" when nobody did).

    Owner rule 2026-10-27 (verbatim: "пусто, пока карточка не знает, кто её
    анализировал или будет анализировать"):

    - ``AI`` — the ACTIVE domain is AI and either an ``AiAnalysisResult`` sits on
      the item or the card is queued / in flight for AI (``analysis_status ==
      PENDING``). A cached scorecard alone does NOT claim "AI" while the
      Algorithms domain is on screen (owner decision 2026-10-27: follow the
      domain, i.e. name the backend whose numbers are shown);
    - ``ALG`` — the LOCAL analysis was part of an EXPLICIT run for the active
      domain (``requested``), i.e. the user asked for it; a number the passive
      folder-open pass filled is not a claim about who analyzed the card;
    - otherwise empty. That is the defect this fixes: ``analysis_source`` says
      ``local`` as soon as ``item.metrics`` is non-empty, so the warm pass made
      every card say "АЛГ" without anyone asking.

    ``domain`` is the tab's ACTIVE judgment domain. ``requested`` is the
    controller's one explicit field (``_analysis_requested_gen``), never an
    inference from the item's state.
    """
    from tabs.image_gallery.analysis.read import SOURCE_AI, SOURCE_LOCAL

    source = _marker_source(item, domain=domain, requested=requested)
    if source == SOURCE_AI:
        return _token(translate, SOURCE_AI, "image_gallery.card.source_ai", "AI")
    if source == SOURCE_LOCAL:
        return _token(translate, SOURCE_LOCAL, "image_gallery.card.source_local", "ALG")
    return ""


def _marker_source(item, *, domain=None, requested: bool = False) -> str:
    """Who owns this card's claim: ``SOURCE_AI`` / ``SOURCE_LOCAL`` / ``""``."""
    from tabs.image_gallery.analysis.read import SOURCE_AI, SOURCE_LOCAL, analysis_source

    live = str(domain or "").strip().lower()
    # The marker names the backend whose numbers the card CURRENTLY shows
    # (owner decision 2026-10-27, asked and answered: "follow the domain").
    # A cached AI scorecard does not entitle the card to say "AI" while the
    # Algorithms domain is the one on screen — that is the 2026-10-22 rule and
    # it stays.
    ai_view = live != "algorithms"
    source = analysis_source(item)
    if ai_view and (source == SOURCE_AI or _ai_pending(item, live)):
        return SOURCE_AI
    if (
        requested
        and not ai_view
        and source == SOURCE_LOCAL
        and not _analyzing(item)
    ):
        # Only an EXPLICIT run of the active (Algorithms) domain earns "ALG".
        return SOURCE_LOCAL
    return ""


def _ai_pending(item, live: str) -> bool:
    """Is this card queued / in flight for the AI domain (the pill's truth)?"""
    if live == "algorithms":
        return False
    try:
        from tabs.image_gallery.models import AnalysisStatus

        status = getattr(item, "analysis_status", None)
        value = str(getattr(status, "value", status) or "").strip().lower()
        return value == AnalysisStatus.PENDING.value
    except Exception:
        return False


def requested_for(widget) -> bool:
    """Did the USER explicitly request analysis for this card's folder gen?

    The authority is the controller's single field ``_analysis_requested_gen``
    (owner 2026-10-27): it equals ``_folder_gen`` exactly when the user asked
    (Analyze / a domain switch) for the generation the cards show. The grid pool
    hands a card no controller, so the owner is reached through the explicit
    back-refs the grid already keeps (``_gallery_widget`` →
    ``_owner_for_triage``), never through an attribute scan on the paint path.
    """
    node = widget
    for _ in range(32):
        if node is None:
            return False
        resolver = getattr(node, "_owner_for_triage", None)
        if callable(resolver):
            return _explicit_run(resolver())
        grid = getattr(node, "_gallery_widget", None)
        if grid is not None:
            resolver = getattr(grid, "_owner_for_triage", None)
            if callable(resolver):
                return _explicit_run(resolver())
        node = getattr(node, "parent", None)
        node = node() if callable(node) else node
    return False


def _explicit_run(owner) -> bool:
    """``owner._analysis_requested_gen == owner._folder_gen`` (never raises)."""
    try:
        gen = int(getattr(owner, "_analysis_requested_gen", -1))
        return gen >= 0 and gen == int(getattr(owner, "_folder_gen", -2))
    except Exception:
        return False


def _analyzing(item) -> bool:
    """Is this item's analysis in flight right now (the pill's truth)?"""
    try:
        from tabs.image_gallery.ui.card.dots import _is_analyzing

        return bool(_is_analyzing(item))
    except Exception:
        return False


def _token(translate, _source: str, key: str, default: str) -> str:
    if callable(translate):
        try:
            return str(translate(key, default))
        except Exception:
            return default
    return default


def paint_source_marker(
    painter, box: QRectF, item, *, translate=None, domain=None, requested: bool = False
) -> None:
    """Draw the marker as plain text at *box*'s bottom-left (no pill, no image).

    Owner 2026-10-22: the first version was a pill INSIDE the cover — it covered
    the image while the strip under the filename was empty. The marker is now a
    small caption in the card's TEXT zone (grid) / text region (list): no
    background chip, no overlap with the preview.
    """
    source = _marker_source(item, domain=domain, requested=requested)
    if not source:
        return
    from tabs.image_gallery.analysis.read import SOURCE_AI, SOURCE_LOCAL

    text = (
        _token(translate, SOURCE_AI, "image_gallery.card.source_ai", "AI")
        if source == SOURCE_AI
        else _token(translate, SOURCE_LOCAL, "image_gallery.card.source_local", "ALG")
    )
    # Colour follows the claim the caption makes: the accent belongs to the AI
    # token, the local one keeps the muted stats-strip text colour.
    is_ai = source == SOURCE_AI
    font = ui_font(pixel_size=_MARK_FONT_PX, bold=True)
    metrics = QFontMetrics(font)
    pad = float(scaled_px(_MARK_PAD))
    height = float(max(metrics.height(), scaled_px(11)))
    width = float(metrics.horizontalAdvance(text) + 1.0)
    if width > box.width() or height > box.height():
        return
    # Clear the hover underline: the accent bar is 3 design px at 8 from the
    # bottom, and the caption used to sit exactly on it (owner 2026-10-22).
    try:
        bar_reserve = float(scaled_px(8.0)) + float(scaled_px(3.0)) + pad
    except Exception:
        bar_reserve = 12.0
    rect = QRectF(box.left() + pad, box.bottom() - height - bar_reserve, width, height)
    painter.save()
    try:
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setFont(font)
        painter.setPen(accent_for(is_ai) if is_ai else _label_color())
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text,
        )
    finally:
        painter.restore()

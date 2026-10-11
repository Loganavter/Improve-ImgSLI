"""Quick Look AI-block text: defect chips + AI axis-flag chips.

Split out of ``meta`` (file-size contract). Pure; no Qt. Renders the model's
defect kinds and its AI-sourced axis flags (``candidate``/``judgment``) as text
for the sidebar AI block — never as measured numbers
(see plan-gallery-two-domain-axes W4).
"""

from __future__ import annotations


def _normalize(text) -> str:
    try:
        from tabs.image_gallery.services.axis_policy import normalize_tag

        return normalize_tag(text)
    except Exception:
        return " ".join(str(text or "").strip().lower().replace("_", " ").replace("-", " ").split())


def defect_chips(defects) -> str:
    """Compact defect chips: ``kind (severity)`` joined by `` · ``.

    The free-text per-defect note is deliberately NOT shown — the model only
    repeated the measured metrics with it; the chip is the signal.
    """
    out = []
    try:
        for d in defects or ():
            kind = str(getattr(d, "kind", "") or "").replace("_", " ").strip()
            if not kind:
                continue
            sev = str(getattr(d, "severity", "") or "").strip()
            out.append(f"{kind} ({sev})" if sev else kind)
    except Exception:
        return ""
    return " · ".join(out)


def axis_flag_chips(flags, defects=()) -> str:
    """AI-sourced axis flags as one text line ('' when none render).

    ``candidate`` → ``possible <label> (AI, unverified)``; ``judgment`` →
    ``AI judgment: <label> (unverified)``. A candidate already shown as a
    defect chip is skipped so the block does not repeat itself; ``measured``
    is never rendered here (numbers are the detectors' job).
    """
    from tabs.image_gallery.models import MetricKind

    defect_terms = {_normalize(getattr(d, "kind", "")) for d in (defects or ())}
    out = []
    try:
        for f in flags or ():
            kind = str(getattr(f, "kind", "") or "").strip()
            label = str(
                getattr(f, "label", "") or getattr(f, "id", "") or ""
            ).replace("_", " ").strip()
            if not label:
                continue
            if kind == MetricKind.CANDIDATE.value:
                if {_normalize(label), _normalize(getattr(f, "id", ""))} & defect_terms:
                    continue  # already rendered as a defect chip
                out.append(f"possible {label} (AI, unverified)")
            elif kind == MetricKind.JUDGMENT.value:
                out.append(f"AI judgment: {label} (unverified)")
    except Exception:
        return ""
    return " · ".join(out)


__all__ = ["axis_flag_chips", "defect_chips"]

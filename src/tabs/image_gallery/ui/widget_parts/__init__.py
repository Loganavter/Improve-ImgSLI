"""Widget-side decomposition package for ``ui/widget.py`` (plan 2026-10-17).

Plain functions taking the owning ``ImageGalleryWidget`` as their first
argument (``def name(owner, ...)``) per ``CODE_PATTERNS.md`` — the owner keeps
the same-named thin delegators so call sites and tests do not move.
"""

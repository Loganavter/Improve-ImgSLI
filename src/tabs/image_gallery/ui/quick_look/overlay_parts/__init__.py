"""QuickLookOverlay method bodies — thin-owner split (plan Part C2).

Every body was moved verbatim out of ``ui/quick_look.py``'s
``QuickLookOverlay``; the shell file keeps same-named one-line delegators so
Qt virtuals, call sites and tests are untouched. The functions are plain
functions taking the overlay as their first argument (``CODE_PATTERNS.md``
"thin owner + ui/<area>_parts" — widget-owned logic lives under ``ui/``).

Modules:

- ``region_select``: LMB region marquee → Ask AI region scope.
- ``filters``: child-hover watch + ``eventFilter``.
- ``pinning``: resize re-pins (insets/nav/grip) + ``sizeHint``.
- ``input_events``: mouse/wheel/context/key handlers.
- ``lifecycle``: canvas release + close-cover + hide/close.
- ``theming``: veil ``paintEvent`` + ``retranslate`` + translator seam.
- ``show``: ``show_for`` + ``refresh_*`` + metric/artifact/strip rebuilds.
- ``populate``: ``_populate`` / series resolve / ``_walk``.
- ``dispatch``: triage button handlers (compare/multi/reject/delete/source).

No QSS here — the painter pipeline owns visuals. This is a NORMAL submodule
of the ``quick_look`` package; the file/package importlib shim lives in
``quick_look/__init__.py`` and is not involved.
"""

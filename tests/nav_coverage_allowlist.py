"""Written exemptions for the app-wide keyboard-coverage contract.

``tests/test_nav_coverage_contract.py`` audits real windows offscreen and
requires every *interactive* control (predicate in that module's docstring) to
be owned by a section of the toolkit ``NavigationManager``. This module is the
**only** escape hatch — the guard never re-reads production code to decide that
a control is "probably fine".

Key format
----------
``"<WindowClass>:<objectName or WidgetClass>" -> reason``
    One control (or one whole class of controls in that window). ``objectName``
    is tried first, then the widget class name. Use this for a control that is
    *deliberately* outside the section graph (a documented click-only
    affordance, a scroll viewport) or for a known gap that is waiting on a
    follow-up task.

``"window:<WindowClass>" -> reason``
    Whole-window exemption, honoured **only while that window registers no
    navigation section at all**. It exists for windows whose keyboard model is
    entirely absent (not for hiding a single orphan) and it ratchets: the
    moment a follow-up registers a section on the window, the entry stops
    being honoured and the freshness check in the contract fails, forcing the
    entry's removal.

Every entry needs a reason. The contract fails when an entry matches no
current orphan (stale) or when a reason is missing/blank, so this list can only
shrink relative to the real widget tree — never rot into a wall of dead keys.

Reasons must say *why the control is outside the keyboard model* — not "TODO"
and not a restatement of the key. If a control is genuinely unreachable, say so
here **and** report it in the task's ``DONE.md`` so a follow-up can be filed;
the allowlist is not the fix.
"""

from __future__ import annotations

#: Prefix that marks a whole-window exemption (see module docstring).
WINDOW_PREFIX = "window:"

#: ``key -> written reason``. Keep entries sorted by key.
NAV_COVERAGE_ALLOWLIST: dict[str, str] = {
    "QuickLookOverlay:quicklook_next": (
        "deliberately NoFocus click-only duplicate of the strip's keyboard "
        "cursor: the › circle (src/tabs/image_gallery/ui/quick_look/"
        "overlay_build/build.py:360) moves the same filmstrip cursor as "
        "Right-arrow, which QuickLookNavSection already owns. It is a pointer "
        "affordance, not a keyboard-reachable control."
    ),
    "QuickLookOverlay:quicklook_prev": (
        "deliberately NoFocus click-only duplicate of the strip's keyboard "
        "cursor: the ‹ circle (src/tabs/image_gallery/ui/quick_look/"
        "overlay_build/build.py:191) moves the same filmstrip cursor as "
        "Left-arrow, which QuickLookNavSection already owns. It is a pointer "
        "affordance, not a keyboard-reachable control."
    ),
    "QuickLookOverlay:quicklook_source_inset_pix": (
        "deliberately NoFocus informational caption thumbnail with no "
        "activation action (setFocusPolicy(NoFocus) at "
        "src/tabs/image_gallery/ui/quick_look/overlay_build/build.py:345); the "
        "SOURCE image itself is the preview, so the inset has no keyboard "
        "contract of its own."
    ),
    "UnifiedListPicker:OverlayScrollArea": (
        "the two list panels' scroll viewports inherit QAbstractScrollArea's "
        "StrongFocus but are containers, not controls: UnifiedListNavSection "
        "deliberately owns only live row cells "
        "(src/ui/widgets/unified_list_picker/nav.py:234) and scrolls the "
        "viewport itself while walking rows. New finding F1 — a focus stop "
        "outside the row model; a follow-up should pin NoFocus or teach the "
        "section to own the viewport."
    ),
}

__all__ = ["NAV_COVERAGE_ALLOWLIST", "WINDOW_PREFIX"]

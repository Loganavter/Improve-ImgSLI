"""Geometry constants for the Session Picker workspace page."""

# Main-window floor while this page is active (includes typical CSD chrome).
# Wide enough for page margins + two recent grid columns; tall enough for
# title, two create-cards, and a one-row recent shelf without clipping.
SESSION_PICKER_WINDOW_MIN_WIDTH = 720
SESSION_PICKER_WINDOW_MIN_HEIGHT = 560

# Softer floor for the page widget inside the workspace stack / scroll host.
SESSION_PICKER_PAGE_MIN_WIDTH = 560
SESSION_PICKER_PAGE_MIN_HEIGHT = 400

# Recent shelf content-width floor before the first layout pass (page min
# minus the page content margins 48+48). Last-resort safety net only — the
# real estimate before layout comes from the main window's already-known
# width (see SESSION_PICKER_PAGE_HORIZONTAL_MARGINS), so this floor should
# only ever bite if the window itself somehow has no width yet either.
SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR = SESSION_PICKER_PAGE_MIN_WIDTH - 96

# SessionPickerWidget's page-content QVBoxLayout margins (48 left + 48
# right, see widget.py._build()). Window -> page-content width is 1:1: no
# sidebar sits beside the workspace stack, and CSD only adds a top
# title-bar margin (no horizontal chrome) — see window_chrome.py.
SESSION_PICKER_PAGE_HORIZONTAL_MARGINS = 48 + 48

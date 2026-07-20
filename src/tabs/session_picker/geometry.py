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
# minus the page content margins 48+48). Avoids a 1-column → N-column jump
# when cards are built synchronously at construction time.
SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR = SESSION_PICKER_PAGE_MIN_WIDTH - 96

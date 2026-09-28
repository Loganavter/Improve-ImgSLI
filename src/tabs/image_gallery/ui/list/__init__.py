"""Gallery list-view card package — thin owner proxy.

List rows (``ui/list/*``) are fully independent from grid cards
(``ui/card/*``): own regions, visuals, painters. The only shared ground
is item-level ``models`` (``GalleryItem``, ``item_unreadable``) plus the
toolkit and triage use-cases. A change in ``ui/card/*`` can never leak
into list rows and vice versa.
"""

from __future__ import annotations

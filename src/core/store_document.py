"""Backward-compatibility shim for the image-pair document model.

The authoritative location for :class:`DocumentModel` and :class:`ImageItem`
is :mod:`tabs.image_compare.state.document` — the image-pair document model
is image_compare-owned state (step 8 of
``docs/dev/TAB_OWNERSHIP_AUDIT.md``).

Platform callers still import these types from ``core.store_document`` /
``core.store`` while the ~188 ``store.document.*`` access points are
gradually rewritten to reach the tab-owned session slot directly. New code
must import from :mod:`tabs.image_compare.state.document` instead.
"""

from __future__ import annotations

from tabs.image_compare.state.document import DocumentModel, ImageItem

__all__ = ["DocumentModel", "ImageItem"]

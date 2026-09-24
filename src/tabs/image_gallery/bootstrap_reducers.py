"""Reducer registration for image_gallery — imported once at plugin load."""

from core.state_management.slot_reducers import register_state_slot_reducer
from tabs.image_gallery.state.reducer import GallerySlotReducer

GALLERY_SLOT_NAME = "gallery"


def register_gallery_reducers() -> None:
    register_state_slot_reducer("gallery", GallerySlotReducer.reduce)

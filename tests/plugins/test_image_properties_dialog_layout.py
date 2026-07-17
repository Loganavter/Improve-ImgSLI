"""Image properties dialog first-show layout must stretch section frames."""

from __future__ import annotations

from plugins.image_properties.dialog import ImagePropertiesDialog
from plugins.image_properties.layout_geometry import (
    apply_image_properties_dialog_geometry,
)
from plugins.image_properties.service import (
    ImageProperties,
    ImagePropertyRow,
    ImagePropertySection,
)


def _sample_properties() -> ImageProperties:
    return ImageProperties(
        title="Properties",
        sections=tuple(
            ImagePropertySection(
                f"section_{index}",
                f"Section {index}",
                (
                    ImagePropertyRow(f"row_{index}", "Name", f"value_{index}.png"),
                    ImagePropertyRow(f"meta_{index}", "Size", "1920 x 1080 px"),
                ),
            )
            for index in range(3)
        ),
    )


def test_image_properties_sections_stretch_after_geometry_while_visible(qapp):
    """Deferred geometry used to call adjustSize on live frames and freeze
    them at sizeHint width; group headers then looked piled until resize.
    """
    dialog = ImagePropertiesDialog(
        _sample_properties(),
        parent=None,
        current_language="en",
    )
    dialog.show()
    qapp.processEvents()

    # Re-apply while visible — the old path broke stretch here.
    apply_image_properties_dialog_geometry(dialog)
    qapp.processEvents()

    content_width = dialog.properties_scroll_content.width()
    assert content_width > 0
    for frame in dialog.properties_section_frames:
        assert frame.width() >= content_width - 4

    geos = [frame.geometry() for frame in dialog.properties_section_frames]
    for index, geo in enumerate(geos):
        for other in geos[index + 1 :]:
            assert not geo.intersects(other)

    dialog.close()

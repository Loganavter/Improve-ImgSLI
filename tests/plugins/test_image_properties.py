from __future__ import annotations

import numpy as np
from PIL import Image

from plugins.image_properties.service import build_image_properties


def _rows_by_label_key(properties):
    return {
        row.label_key: row for section in properties.sections for row in section.rows
    }


def test_image_properties_reads_file_and_pil_dimensions(tmp_path):
    path = tmp_path / "sample.png"
    Image.new("RGBA", (320, 180), (10, 20, 30, 255)).save(path)

    properties = build_image_properties(
        path=path,
        display_name="sample",
        image=Image.new("RGBA", (320, 180)),
        app_rows=(("image_properties.slot", "Slot", 1),),
    )

    rows = _rows_by_label_key(properties)
    assert rows["image_properties.name"].value == "sample"
    assert "image_properties.folder" not in rows
    assert rows["image_properties.format"].value == "PNG"
    assert rows["image_properties.size"].value == "320 x 180 px"
    assert rows["image_properties.channels"].value == "4"
    assert rows["image_properties.orientation"].value_key == (
        "image_properties.orientation_landscape"
    )
    assert rows["image_properties.slot"].value == "1"


def test_image_properties_reads_numpy_shape_without_file():
    image = np.zeros((64, 128, 3), dtype=np.uint8)

    properties = build_image_properties(
        path=None,
        display_name="array",
        image=image,
    )

    rows = _rows_by_label_key(properties)
    assert rows["image_properties.size"].value == "128 x 64 px"
    assert rows["image_properties.channels"].value == "3"
    assert rows["image_properties.orientation"].value_key == (
        "image_properties.orientation_landscape"
    )

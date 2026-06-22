"""Progressive previews are valid live-canvas sources before full-res loading."""

from types import SimpleNamespace

from PIL import Image

from ui.canvas_presentation.plan_builder import build_live_store_presentation


def test_live_presentation_uses_progressive_previews_as_sources():
    preview1 = Image.new("RGBA", (20, 10), "red")
    preview2 = Image.new("RGBA", (20, 10), "blue")
    store = SimpleNamespace(
        document=SimpleNamespace(
            image1_path="left.png",
            image2_path="right.png",
            full_res_image1=None,
            full_res_image2=None,
            preview_image1=preview1,
            preview_image2=preview2,
            original_image1=None,
            original_image2=None,
        ),
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(
                    display_cache_image1=None,
                    display_cache_image2=None,
                    scaled_image1_for_display=None,
                    scaled_image2_for_display=None,
                ),
                image_state=SimpleNamespace(image1=preview1, image2=preview2),
            )
        ),
    )

    presentation = build_live_store_presentation(store)

    assert presentation.display_image1 is preview1
    assert presentation.display_image2 is preview2
    assert presentation.source_image1 is preview1
    assert presentation.source_image2 is preview2


def test_live_presentation_prefers_unified_pair_over_raw_full_res_sources():
    raw1 = Image.new("RGBA", (40, 20), "red")
    raw2 = Image.new("RGBA", (20, 40), "blue")
    unified1 = Image.new("RGBA", (40, 40), "red")
    unified2 = Image.new("RGBA", (40, 40), "blue")
    store = SimpleNamespace(
        document=SimpleNamespace(
            image1_path="left.png",
            image2_path="right.png",
            full_res_image1=raw1,
            full_res_image2=raw2,
            preview_image1=None,
            preview_image2=None,
            original_image1=raw1,
            original_image2=raw2,
        ),
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(
                    display_cache_image1=None,
                    display_cache_image2=None,
                    scaled_image1_for_display=None,
                    scaled_image2_for_display=None,
                ),
                image_state=SimpleNamespace(
                    image1=unified1,
                    image2=unified2,
                ),
            )
        ),
    )

    presentation = build_live_store_presentation(store)

    assert presentation.source_image1 is unified1
    assert presentation.source_image2 is unified2
    assert presentation.source_image1.size == presentation.source_image2.size

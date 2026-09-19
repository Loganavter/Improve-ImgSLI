"""Round-trip for the submit-vs-plan discriminator (phantom-hunt)."""

from tabs.image_compare.canvas.rhi_renderer.resources import (
    _ARRAY_INSTANCE_STRIDE,
    pack_array_instance,
    unpack_instance_layer2,
)


def _pack(layer1, layer2):
    return pack_array_instance(
        rect1=(0.0, 0.0, 0.5, 1.0),
        rect2=(0.5, 0.0, 0.5, 1.0),
        content_scale=(1.0, 1.0, 1.0, 1.0),
        content_scale_diff=(1.0, 1.0),
        layer1=layer1,
        layer2=layer2,
        layer_diff=0,
        bbox=(0.0, 0.0, 1.0, 1.0),
    )


def test_unpack_reads_back_packed_layer2():
    blob = b"".join(_pack(l1, l2) for l1, l2 in [(3, 7), (3, 5), (0, 4)])
    assert len(blob) == 3 * _ARRAY_INSTANCE_STRIDE
    assert [unpack_instance_layer2(blob, i) for i in range(3)] == [7, 5, 4]


def test_unpack_preserves_duplicates_verbatim():
    # A duplicated layer2 in the plan must read back duplicated (faithful
    # submit); the discriminator's job is comparing, not sanitizing.
    blob = b"".join(_pack(l1, l2) for l1, l2 in [(3, 3), (3, 3), (0, 0)])
    assert [unpack_instance_layer2(blob, i) for i in range(3)] == [3, 3, 0]

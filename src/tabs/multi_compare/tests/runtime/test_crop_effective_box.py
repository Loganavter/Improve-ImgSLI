"""Tests for multi_compare effective crop-box resolution (parametric crop)."""

from types import SimpleNamespace

from tabs.multi_compare.models import CompareSlot
from tabs.multi_compare.use_cases.crop import effective_crop_box


class _Box:
    def __init__(self, tup):
        self._tup = tup

    def to_tuple(self):
        return self._tup


class _Service:
    def __init__(self, box):
        self._box = box

    def get(self, path):
        return self._box


def _controller(*, service=None, setting=True):
    ctrl = SimpleNamespace(
        _crop_service=service,
        store=SimpleNamespace(
            settings=SimpleNamespace(auto_crop_black_borders=setting)
        ),
    )
    ctrl._get_crop_service = lambda: service if setting else None
    return ctrl


def test_override_false_is_full_frame():
    slot = CompareSlot(id=1, path='a.png', crop_override=False)
    ctrl = _controller(service=_Service(_Box((0, 0, 10, 10))))
    assert effective_crop_box(ctrl, slot) is None


def test_override_true_uses_service_box():
    slot = CompareSlot(id=1, path='a.png', crop_override=True)
    ctrl = _controller(service=_Service(_Box((2, 2, 20, 20))), setting=False)
    assert effective_crop_box(ctrl, slot) == (2, 2, 20, 20)


def test_override_true_no_box_is_full_frame():
    slot = CompareSlot(id=1, path='a.png', crop_override=True)
    ctrl = _controller(service=_Service(None))
    assert effective_crop_box(ctrl, slot) is None


def test_auto_follows_global_setting():
    slot = CompareSlot(id=1, path='a.png', crop_override=None)
    assert effective_crop_box(
        _controller(service=_Service(_Box((1, 1, 9, 9))), setting=True), slot
    ) == (1, 1, 9, 9)
    assert effective_crop_box(
        _controller(service=_Service(_Box((1, 1, 9, 9))), setting=False), slot
    ) is None


def test_failures_are_full_frame_never_raise():
    assert effective_crop_box(object(), object()) is None
    assert effective_crop_box(_controller(service=None), CompareSlot(id=1, path='a.png')) is None

    class _Boom:
        def get(self, path):
            raise RuntimeError("probe exploded")

    slot = CompareSlot(id=1, path='a.png', crop_override=True)
    assert effective_crop_box(_controller(service=_Boom()), slot) is None

"""Tests for engine.store.crop_window (parametric-crop box math)."""

import pytest

from engine.store.crop_window import crop_view_size, intersect_box


def test_none_crop_is_passthrough():
    assert intersect_box((0, 0, 100, 80), None) == (0, 0, 100, 80)
    assert crop_view_size((100, 80), None) == (100, 80)


def test_intersection_clamps_to_window():
    assert intersect_box((0, 0, 100, 80), (10, 5, 60, 40)) == (10, 5, 60, 40)
    assert intersect_box((50, 10, 200, 200), (10, 5, 60, 40)) == (50, 10, 60, 40)
    assert crop_view_size((100, 80), (10, 5, 60, 40)) == (50, 35)


def test_empty_intersection_is_gap_not_degenerate():
    assert intersect_box((0, 0, 10, 10), (50, 50, 60, 60)) is None
    assert intersect_box((0, 0, 10, 10), (5, 5, 5, 8)) is None  # zero width
    assert intersect_box((0, 0, 10, 10), (8, 8, 5, 5)) is None  # inverted


def test_malformed_input_fails_closed():
    assert intersect_box((0, 0, 10), (0, 0, 5, 5)) is None
    assert intersect_box((0, 0, 10, 10), "nope") is None
    assert intersect_box(None, None) is None
    assert crop_view_size(("x", "y"), None) == (0, 0)


def test_crop_clamped_to_frame():
    assert crop_view_size((100, 80), (-10, -5, 200, 200)) == (100, 80)
    assert intersect_box((0, 0, 100, 80), (-10, -5, 200, 200)) == (0, 0, 100, 80)

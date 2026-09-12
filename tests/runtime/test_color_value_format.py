"""Color value format cycle: HEX/RGB/HSL formatting, parsing, alpha rules."""

from __future__ import annotations

from PySide6.QtGui import QColor

from ui.widgets.color import (
    ValueFormat,
    color_value_has_alpha,
    format_color_value,
    next_color_format,
    parse_color_value,
)


def test_next_color_format_cycles_and_wraps():
    assert next_color_format(ValueFormat.HEX) is ValueFormat.RGB
    assert next_color_format(ValueFormat.RGB) is ValueFormat.HSL
    assert next_color_format(ValueFormat.HSL) is ValueFormat.HEX


def test_hex_format_matches_storage_convention():
    color = QColor(255, 136, 0, 170)
    assert format_color_value(color, ValueFormat.HEX, include_alpha=False) == "#FF8800"
    assert format_color_value(color, ValueFormat.HEX, include_alpha=True) == "#FF8800AA"
    assert format_color_value(QColor("#224466"), ValueFormat.HEX, include_alpha=True) == "#224466"


def test_rgb_format_opaque_and_translucent():
    assert (
        format_color_value(QColor(255, 136, 0), ValueFormat.RGB, include_alpha=False)
        == "rgb(255, 136, 0)"
    )
    assert (
        format_color_value(QColor(255, 136, 0, 170), ValueFormat.RGB, include_alpha=True)
        == "rgba(255, 136, 0, 170)"
    )
    # Opaque color never renders the alpha channel, even with include_alpha.
    assert (
        format_color_value(QColor(255, 136, 0, 255), ValueFormat.RGB, include_alpha=True)
        == "rgb(255, 136, 0)"
    )


def test_hsl_format_opaque_and_translucent():
    assert (
        format_color_value(QColor(255, 136, 0), ValueFormat.HSL, include_alpha=False)
        == "hsl(32, 100%, 50%)"
    )
    assert (
        format_color_value(QColor(255, 136, 0, 170), ValueFormat.HSL, include_alpha=True)
        == "hsla(32, 100%, 50%, 170)"
    )


def test_rgb_roundtrip_exact():
    for color in (
        QColor(255, 136, 0, 170),
        QColor(0, 0, 0),
        QColor(255, 255, 255, 1),
        QColor(34, 68, 102, 200),
    ):
        text = format_color_value(color, ValueFormat.RGB, include_alpha=True)
        parsed = parse_color_value(text, ValueFormat.RGB)
        assert parsed is not None
        assert (parsed.red(), parsed.green(), parsed.blue(), parsed.alpha()) == (
            color.red(),
            color.green(),
            color.blue(),
            color.alpha(),
        )


def test_hsl_roundtrip_within_one():
    # Percent-based HSL is lossy by nature — allow +/-1 per RGB channel,
    # alpha must round-trip exactly.
    for color in (
        QColor(255, 136, 0, 170),
        QColor(51, 102, 153),
        QColor(200, 40, 90, 64),
    ):
        text = format_color_value(color, ValueFormat.HSL, include_alpha=True)
        parsed = parse_color_value(text, ValueFormat.HSL)
        assert parsed is not None
        for got, want in zip(
            (parsed.red(), parsed.green(), parsed.blue()),
            (color.red(), color.green(), color.blue()),
        ):
            assert abs(got - want) <= 1, text
        assert parsed.alpha() == color.alpha()


def test_rgb_parse_accepts_css_alpha_forms():
    for token, expected_alpha in (("128", 128), ("0.5", 128), ("50%", 128), ("100%", 255)):
        color = parse_color_value(f"rgba(10, 20, 30, {token})", ValueFormat.RGB)
        assert color is not None
        assert color.alpha() == expected_alpha


def test_hsl_parse_accepts_css_alpha_forms():
    for token, expected_alpha in (("64", 64), ("0.25", 64), ("25%", 64)):
        color = parse_color_value(f"hsla(210, 50%, 40%, {token})", ValueFormat.HSL)
        assert color is not None
        assert color.alpha() == expected_alpha


def test_hsl_percent_optional_and_hue_normalized():
    color = parse_color_value("hsl(390, 50, 40)", ValueFormat.HSL)
    assert color is not None
    assert color.hue() == 30


def test_parse_invalid_returns_none():
    assert parse_color_value("zzz", ValueFormat.HEX) is None
    assert parse_color_value("rgb(300, 0, 0)", ValueFormat.RGB) is not None
    assert parse_color_value("rgb(1, 2)", ValueFormat.RGB) is None
    assert parse_color_value("hsl(1, 2)", ValueFormat.HSL) is None
    assert parse_color_value("#12345", ValueFormat.HEX) is None


def test_alpha_component_detection():
    assert color_value_has_alpha("#FF8800AA", ValueFormat.HEX)
    assert not color_value_has_alpha("#FF8800", ValueFormat.HEX)
    assert color_value_has_alpha("rgba(1, 2, 3, 4)", ValueFormat.RGB)
    assert not color_value_has_alpha("rgb(1, 2, 3)", ValueFormat.RGB)
    assert color_value_has_alpha("hsla(1, 2%, 3%, 4%)", ValueFormat.HSL)
    assert not color_value_has_alpha("hsl(1, 2%, 3%)", ValueFormat.HSL)

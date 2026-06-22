#pragma once

#include <QColor>
#include <QSize>
#include <QString>

#include <optional>

class QWidget;

namespace sli::toolkit {

// -----------------------------------------------------------------------
// StyleVariant — core type/style/density/shape descriptors.
// Mirrors the variant/tone/density/shape fields of Python's
// WidgetStyleTokens.
// -----------------------------------------------------------------------
struct StyleVariant {
    QString variant = QStringLiteral("default");
    QString tone = QStringLiteral("neutral");
    QString density = QStringLiteral("normal");
    QString shape = QStringLiteral("rounded");
};

// -----------------------------------------------------------------------
// StyleConfig — complete style token set for a widget.
// Mirrors Python's WidgetStyleTokens 1:1.
// -----------------------------------------------------------------------
struct StyleConfig {
    StyleVariant variant;
    std::optional<QColor> accentColor;
    std::optional<QColor> backgroundColor;
    std::optional<QColor> foregroundColor;   // also read from "textColor"
    std::optional<QColor> underlineColor;
    std::optional<int> iconSizePx;
    std::optional<int> cornerRadiusPx;
    std::optional<bool> showUnderline;
};

// -----------------------------------------------------------------------
// WidgetStyle — convenience wrapper around a read StyleConfig.
// -----------------------------------------------------------------------
struct WidgetStyle {
    StyleConfig config;
};

// -----------------------------------------------------------------------
// readWidgetStyle — read style-relevant dynamic properties off a widget.
// Mirrors Python read_widget_style().
// -----------------------------------------------------------------------
StyleConfig readWidgetStyle(QWidget* widget,
                            int defaultIconSize = 22,
                            int defaultCornerRadius = 6);

// -----------------------------------------------------------------------
// applyStyle — unpolish/polish the widget's style (optionally also
// updateGeometry).  Mirrors Python update_widget_style().
// -----------------------------------------------------------------------
void applyStyle(QWidget* widget, bool updateGeometry = false);

// -----------------------------------------------------------------------
// iconSizeQSize — construct a square QSize from an optional pixel size.
// Mirrors Python icon_size_qsize().
// -----------------------------------------------------------------------
QSize iconSizeQSize(std::optional<int> px, int fallback = 22);

// -----------------------------------------------------------------------
// Internal helpers exposed so callers can reuse conversion logic.
// -----------------------------------------------------------------------
namespace detail {

QString asStr(const QVariant& value, const QString& defaultVal);
std::optional<int> asInt(const QVariant& value, std::optional<int> defaultVal);
std::optional<bool> asBool(const QVariant& value, std::optional<bool> defaultVal);
std::optional<QColor> asColor(const QVariant& value);

}  // namespace detail

}  // namespace sli::toolkit

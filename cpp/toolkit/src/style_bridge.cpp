#include "sli/toolkit/style_bridge.h"

#include <QColor>
#include <QStyle>
#include <QVariant>
#include <QWidget>

namespace sli::toolkit {

// =======================================================================
// detail helpers
// =======================================================================
namespace detail {

QString asStr(const QVariant& value, const QString& defaultVal) {
    if (value.isNull() || !value.isValid())
        return defaultVal;
    QString text = value.toString().trimmed();
    return text.isEmpty() ? defaultVal : text;
}

std::optional<int> asInt(const QVariant& value, std::optional<int> defaultVal) {
    if (value.isNull() || !value.isValid())
        return defaultVal;
    bool ok = false;
    int result = value.toInt(&ok);
    return ok ? std::optional(result) : defaultVal;
}

std::optional<bool> asBool(const QVariant& value, std::optional<bool> defaultVal) {
    if (value.isNull() || !value.isValid())
        return defaultVal;
    if (value.typeId() == QMetaType::Bool)
        return value.toBool();
    if (value.typeId() == QMetaType::QString) {
        QString s = value.toString().trimmed().toLower();
        if (s == QLatin1String("1") || s == QLatin1String("true") ||
            s == QLatin1String("yes") || s == QLatin1String("on"))
            return true;
        if (s == QLatin1String("0") || s == QLatin1String("false") ||
            s == QLatin1String("no") || s == QLatin1String("off"))
            return false;
    }
    return value.toBool();
}

std::optional<QColor> asColor(const QVariant& value) {
    if (value.isNull() || !value.isValid())
        return std::nullopt;
    if (value.typeId() == QMetaType::QColor)
        return QColor(value.value<QColor>());
    QColor c(value.toString());
    return c.isValid() ? std::optional(c) : std::nullopt;
}

}  // namespace detail

// =======================================================================
// readWidgetStyle
// =======================================================================
StyleConfig readWidgetStyle(QWidget* widget, int defaultIconSize,
                             int defaultCornerRadius) {
    if (!widget)
        return {};

    StyleConfig cfg;

    cfg.variant.variant =
        detail::asStr(widget->property("variant"), QStringLiteral("default"));
    cfg.variant.tone =
        detail::asStr(widget->property("tone"), QStringLiteral("neutral"));
    cfg.variant.density =
        detail::asStr(widget->property("density"), QStringLiteral("normal"));
    cfg.variant.shape =
        detail::asStr(widget->property("shape"), QStringLiteral("rounded"));

    cfg.accentColor = detail::asColor(widget->property("accentColor"));
    cfg.backgroundColor = detail::asColor(widget->property("backgroundColor"));

    // foregroundColor read from "foregroundColor", falling back to "textColor"
    auto fg = detail::asColor(widget->property("foregroundColor"));
    if (!fg)
        fg = detail::asColor(widget->property("textColor"));
    cfg.foregroundColor = fg;

    cfg.underlineColor = detail::asColor(widget->property("underlineColor"));

    cfg.iconSizePx = detail::asInt(widget->property("iconSizePx"),
                                   std::optional(defaultIconSize));
    cfg.cornerRadiusPx = detail::asInt(widget->property("cornerRadiusPx"),
                                        std::optional(defaultCornerRadius));
    cfg.showUnderline = detail::asBool(widget->property("showUnderline"),
                                        std::nullopt);

    return cfg;
}

// =======================================================================
// applyStyle — mirrors Python update_widget_style()
// =======================================================================
void applyStyle(QWidget* widget, bool updateGeometry) {
    if (!widget)
        return;

    // Guard against re-entrancy, matching Python's _sli_style_refreshing flag
    static const char* kGuardProp = "_sli_style_refreshing";
    if (widget->property(kGuardProp).toBool()) {
        if (updateGeometry)
            widget->updateGeometry();
        widget->update();
        return;
    }

    widget->setProperty(kGuardProp, true);
    if (auto* style = widget->style()) {
        style->unpolish(widget);
        style->polish(widget);
    }
    if (updateGeometry)
        widget->updateGeometry();
    widget->update();
    widget->setProperty(kGuardProp, false);
}

// =======================================================================
// iconSizeQSize
// =======================================================================
QSize iconSizeQSize(std::optional<int> px, int fallback) {
    int size = std::max(1, px.value_or(fallback));
    return QSize(size, size);
}

}  // namespace sli::toolkit

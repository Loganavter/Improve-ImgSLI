#include "sli/toolkit/buttons/variants.h"

#include <QHash>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

namespace {

QColor scaleAlpha(const QColor& color, double factor) {
  QColor result(color);
  const int alpha = std::clamp(static_cast<int>(color.alpha() * factor), 0, 255);
  result.setAlpha(alpha);
  return result;
}

// Mirror of Python `default_resolve_bg(prefix)` — full token cascade.
BackgroundResolver tokenResolver(const QString& prefix) {
  return [prefix](StateSet states, const Theme& theme) -> QColor {
    if (states.testFlag(ButtonState::Disabled)) {
      if (auto c = theme.tryGetColor(prefix + QStringLiteral(".background.disabled"));
          c.has_value()) {
        return *c;
      }
      return theme.getColor(QStringLiteral("button.toggle.background.normal"));
    }
    if (states.testFlag(ButtonState::Pressed)) {
      return theme.getColor(prefix + QStringLiteral(".background.pressed"));
    }
    if (states.testFlag(ButtonState::Checked)) {
      const QString checkedKey = prefix + QStringLiteral(".background.checked");
      if (theme.tryGetColor(checkedKey).has_value()) {
        if (states.testFlag(ButtonState::Hovered)) {
          const QString hoverKey = checkedKey + QStringLiteral(".hover");
          if (theme.tryGetColor(hoverKey).has_value()) {
            return theme.getColor(hoverKey);
          }
        }
        return theme.getColor(checkedKey);
      }
      return theme.getColor(prefix + QStringLiteral(".background.pressed"));
    }
    if (states.testFlag(ButtonState::Hovered)) {
      return theme.getColor(prefix + QStringLiteral(".background.hover"));
    }
    const QString normalKey =
        prefix == QStringLiteral("button.toggle")
            ? prefix + QStringLiteral(".background.normal")
            : prefix + QStringLiteral(".background");
    return theme.getColor(normalKey);
  };
}

QColor ghostResolveBg(StateSet states, const Theme& theme) {
  if (states.testFlag(ButtonState::Pressed)) {
    return theme.getColor(QStringLiteral("button.toggle.background.pressed"));
  }
  if (states.testFlag(ButtonState::Hovered)) {
    return theme.getColor(QStringLiteral("button.toggle.background.hover"));
  }
  return QColor(0, 0, 0, 0);
}

QHash<QString, VariantSpec>& variantRegistry() {
  static QHash<QString, VariantSpec> instance = [] {
    QHash<QString, VariantSpec> map;
    map.insert(QStringLiteral("default"),
               VariantSpec{QStringLiteral("default"),
                           QStringLiteral("button.toggle"),
                           tokenResolver(QStringLiteral("button.toggle"))});
    map.insert(QStringLiteral("surface"),
               VariantSpec{QStringLiteral("surface"),
                           QStringLiteral("button.dialog.default"),
                           tokenResolver(QStringLiteral("button.dialog.default"))});
    map.insert(QStringLiteral("ghost"),
               VariantSpec{QStringLiteral("ghost"),
                           QStringLiteral("button.toggle"), ghostResolveBg});
    map.insert(QStringLiteral("subtle"),
               VariantSpec{QStringLiteral("subtle"),
                           QStringLiteral("button.toggle"), ghostResolveBg});
    return map;
  }();
  return instance;
}

}  // namespace

void registerVariant(VariantSpec spec) {
  variantRegistry().insert(spec.name, std::move(spec));
}

const VariantSpec& getVariant(const QString& name) {
  auto& registry = variantRegistry();
  const QString key = name.isEmpty() ? QStringLiteral("default") : name.toLower();
  auto it = registry.find(key);
  if (it != registry.end()) {
    return *it;
  }
  return *registry.find(QStringLiteral("default"));
}

QColor resolveBackground(const VariantSpec& spec, StateSet states,
                         const Theme& theme) {
  if (spec.resolveBg) {
    return spec.resolveBg(states, theme);
  }
  const QString prefix = spec.tokenPrefix.isEmpty()
                              ? QStringLiteral("button.toggle")
                              : spec.tokenPrefix;
  return tokenResolver(prefix)(states, theme);
}

QColor contrastingTextColor(const QColor& bg) {
  const double luminance =
      (0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()) / 255.0;
  return luminance > 0.5 ? QColor(QStringLiteral("#000000"))
                         : QColor(QStringLiteral("#FFFFFF"));
}

CustomPalette deriveCustomPalette(const QColor& base,
                                  const QString& variantName) {
  const QString name = variantName.isEmpty() ? QStringLiteral("default")
                                              : variantName.toLower();
  if (name == QStringLiteral("surface")) {
    return CustomPalette{
        scaleAlpha(base, 0.18), scaleAlpha(base, 0.30),
        scaleAlpha(base, 0.30), scaleAlpha(base, 0.40),
        scaleAlpha(base, 0.08),
    };
  }
  if (name == QStringLiteral("ghost")) {
    QColor transparent(base);
    transparent.setAlpha(0);
    return CustomPalette{transparent,
                         scaleAlpha(base, 0.20),
                         scaleAlpha(base, 0.30),
                         std::nullopt,
                         transparent};
  }
  return CustomPalette{
      scaleAlpha(base, 0.18), scaleAlpha(base, 0.30),
      scaleAlpha(base, 0.30), std::nullopt,
      scaleAlpha(base, 0.08),
  };
}

}  // namespace sli::toolkit::buttons

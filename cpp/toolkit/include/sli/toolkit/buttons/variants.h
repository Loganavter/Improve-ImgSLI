#pragma once

#include <QColor>
#include <QString>

#include <optional>

#include "sli/toolkit/buttons/state.h"
#include "sli/toolkit/buttons/variant_spec.h"

namespace sli::toolkit::buttons {

struct CustomPalette {
  QColor normal;
  QColor hover;
  QColor pressed;
  std::optional<QColor> border;
  QColor disabled;
};

void registerVariant(VariantSpec spec);
const VariantSpec& getVariant(const QString& name);
QColor resolveBackground(const VariantSpec& spec, StateSet states,
                         const Theme& theme);
QColor contrastingTextColor(const QColor& background);
CustomPalette deriveCustomPalette(const QColor& base,
                                  const QString& variantName = {});

}  // namespace sli::toolkit::buttons

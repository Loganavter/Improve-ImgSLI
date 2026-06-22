#pragma once

#include <QColor>
#include <QPainter>
#include <QPainterPath>
#include <QRectF>
#include <QString>
#include <QVariant>
#include <QWidget>

#include <memory>
#include <optional>

#include "sli/toolkit/buttons/state.h"
#include "sli/toolkit/buttons/variant_spec.h"

namespace sli::toolkit::buttons {

class Content;

struct DrawContext {
  QWidget* widget = nullptr;
  QPainter* painter = nullptr;
  QRectF rect;

  StateSet states;
  VariantSpec variant;
  int cornerRadius = 4;

  std::shared_ptr<const Content> content;

  std::optional<QColor> overrideBgColor;
  std::optional<QColor> customBgColor;
  std::optional<QColor> overrideBorderColor;

  std::optional<QString> badgeText;
  bool showUnderline = false;
  QVariant underlineColor;
  std::optional<double> underlineThickness;
  bool showStrikeThrough = false;
  bool isFooter = false;

  int iconSizePx = 22;
  std::optional<int> scrollValue;
  bool scrollValueAlwaysVisible = false;

  std::optional<QString> regionId;
  std::optional<QRectF> regionRect;
  std::optional<QPainterPath> regionPath;
  std::optional<StateSet> regionStates;
  std::shared_ptr<const Content> regionContent;
  std::optional<VariantSpec> regionVariant;
  std::optional<QColor> regionOverrideBgColor;
  std::optional<QColor> regionCustomBgColor;
  std::optional<QColor> regionOverrideBorderColor;
  std::optional<bool> regionShowUnderline;
  QVariant regionUnderlineColor;
  std::optional<double> regionUnderlineThickness;
  std::optional<int> regionIconSizePx;

  QRectF effectiveRect() const {
    return regionRect.value_or(rect);
  }

  QPainterPath effectivePath() const {
    if (regionPath.has_value()) {
      return *regionPath;
    }
    QPainterPath path;
    path.addRect(effectiveRect());
    return path;
  }

  StateSet effectiveStates() const {
    return regionStates.value_or(states);
  }

  std::shared_ptr<const Content> effectiveContent() const {
    return regionContent ? regionContent : content;
  }

  const VariantSpec& effectiveVariant() const {
    return regionVariant.has_value() ? *regionVariant : variant;
  }

  std::optional<QColor> effectiveOverrideBg() const {
    return regionOverrideBgColor.has_value() ? regionOverrideBgColor
                                             : overrideBgColor;
  }

  std::optional<QColor> effectiveCustomBg() const {
    return regionCustomBgColor.has_value() ? regionCustomBgColor
                                           : customBgColor;
  }

  std::optional<QColor> effectiveOverrideBorder() const {
    return regionOverrideBorderColor.has_value() ? regionOverrideBorderColor
                                                 : overrideBorderColor;
  }

  bool effectiveShowUnderline() const {
    return regionShowUnderline.value_or(showUnderline);
  }

  QVariant effectiveUnderlineColor() const {
    return regionUnderlineColor.isValid() ? regionUnderlineColor
                                          : underlineColor;
  }

  std::optional<double> effectiveUnderlineThickness() const {
    return regionUnderlineThickness.has_value() ? regionUnderlineThickness
                                                : underlineThickness;
  }

  int effectiveIconSizePx() const {
    return regionIconSizePx.value_or(iconSizePx);
  }

  struct ScopeArgs {
    QString regionId;
    QRectF rect;
    std::optional<QPainterPath> path;
    StateSet states;
    std::shared_ptr<const Content> content;
    std::optional<VariantSpec> variant;
    std::optional<QColor> overrideBgColor;
    std::optional<QColor> customBgColor;
    std::optional<QColor> overrideBorderColor;
    std::optional<bool> showUnderline;
    QVariant underlineColor;
    std::optional<double> underlineThickness;
    std::optional<int> iconSizePx;
  };

  DrawContext scopedTo(const ScopeArgs& args) const {
    DrawContext copy = *this;
    copy.regionId = args.regionId;
    copy.regionRect = args.rect;
    copy.regionPath = args.path;
    copy.regionStates = args.states;
    copy.regionContent = args.content;
    copy.regionVariant = args.variant;
    copy.regionOverrideBgColor = args.overrideBgColor;
    copy.regionCustomBgColor = args.customBgColor;
    copy.regionOverrideBorderColor = args.overrideBorderColor;
    copy.regionShowUnderline = args.showUnderline;
    copy.regionUnderlineColor = args.underlineColor;
    copy.regionUnderlineThickness = args.underlineThickness;
    copy.regionIconSizePx = args.iconSizePx;
    return copy;
  }
};

}  // namespace sli::toolkit::buttons

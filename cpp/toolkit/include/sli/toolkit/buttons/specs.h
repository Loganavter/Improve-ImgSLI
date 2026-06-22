#pragma once

#include <QColor>
#include <QCursor>
#include <QIcon>
#include <QSize>
#include <QString>
#include <QVariant>

#include <functional>
#include <memory>
#include <optional>
#include <utility>
#include <vector>

#include "sli/toolkit/buttons/content/button_row.h"
#include "sli/toolkit/buttons/regions.h"

namespace sli::toolkit::buttons {

using ActionCallback = std::function<void(const QString&, const QVariant&)>;

struct ShapeSpec {
  std::optional<int> cornerRadius;
  QSize size{36, 36};
  int iconSize = 22;

  QSize qsize() const { return size; }
};

struct ContentSpec {
  QVariant icon;
  QVariant iconChecked;
  QString text;
  std::vector<ButtonRow> rows;

  static ContentSpec fromRegion(const ButtonRegion& region);
};

struct RegionStyle {
  std::optional<QString> variant;
  std::optional<QColor> customBgColor;
  std::optional<QColor> overrideBgColor;
  std::optional<QColor> overrideBorderColor;
  std::optional<bool> showUnderline;
  QVariant underlineColor;
  std::optional<double> underlineThickness;
  std::optional<int> iconSizePx;
  bool showStrikeThrough = false;

  static RegionStyle fromRegion(const ButtonRegion& region);
};

enum class BehaviorKind {
  Click,
  Toggle,
  Scroll,
  LongPress,
  Menu,
};

struct BehaviorSpec {
  BehaviorKind kind = BehaviorKind::Click;
  std::optional<QString> action;
  QVariant data;
  ActionCallback callback;

  int scrollMin = 0;
  int scrollMax = 10;
  int longPressDelayMs = 600;
  std::vector<std::pair<QString, QVariant>> menuItems;
};

inline BehaviorSpec clickBehavior() {
  return BehaviorSpec{BehaviorKind::Click, {}, {}, {}, 0, 10, 600, {}};
}

inline BehaviorSpec toggleBehavior() {
  return BehaviorSpec{BehaviorKind::Toggle, {}, {}, {}, 0, 10, 600, {}};
}

inline BehaviorSpec scrollBehavior(int minValue, int maxValue) {
  return BehaviorSpec{
      BehaviorKind::Scroll, {}, {}, {}, minValue, maxValue, 600, {}};
}

inline BehaviorSpec longPressBehavior(int delayMs = 600) {
  return BehaviorSpec{BehaviorKind::LongPress, {}, {}, {}, 0, 10, delayMs, {}};
}

inline BehaviorSpec menuBehavior(
    std::vector<std::pair<QString, QVariant>> items) {
  return BehaviorSpec{
      BehaviorKind::Menu, {}, {}, {}, 0, 10, 600, std::move(items)};
}

struct RegionSpec {
  QString id;
  ContentSpec content;
  std::vector<BehaviorSpec> behaviors;
  RegionStyle style;
  double weight = 1.0;
  bool enabled = true;
  QVariant badge;
  std::optional<QCursor> cursor;
  RectFn rectFn;
  PathFn pathFn;
  int zIndex = 0;

  static RegionSpec fromRegion(const ButtonRegion& region);
  ButtonRegion toRegion() const;
};

struct ButtonSpecArgs {
  std::shared_ptr<SplitLayout> split;
  std::optional<Divider> divider;
  std::optional<ShapeSpec> shape;
  QString variant = QStringLiteral("default");
  QString density = QStringLiteral("normal");
  bool deferClick = false;
  bool wheelRequiresFocus = false;
};

struct ButtonSpec {
  std::vector<RegionSpec> regions;
  std::shared_ptr<SplitLayout> split;
  std::optional<Divider> divider;
  ShapeSpec shape;
  QString variant = QStringLiteral("default");
  QString density = QStringLiteral("normal");
  bool deferClick = false;
  bool wheelRequiresFocus = false;

  static ButtonSpec fromRegions(const std::vector<ButtonRegion>& regions,
                                const ButtonSpecArgs& args = {});
  std::vector<ButtonRegion> toRegions() const;
};

}  // namespace sli::toolkit::buttons

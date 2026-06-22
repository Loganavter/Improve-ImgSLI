#pragma once

#include <QColor>
#include <QCursor>
#include <QLineF>
#include <QPainterPath>
#include <QRectF>
#include <QString>
#include <QVariant>

#include <functional>
#include <optional>
#include <utility>
#include <vector>

#include "sli/toolkit/buttons/content/button_row.h"

namespace sli::toolkit::buttons {

using RectFn = std::function<QRectF(const QRectF&)>;
using PathFn = std::function<QPainterPath(const QRectF&)>;

struct ButtonRegion {
  QString id;
  double weight = 1.0;
  QVariant icon;
  // Alternate icon shown in checked state — mirrors Python `icon=(unchecked,
  // checked)` tuple form. Empty/null means use `icon` for both states.
  QVariant iconChecked;
  QString text;
  std::optional<std::vector<ButtonRow>> rows;
  bool toggle = false;
  bool longPress = false;
  int longPressMs = 600;
  std::optional<std::pair<int, int>> scrollable;
  std::optional<std::vector<std::pair<QString, QVariant>>> menu;
  QVariant badge;
  std::optional<QString> variant;
  std::optional<QColor> customBgColor;
  std::optional<QColor> overrideBgColor;
  std::optional<QColor> overrideBorderColor;
  std::optional<bool> showUnderline;
  QVariant underlineColor;
  std::optional<double> underlineThickness;
  std::optional<int> iconSizePx;
  bool showStrikeThrough = false;
  bool enabled = true;
  std::optional<QCursor> cursor;
  RectFn rectFn;
  PathFn pathFn;
  int zIndex = 0;
};

class SplitLayout {
 public:
  virtual ~SplitLayout() = default;
  virtual std::vector<QRectF> compute(
      const QRectF& rect, const std::vector<ButtonRegion>& regions) const = 0;
  virtual std::vector<QLineF> dividers(
      const std::vector<QRectF>& rects) const = 0;
};

class SingleRegionSplit final : public SplitLayout {
 public:
  std::vector<QRectF> compute(
      const QRectF& rect,
      const std::vector<ButtonRegion>& regions) const override;
  std::vector<QLineF> dividers(
      const std::vector<QRectF>& rects) const override;
};

class HorizontalSplit final : public SplitLayout {
 public:
  std::vector<QRectF> compute(
      const QRectF& rect,
      const std::vector<ButtonRegion>& regions) const override;
  std::vector<QLineF> dividers(
      const std::vector<QRectF>& rects) const override;
};

class VerticalSplit final : public SplitLayout {
 public:
  std::vector<QRectF> compute(
      const QRectF& rect,
      const std::vector<ButtonRegion>& regions) const override;
  std::vector<QLineF> dividers(
      const std::vector<QRectF>& rects) const override;
};

class GridSplit final : public SplitLayout {
 public:
  GridSplit(int rows, int cols) : rows_(rows < 1 ? 1 : rows),
                                  cols_(cols < 1 ? 1 : cols) {}
  std::vector<QRectF> compute(
      const QRectF& rect,
      const std::vector<ButtonRegion>& regions) const override;
  std::vector<QLineF> dividers(
      const std::vector<QRectF>& rects) const override;
  int rows() const { return rows_; }
  int cols() const { return cols_; }

 private:
  int rows_;
  int cols_;
};

class CustomSplit final : public SplitLayout {
 public:
  explicit CustomSplit(std::vector<RectFn> rectFns)
      : rectFns_(std::move(rectFns)) {}
  std::vector<QRectF> compute(
      const QRectF& rect,
      const std::vector<ButtonRegion>& regions) const override;
  std::vector<QLineF> dividers(
      const std::vector<QRectF>& rects) const override;

 private:
  std::vector<RectFn> rectFns_;
};

struct Divider {
  QString colorToken = QStringLiteral("separator.color");
  QString fallbackToken = QStringLiteral("dialog.border");
  double thickness = 1.0;
  double margin = 2.0;
};

}  // namespace sli::toolkit::buttons

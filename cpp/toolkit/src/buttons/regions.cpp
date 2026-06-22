#include "sli/toolkit/buttons/regions.h"

#include <algorithm>

namespace sli::toolkit::buttons {

namespace {

double totalWeight(const std::vector<ButtonRegion>& regions) {
  double total = 0.0;
  for (const auto& region : regions) {
    total += std::max(0.0, region.weight);
  }
  if (total <= 0.0) {
    total = static_cast<double>(regions.size());
  }
  if (total <= 0.0) {
    total = 1.0;
  }
  return total;
}

}  // namespace

std::vector<QRectF> SingleRegionSplit::compute(
    const QRectF& rect, const std::vector<ButtonRegion>& regions) const {
  std::vector<QRectF> out;
  out.reserve(regions.size());
  for (std::size_t i = 0; i < regions.size(); ++i) {
    out.emplace_back(rect);
  }
  return out;
}

std::vector<QLineF> SingleRegionSplit::dividers(
    const std::vector<QRectF>&) const {
  return {};
}

std::vector<QRectF> HorizontalSplit::compute(
    const QRectF& rect, const std::vector<ButtonRegion>& regions) const {
  const double total = totalWeight(regions);
  double x = rect.left();
  std::vector<QRectF> out;
  out.reserve(regions.size());
  for (std::size_t index = 0; index < regions.size(); ++index) {
    double w = 0.0;
    if (index + 1 == regions.size()) {
      w = rect.right() - x + 1.0;
    } else {
      w = rect.width() * (std::max(0.0, regions[index].weight) / total);
    }
    out.emplace_back(x, rect.top(), w, rect.height());
    x += w;
  }
  return out;
}

std::vector<QLineF> HorizontalSplit::dividers(
    const std::vector<QRectF>& rects) const {
  std::vector<QLineF> out;
  if (rects.size() < 2) {
    return out;
  }
  out.reserve(rects.size() - 1);
  for (std::size_t i = 0; i + 1 < rects.size(); ++i) {
    out.emplace_back(rects[i].right(), rects[i].top(), rects[i].right(),
                     rects[i].bottom());
  }
  return out;
}

std::vector<QRectF> VerticalSplit::compute(
    const QRectF& rect, const std::vector<ButtonRegion>& regions) const {
  const double total = totalWeight(regions);
  double y = rect.top();
  std::vector<QRectF> out;
  out.reserve(regions.size());
  for (std::size_t index = 0; index < regions.size(); ++index) {
    double h = 0.0;
    if (index + 1 == regions.size()) {
      h = rect.bottom() - y + 1.0;
    } else {
      h = rect.height() * (std::max(0.0, regions[index].weight) / total);
    }
    out.emplace_back(rect.left(), y, rect.width(), h);
    y += h;
  }
  return out;
}

std::vector<QLineF> VerticalSplit::dividers(
    const std::vector<QRectF>& rects) const {
  std::vector<QLineF> out;
  if (rects.size() < 2) {
    return out;
  }
  out.reserve(rects.size() - 1);
  for (std::size_t i = 0; i + 1 < rects.size(); ++i) {
    out.emplace_back(rects[i].left(), rects[i].bottom(), rects[i].right(),
                     rects[i].bottom());
  }
  return out;
}

std::vector<QRectF> GridSplit::compute(
    const QRectF& rect, const std::vector<ButtonRegion>& regions) const {
  const double cellW = rect.width() / cols_;
  const double cellH = rect.height() / rows_;
  std::vector<QRectF> out;
  out.reserve(regions.size());
  for (std::size_t index = 0; index < regions.size(); ++index) {
    const int row = static_cast<int>(index) / cols_;
    const int col = static_cast<int>(index) % cols_;
    if (row >= rows_) {
      break;
    }
    out.emplace_back(rect.left() + col * cellW, rect.top() + row * cellH, cellW,
                     cellH);
  }
  return out;
}

std::vector<QLineF> GridSplit::dividers(const std::vector<QRectF>&) const {
  return {};
}

std::vector<QRectF> CustomSplit::compute(
    const QRectF& rect, const std::vector<ButtonRegion>& regions) const {
  std::vector<QRectF> out;
  out.reserve(regions.size());
  for (std::size_t index = 0; index < regions.size(); ++index) {
    const auto& region = regions[index];
    RectFn fn = region.rectFn;
    if (!fn && index < rectFns_.size()) {
      fn = rectFns_[index];
    }
    out.emplace_back(fn ? fn(rect) : rect);
  }
  return out;
}

std::vector<QLineF> CustomSplit::dividers(const std::vector<QRectF>&) const {
  return {};
}

}  // namespace sli::toolkit::buttons

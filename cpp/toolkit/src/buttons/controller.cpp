#include "sli/toolkit/buttons/controller.h"

#include <QWidget>

#include "sli/toolkit/buttons/layers/ripple.h"

#include <algorithm>

namespace sli::toolkit::buttons {

namespace {

std::vector<std::size_t> orderByZIndex(
    const std::vector<ButtonRegion>& regions) {
  std::vector<std::size_t> indices(regions.size());
  for (std::size_t i = 0; i < regions.size(); ++i) {
    indices[i] = i;
  }
  std::stable_sort(indices.begin(), indices.end(),
                   [&regions](std::size_t a, std::size_t b) {
                     if (regions[a].zIndex != regions[b].zIndex) {
                       return regions[a].zIndex > regions[b].zIndex;
                     }
                     return a > b;
                   });
  return indices;
}

}  // namespace

ButtonController::ButtonController(QWidget* button) : button_(button) {}

ButtonController::ButtonController(QWidget* button, ButtonSpec spec)
    : button_(button) {
  setSpec(std::move(spec));
}

ButtonController::~ButtonController() = default;

void ButtonController::setSpec(ButtonSpec spec) {
  spec_ = std::move(spec);
  regions_ = spec_.toRegions();
  if (regions_.empty()) {
    ButtonRegion main;
    main.id = QStringLiteral("_main");
    regions_.push_back(std::move(main));
  }
  regionSpecs_.clear();
  for (const auto& region : spec_.regions) {
    regionSpecs_.insert(region.id, region);
  }
  split_ = spec_.split ? spec_.split : std::make_shared<SingleRegionSplit>();
  divider_ = spec_.divider;

  QHash<QString, bool> seen;
  for (const auto& region : regions_) {
    seen.insert(region.id, true);
    auto& runtime = runtime_[region.id];
    if (region.enabled) {
      runtime.states.setFlag(ButtonState::Disabled, false);
    } else {
      runtime.states.setFlag(ButtonState::Disabled, true);
    }
    // Each region owns its own RippleEffect — mirrors Python's
    // `_region_ripple[region.id] = RippleEffect(self)`. Lazy so a
    // re-setSpec on the same id keeps the existing effect (no animation
    // restart on spec churn). The button is the QObject parent so the
    // effect dies with the widget.
    if (!runtime.ripple && button_ != nullptr) {
      runtime.ripple = std::make_shared<RippleEffect>(button_);
    }

    if (auto scroll = scrollBehavior(region.id); scroll.has_value()) {
      const int minV = scroll->scrollMin;
      const int maxV = scroll->scrollMax;
      runtime.scrollRange = std::pair<int, int>{minV, maxV};
      if (!runtime.scrollValue.has_value()) {
        const int initial = std::max(minV, 1);
        runtime.scrollValue = std::max(minV, std::min(maxV, initial));
      } else {
        runtime.scrollValue =
            std::max(minV, std::min(maxV, *runtime.scrollValue));
      }
    } else {
      runtime.scrollRange.reset();
      runtime.scrollValue.reset();
    }
  }

  for (auto it = runtime_.begin(); it != runtime_.end();) {
    if (!seen.contains(it.key())) {
      it = runtime_.erase(it);
    } else {
      ++it;
    }
  }
  recomputeRects();
}

void ButtonController::setRegions(std::vector<ButtonRegion> regions,
                                  const ButtonSpecArgs& args) {
  setSpec(ButtonSpec::fromRegions(regions, args));
}

void ButtonController::recomputeRects() {
  if (button_ == nullptr || split_ == nullptr) {
    rects_.clear();
    paths_.clear();
    return;
  }
  const QRectF rect(button_->rect());
  const auto computed = split_->compute(rect, regions_);
  rects_.clear();
  for (std::size_t i = 0; i < regions_.size() && i < computed.size(); ++i) {
    const auto& region = regions_[i];
    QRectF regionRect = region.rectFn ? region.rectFn(rect) : computed[i];
    rects_.insert(region.id, regionRect);
  }
  paths_.clear();
  for (const auto& region : regions_) {
    auto rectIt = rects_.find(region.id);
    if (rectIt == rects_.end()) {
      continue;
    }
    QPainterPath path;
    if (region.pathFn) {
      path = region.pathFn(rect);
    } else {
      path.addRect(*rectIt);
    }
    paths_.insert(region.id, path);
  }
}

std::optional<QString> ButtonController::regionAt(const QPointF& pos) const {
  if (button_ == nullptr) {
    return std::nullopt;
  }
  const QRectF bounds(button_->rect());
  if (!bounds.contains(pos)) {
    return std::nullopt;
  }
  const auto ordered = orderByZIndex(regions_);
  for (auto idx : ordered) {
    const auto& region = regions_[idx];
    auto pathIt = paths_.find(region.id);
    if (pathIt == paths_.end() || !pathIt->contains(pos)) {
      continue;
    }
    auto runtimeIt = runtime_.find(region.id);
    if (runtimeIt != runtime_.end() &&
        runtimeIt->states.testFlag(ButtonState::Disabled)) {
      return std::nullopt;
    }
    return region.id;
  }
  return std::nullopt;
}

QRectF ButtonController::rectFor(const QString& regionId) const {
  auto it = rects_.find(regionId);
  return it != rects_.end() ? *it : QRectF{};
}

QPainterPath ButtonController::pathFor(const QString& regionId) const {
  auto it = paths_.find(regionId);
  return it != paths_.end() ? *it : QPainterPath{};
}

StateSet ButtonController::states(const QString& regionId) {
  return runtimeFor(regionId).states;
}

void ButtonController::setState(const std::optional<QString>& regionId,
                                ButtonState state, bool active) {
  if (!regionId.has_value()) {
    return;
  }
  auto& runtime = runtimeFor(*regionId);
  runtime.states.setFlag(state, active);
}

RippleEffect* ButtonController::ripple(const QString& regionId) {
  auto it = runtime_.find(regionId);
  return it != runtime_.end() ? it->ripple.get() : nullptr;
}

std::optional<std::pair<int, int>> ButtonController::scrollRange(
    const QString& regionId) const {
  auto it = runtime_.find(regionId);
  return it != runtime_.end() ? it->scrollRange : std::nullopt;
}

std::optional<int> ButtonController::scrollValue(
    const QString& regionId) const {
  auto it = runtime_.find(regionId);
  return it != runtime_.end() ? it->scrollValue : std::nullopt;
}

void ButtonController::setScrollValue(const QString& regionId, int value) {
  auto& runtime = runtimeFor(regionId);
  if (!runtime.scrollRange.has_value()) {
    runtime.scrollValue = value;
    return;
  }
  const auto [minV, maxV] = *runtime.scrollRange;
  runtime.scrollValue = std::max(minV, std::min(maxV, value));
}

std::vector<BehaviorSpec> ButtonController::behaviors(
    const QString& regionId, std::optional<BehaviorKind> kind) const {
  const auto* spec = regionSpec(regionId);
  if (spec == nullptr) {
    return {};
  }
  if (!kind.has_value()) {
    return spec->behaviors;
  }
  std::vector<BehaviorSpec> out;
  for (const auto& behavior : spec->behaviors) {
    if (behavior.kind == *kind) {
      out.push_back(behavior);
    }
  }
  return out;
}

RegionRuntimeState& ButtonController::runtimeFor(const QString& regionId) {
  return runtime_[regionId];
}

const RegionSpec* ButtonController::regionSpec(const QString& regionId) const {
  auto it = regionSpecs_.find(regionId);
  return it != regionSpecs_.end() ? &it.value() : nullptr;
}

std::optional<BehaviorSpec> ButtonController::scrollBehavior(
    const QString& regionId) const {
  const auto* spec = regionSpec(regionId);
  if (spec == nullptr) {
    return std::nullopt;
  }
  for (const auto& behavior : spec->behaviors) {
    if (behavior.kind == BehaviorKind::Scroll) {
      return behavior;
    }
  }
  return std::nullopt;
}

}  // namespace sli::toolkit::buttons

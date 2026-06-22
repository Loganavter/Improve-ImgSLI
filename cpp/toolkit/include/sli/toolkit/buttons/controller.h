#pragma once

#include <QHash>
#include <QPainterPath>
#include <QPointF>
#include <QRectF>
#include <QString>

#include <memory>
#include <optional>
#include <utility>
#include <vector>

#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/buttons/specs.h"
#include "sli/toolkit/buttons/state.h"

class QWidget;

namespace sli::toolkit::buttons {

class RippleEffect;

struct RegionRuntimeState {
  StateSet states;
  std::shared_ptr<RippleEffect> ripple;
  std::optional<std::pair<int, int>> scrollRange;
  std::optional<int> scrollValue;
};

class ButtonController {
 public:
  explicit ButtonController(QWidget* button);
  ButtonController(QWidget* button, ButtonSpec spec);
  ~ButtonController();

  ButtonController(const ButtonController&) = delete;
  ButtonController& operator=(const ButtonController&) = delete;

  void setSpec(ButtonSpec spec);
  void setRegions(std::vector<ButtonRegion> regions,
                  const ButtonSpecArgs& args = {});

  const ButtonSpec& spec() const { return spec_; }
  const std::vector<ButtonRegion>& regions() const { return regions_; }
  const SplitLayout* split() const { return split_.get(); }
  const std::optional<Divider>& divider() const { return divider_; }

  void recomputeRects();
  std::optional<QString> regionAt(const QPointF& pos) const;
  QRectF rectFor(const QString& regionId) const;
  QPainterPath pathFor(const QString& regionId) const;

  StateSet states(const QString& regionId);
  void setState(const std::optional<QString>& regionId, ButtonState state,
                bool active);

  RippleEffect* ripple(const QString& regionId);
  std::optional<std::pair<int, int>> scrollRange(const QString& regionId) const;
  std::optional<int> scrollValue(const QString& regionId) const;
  void setScrollValue(const QString& regionId, int value);

  std::vector<BehaviorSpec> behaviors(
      const QString& regionId,
      std::optional<BehaviorKind> kind = std::nullopt) const;

  const QHash<QString, RegionRuntimeState>& runtime() const { return runtime_; }

 private:
  RegionRuntimeState& runtimeFor(const QString& regionId);
  const RegionSpec* regionSpec(const QString& regionId) const;
  std::optional<BehaviorSpec> scrollBehavior(const QString& regionId) const;

  QWidget* button_ = nullptr;
  ButtonSpec spec_;
  std::vector<ButtonRegion> regions_;
  QHash<QString, RegionSpec> regionSpecs_;
  std::shared_ptr<SplitLayout> split_;
  std::optional<Divider> divider_;
  QHash<QString, QRectF> rects_;
  QHash<QString, QPainterPath> paths_;
  QHash<QString, RegionRuntimeState> runtime_;
};

}  // namespace sli::toolkit::buttons

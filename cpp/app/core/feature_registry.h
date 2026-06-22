#pragma once

#include <QStringList>

#include <memory>
#include <vector>

#include "imgsli/contracts/canvas_widget_feature.h"

namespace imgsli::app {

class FeatureRegistry final {
public:
  static FeatureRegistry &instance();

  void add(std::unique_ptr<CanvasWidgetFeature> feature);
  [[nodiscard]] const std::vector<std::unique_ptr<CanvasWidgetFeature>> &
  features() const;
  [[nodiscard]] QStringList names() const;

private:
  std::vector<std::unique_ptr<CanvasWidgetFeature>> features_;
};

template <typename Feature> class StaticFeatureRegistration final {
public:
  StaticFeatureRegistration() {
    FeatureRegistry::instance().add(std::make_unique<Feature>());
  }
};

#define IMGSLI_REGISTER_CANVAS_FEATURE(FeatureType)                            \
  static ::imgsli::app::StaticFeatureRegistration<FeatureType>                 \
      register_##FeatureType

} // namespace imgsli::app

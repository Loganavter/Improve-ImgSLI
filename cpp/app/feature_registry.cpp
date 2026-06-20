#include "feature_registry.h"

namespace imgsli::app {

FeatureRegistry &FeatureRegistry::instance() {
  static FeatureRegistry registry;
  return registry;
}

void FeatureRegistry::add(std::unique_ptr<CanvasWidgetFeature> feature) {
  features_.push_back(std::move(feature));
}

const std::vector<std::unique_ptr<CanvasWidgetFeature>> &
FeatureRegistry::features() const {
  return features_;
}

QStringList FeatureRegistry::names() const {
  QStringList result;
  for (const auto &feature : features_) {
    result.append(feature->name());
  }
  return result;
}

} // namespace imgsli::app

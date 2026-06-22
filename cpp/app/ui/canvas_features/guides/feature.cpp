#include "core/feature_registry.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class GuidesFeature final : public CanvasWidgetFeature {
 public:
  QString name() const override { return QStringLiteral("guides"); }
  QStringList commandIds() const override {
    return {QStringLiteral("set_enabled")};
  }
  void applyDefaults(CanvasRenderPlan &) const override {}
  bool execute(CanvasRenderPlan &plan, const QString &commandId,
               const QVariant &value) const override {
    if (commandId != QStringLiteral("set_enabled")) {
      return false;
    }
    plan.guidesEnabled = value.toBool();
    return true;
  }
};

IMGSLI_REGISTER_CANVAS_FEATURE(GuidesFeature);

}  // namespace imgsli::app

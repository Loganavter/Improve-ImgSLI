#include "core/feature_registry.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class MagnifierFeature final : public CanvasWidgetFeature {
 public:
  QString name() const override { return QStringLiteral("magnifier"); }
  QStringList commandIds() const override {
    return {
        QStringLiteral("set_enabled"), QStringLiteral("set_x"),
        QStringLiteral("set_y"),       QStringLiteral("set_radius"),
        QStringLiteral("set_zoom"),
    };
  }
  void applyDefaults(CanvasRenderPlan &plan) const override {
    plan.magnifierRadius = qBound(0.04F, plan.magnifierRadius, 0.45F);
    plan.magnifierZoom = qMax(1.0F, plan.magnifierZoom);
  }
  bool execute(CanvasRenderPlan &plan, const QString &commandId,
               const QVariant &value) const override {
    if (commandId == QStringLiteral("set_enabled")) {
      plan.magnifierEnabled = value.toBool();
      plan.captureEnabled = value.toBool();
    } else if (commandId == QStringLiteral("set_x")) {
      plan.magnifierX = qBound(0.0F, value.toFloat(), 1.0F);
    } else if (commandId == QStringLiteral("set_y")) {
      plan.magnifierY = qBound(0.0F, value.toFloat(), 1.0F);
    } else if (commandId == QStringLiteral("set_radius")) {
      plan.magnifierRadius = qBound(0.04F, value.toFloat(), 0.45F);
    } else if (commandId == QStringLiteral("set_zoom")) {
      plan.magnifierZoom = qMax(1.0F, value.toFloat());
    } else {
      return false;
    }
    return true;
  }
};

IMGSLI_REGISTER_CANVAS_FEATURE(MagnifierFeature);

}  // namespace imgsli::app

#include "core/feature_registry.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class CaptureFeature final : public CanvasWidgetFeature {
 public:
  QString name() const override { return QStringLiteral("capture"); }
  QStringList commandIds() const override {
    return {
        QStringLiteral("set_enabled"),
        QStringLiteral("set_x"),
        QStringLiteral("set_y"),
    };
  }
  void applyDefaults(CanvasRenderPlan &) const override {}
  bool execute(CanvasRenderPlan &plan, const QString &commandId,
               const QVariant &value) const override {
    if (commandId == QStringLiteral("set_enabled")) {
      plan.captureEnabled = value.toBool();
    } else if (commandId == QStringLiteral("set_x")) {
      plan.captureX = qBound(0.0F, value.toFloat(), 1.0F);
    } else if (commandId == QStringLiteral("set_y")) {
      plan.captureY = qBound(0.0F, value.toFloat(), 1.0F);
    } else {
      return false;
    }
    return true;
  }
};

IMGSLI_REGISTER_CANVAS_FEATURE(CaptureFeature);

}  // namespace imgsli::app

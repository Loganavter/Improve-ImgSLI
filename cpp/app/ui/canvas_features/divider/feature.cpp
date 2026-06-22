#include "core/feature_registry.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class DividerFeature final : public CanvasWidgetFeature {
 public:
  QString name() const override { return QStringLiteral("divider"); }
  QStringList commandIds() const override {
    return {
        QStringLiteral("set_split"),
        QStringLiteral("set_horizontal"),
        QStringLiteral("set_visible"),
        QStringLiteral("set_thickness"),
    };
  }
  void applyDefaults(CanvasRenderPlan &plan) const override {
    plan.dividerEnabled = true;
    plan.dividerThickness = qMax(1.0F, plan.dividerThickness);
  }
  bool execute(CanvasRenderPlan &plan, const QString &commandId,
               const QVariant &value) const override {
    if (commandId == QStringLiteral("set_split")) {
      plan.split = qBound(0.0F, value.toFloat(), 1.0F);
    } else if (commandId == QStringLiteral("set_horizontal")) {
      plan.horizontal = value.toBool();
    } else if (commandId == QStringLiteral("set_visible")) {
      plan.dividerEnabled = value.toBool();
    } else if (commandId == QStringLiteral("set_thickness")) {
      plan.dividerThickness = qMax(0.0F, value.toFloat());
    } else {
      return false;
    }
    return true;
  }
};

IMGSLI_REGISTER_CANVAS_FEATURE(DividerFeature);

}  // namespace imgsli::app

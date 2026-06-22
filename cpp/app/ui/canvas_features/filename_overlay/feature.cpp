#include "core/feature_registry.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class FilenameOverlayFeature final : public CanvasWidgetFeature {
 public:
  QString name() const override { return QStringLiteral("filename_overlay"); }
  QStringList commandIds() const override {
    return {QStringLiteral("set_enabled")};
  }
  void applyDefaults(CanvasRenderPlan &) const override {}
  bool execute(CanvasRenderPlan &plan, const QString &commandId,
               const QVariant &value) const override {
    if (commandId != QStringLiteral("set_enabled")) {
      return false;
    }
    plan.filenameEnabled = value.toBool();
    return true;
  }
};

IMGSLI_REGISTER_CANVAS_FEATURE(FilenameOverlayFeature);

}  // namespace imgsli::app

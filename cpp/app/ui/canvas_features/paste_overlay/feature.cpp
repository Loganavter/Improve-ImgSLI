#include "core/feature_registry.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class PasteOverlayFeature final : public CanvasWidgetFeature {
 public:
  QString name() const override { return QStringLiteral("paste_overlay"); }
  QStringList commandIds() const override {
    return {QStringLiteral("set_enabled")};
  }
  void applyDefaults(CanvasRenderPlan &) const override {}
  bool execute(CanvasRenderPlan &plan, const QString &commandId,
               const QVariant &value) const override {
    if (commandId != QStringLiteral("set_enabled")) {
      return false;
    }
    plan.pasteOverlayEnabled = value.toBool();
    return true;
  }
};

IMGSLI_REGISTER_CANVAS_FEATURE(PasteOverlayFeature);

}  // namespace imgsli::app

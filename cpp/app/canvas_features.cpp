#include "feature_registry.h"

#include "canvas_widget.h"

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

IMGSLI_REGISTER_CANVAS_FEATURE(DividerFeature);
IMGSLI_REGISTER_CANVAS_FEATURE(MagnifierFeature);
IMGSLI_REGISTER_CANVAS_FEATURE(GuidesFeature);
IMGSLI_REGISTER_CANVAS_FEATURE(FilenameOverlayFeature);
IMGSLI_REGISTER_CANVAS_FEATURE(CaptureFeature);
IMGSLI_REGISTER_CANVAS_FEATURE(PasteOverlayFeature);

} // namespace imgsli::app

#pragma once

#include <QString>
#include <QStringList>
#include <QVariant>
#include <QtPlugin>

namespace imgsli::app {

struct CanvasRenderPlan;

class CanvasWidgetFeature {
public:
  virtual ~CanvasWidgetFeature() = default;
  [[nodiscard]] virtual QString name() const = 0;
  [[nodiscard]] virtual QStringList commandIds() const = 0;
  virtual void applyDefaults(CanvasRenderPlan &plan) const = 0;
  virtual bool execute(CanvasRenderPlan &plan, const QString &commandId,
                       const QVariant &value) const = 0;
};

} // namespace imgsli::app

#define ImgSliCanvasWidgetFeature_iid                                          \
  "io.github.Loganavter.ImproveImgSLI.CanvasWidgetFeature/1.0"
Q_DECLARE_INTERFACE(imgsli::app::CanvasWidgetFeature,
                    ImgSliCanvasWidgetFeature_iid)

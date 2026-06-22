#include "plugins/export/services/canvas_export.h"

#include <QImage>
#include <QSize>
#include <QString>
#include <QVariantList>

#include <algorithm>

#include "core/plugin_registry.h"
#include "plugins/export/services/image_export.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app::export_services {

namespace {

QSize resolveTargetSize(CanvasWidget* sourceCanvas, const QVariantMap& args) {
  const int rawWidth = args.value(QStringLiteral("width"), 0).toInt();
  const int rawHeight = args.value(QStringLiteral("height"), 0).toInt();
  if (rawWidth > 0 && rawHeight > 0) {
    return {rawWidth, rawHeight};
  }
  const bool sourceResolution =
      args.value(QStringLiteral("source_resolution"), false).toBool();
  if (sourceResolution) {
    const CanvasRenderPlan plan = sourceCanvas->renderPlan();
    return {std::max(1, plan.canvasWidth),
             std::max(1, plan.canvasHeight)};
  }
  return sourceCanvas->size();
}

}  // namespace

QVariantMap saveCanvas(const QVariantMap& args) {
  QVariantMap result{
      {QStringLiteral("ok"), false},
      {QStringLiteral("path"), args.value(QStringLiteral("path")).toString()},
  };
  auto* sourceCanvas = qobject_cast<CanvasWidget*>(
      args.value(QStringLiteral("canvas")).value<QObject*>());
  if (sourceCanvas == nullptr) {
    result.insert(QStringLiteral("error"),
                   QStringLiteral("Canvas service is unavailable"));
    return result;
  }

  const QSize targetSize = resolveTargetSize(sourceCanvas, args);
  const QVariantList rendered =
      PluginRegistry::instance()
          .callService(
              QStringLiteral("offscreen_renderer.render_batch"),
              {{QStringLiteral("requests"),
                QVariantList{QVariantMap{
                    {QStringLiteral("canvas"),
                      QVariant::fromValue<QObject*>(sourceCanvas)},
                    {QStringLiteral("width"), targetSize.width()},
                    {QStringLiteral("height"), targetSize.height()},
                }}}})
          .toList();
  const QImage image =
      rendered.isEmpty() ? QImage{} : rendered.constFirst().value<QImage>();
  if (image.isNull()) {
    result.insert(QStringLiteral("error"),
                   QStringLiteral("Canvas framebuffer is empty"));
    return result;
  }

  QVariantMap saveArgs = args;
  saveArgs.insert(QStringLiteral("image"), image);
  const bool ok = saveImage(saveArgs);
  result.insert(QStringLiteral("ok"), ok);
  result.insert(QStringLiteral("width"), image.width());
  result.insert(QStringLiteral("height"), image.height());
  if (!ok) {
    result.insert(QStringLiteral("error"),
                   QStringLiteral("Image encoder rejected the output"));
  }
  return result;
}

}  // namespace imgsli::app::export_services

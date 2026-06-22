#include "analysis_snapshot_command.h"

#include <QApplication>
#include <QTimer>
#include <QVariant>
#include <QVariantMap>

#include "plugins/analysis/controller.h"
#include "ui/canvas/canvas_widget.h"
#include "core/plugin_registry.h"

namespace imgsli::app::cli {

void installAnalysisSnapshotCommand(QApplication& app,
                                    AnalysisController* analysis,
                                    CanvasWidget* canvas,
                                    const QString& outputPath) {
  if (outputPath.isEmpty()) {
    return;
  }
  QObject::connect(
      analysis, &AnalysisController::analysisRendered, &app,
      [canvas, outputPath, &app]() {
        const QVariantMap result =
            PluginRegistry::instance()
                .callService(
                    QStringLiteral("export.save_canvas"),
                    {{QStringLiteral("path"), outputPath},
                     {QStringLiteral("canvas"),
                      QVariant::fromValue<QObject*>(canvas)},
                     {QStringLiteral("source_resolution"), true}})
                .toMap();
        app.exit(result.value(QStringLiteral("ok")).toBool() ? 0 : 25);
      },
      Qt::SingleShotConnection);
  QTimer::singleShot(15000, &app, [&app]() { app.exit(26); });
}

}  // namespace imgsli::app::cli

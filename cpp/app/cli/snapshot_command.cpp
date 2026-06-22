#include "snapshot_command.h"

#include <QApplication>
#include <QVariant>
#include <QVariantMap>

#include "ui/canvas/canvas_widget.h"
#include "core/plugin_registry.h"
#include "startup_options.h"

namespace imgsli::app::cli {

void installSnapshotCommand(QApplication& app, CanvasWidget* canvas,
                            const StartupOptions& options) {
  if (!options.smokeExit && options.snapshotPath.isEmpty()) {
    return;
  }
  QObject::connect(
      canvas, &CanvasWidget::frameRendered, &app,
      [canvas, snapshotPath = options.snapshotPath, &app]() {
        if (!snapshotPath.isEmpty()) {
          const QVariant result = PluginRegistry::instance().callService(
              QStringLiteral("export.save_canvas"),
              {{QStringLiteral("path"), snapshotPath},
               {QStringLiteral("canvas"),
                QVariant::fromValue<QObject*>(canvas)},
               {QStringLiteral("source_resolution"), true}});
          if (!result.toMap().value(QStringLiteral("ok")).toBool()) {
            app.exit(15);
            return;
          }
        }
        app.quit();
      },
      Qt::QueuedConnection);
}

}  // namespace imgsli::app::cli

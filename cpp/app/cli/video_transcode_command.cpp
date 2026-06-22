#include "video_transcode_command.h"

#include <QApplication>
#include <QTimer>

#include "startup_options.h"
#include "plugins/video_editor/controller.h"

namespace imgsli::app::cli {

void installVideoTranscodeCommand(QApplication& app,
                                  VideoEditorController* controller,
                                  const VideoTranscodeOptions& options) {
  if (options.size.has_value()) {
    controller->setAspectRatioLocked(false);
    controller->setResolution(options.size->width(), options.size->height());
  }
  if (options.fps.has_value()) {
    controller->setFps(*options.fps);
  }
  QObject::connect(
      controller, &VideoEditorController::exportFinished, &app,
      [&app](bool ok, const QString& message) {
        if (!ok) {
          qCritical("Video transcode failed: %s", qPrintable(message));
        }
        app.exit(ok ? 0 : 20);
      });
  QTimer::singleShot(
      0, controller,
      [controller, input = options.input, output = options.output, &app]() {
        if (!controller->startExport(input, output)) {
          app.exit(21);
        }
      });
}

}  // namespace imgsli::app::cli

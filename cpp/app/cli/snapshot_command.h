#pragma once

class QApplication;

namespace imgsli::app {
class CanvasWidget;
}

namespace imgsli::app::cli {

struct StartupOptions;

void installSnapshotCommand(QApplication& app, CanvasWidget* canvas,
                            const StartupOptions& options);

}  // namespace imgsli::app::cli

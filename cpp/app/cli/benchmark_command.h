#pragma once

class QApplication;

namespace imgsli::app {
class CanvasWidget;
}

namespace imgsli::app::cli {

void installBenchmarkCommand(QApplication& app, CanvasWidget* canvas,
                             int frameCount);

}  // namespace imgsli::app::cli

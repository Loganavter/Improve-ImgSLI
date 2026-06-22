#pragma once

#include <QString>

class QApplication;

namespace imgsli::app {
class AnalysisController;
class CanvasWidget;
}

namespace imgsli::app::cli {

void installAnalysisSnapshotCommand(QApplication& app,
                                    AnalysisController* analysis,
                                    CanvasWidget* canvas,
                                    const QString& outputPath);

}  // namespace imgsli::app::cli

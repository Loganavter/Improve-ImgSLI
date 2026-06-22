#pragma once

class QApplication;

namespace imgsli::app {
class AnalysisController;
class ComparisonController;
}

namespace imgsli::app::cli {

struct StartupOptions;

void applyComparisonCommand(QApplication& app,
                            ComparisonController* comparison,
                            AnalysisController* analysis,
                            const StartupOptions& options);

}  // namespace imgsli::app::cli

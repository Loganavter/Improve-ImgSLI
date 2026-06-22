#pragma once

#include <QString>

namespace imgsli::app {
class AnalysisController;
class ComparisonController;
class Store;
}

namespace imgsli::app::cli {

bool applySessionBlueprintCommand(Store* store,
                                  ComparisonController* comparison,
                                  AnalysisController* analysis,
                                  const QString& path, QString* error);

}  // namespace imgsli::app::cli

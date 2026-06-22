#pragma once

#include <QString>

class QLabel;
class QVBoxLayout;
class QWidget;

namespace sli::toolkit {
class Button;
}

namespace imgsli::app {
class AnalysisController;
class ComparisonController;
}  // namespace imgsli::app

namespace imgsli::app::multi_compare_sections {

// Page context shared across all three sections. The original
// monolithic `createPage` captured these as locals; centralising them
// lets each section live in its own translation unit.
struct PageContext {
  QWidget* root = nullptr;
  QVBoxLayout* layout = nullptr;
  ComparisonController* controller = nullptr;
  AnalysisController* analysisController = nullptr;
  QLabel* status = nullptr;
};

sli::toolkit::Button* makeToggleButton(QWidget* parent,
                                        const QString& translationKey,
                                        const QString& objectName,
                                        bool checked);

void buildComparisonControlsSection(PageContext& ctx);
void buildAnalysisControlsSection(PageContext& ctx);
void buildGridSection(PageContext& ctx);

}  // namespace imgsli::app::multi_compare_sections

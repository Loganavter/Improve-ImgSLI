#include "comparison_command.h"

#include <QApplication>
#include <QTimer>

#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"
#include "startup_options.h"

namespace imgsli::app::cli {

void applyComparisonCommand(QApplication& app,
                            ComparisonController* comparison,
                            AnalysisController* analysis,
                            const StartupOptions& options) {
  Q_UNUSED(app);
  if (!options.diffMode.isEmpty()) {
    analysis->setDiffMode(options.diffMode);
  }
  if (!options.channelMode.isEmpty()) {
    analysis->setChannelMode(options.channelMode);
  }
  comparison->setHorizontal(options.horizontal);
  comparison->setMagnifierEnabled(options.magnifierEnabled);
  comparison->setGuidesEnabled(options.guidesEnabled);
  comparison->setPasteOverlayEnabled(options.pasteOverlayEnabled);
  if (options.splitSpecified) {
    comparison->setSplit(options.split);
  }
  if (!options.compareLeftPath.isEmpty()) {
    QTimer::singleShot(
        0, comparison,
        [comparison, left = options.compareLeftPath,
         right = options.compareRightPath]() {
          comparison->openPair(left, right);
        });
  } else if (!options.openPath.isEmpty()) {
    QTimer::singleShot(
        0, comparison,
        [comparison, path = options.openPath]() {
          comparison->openPair(path, QString());
        });
  }
}

}  // namespace imgsli::app::cli

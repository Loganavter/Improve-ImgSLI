// Mirrors src/plugins/comparison/use_cases/navigation.py — the
// user-facing file-pair picker. The actual decode + scaling are owned
// by use_cases/loading.cpp.

#include <QFileDialog>
#include <QString>
#include <QStringList>
#include <QWidget>

#include "plugins/comparison/controller.h"

namespace imgsli::app {

void ComparisonController::openDialog(QWidget* parent) {
  const QStringList paths = QFileDialog::getOpenFileNames(
      parent, QStringLiteral("Open one or two images"), {},
      QStringLiteral(
          "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff);;"
          "All files (*)"));
  if (!paths.isEmpty()) {
    openPair(paths[0], paths.size() > 1 ? paths[1] : QString());
  }
}

}  // namespace imgsli::app

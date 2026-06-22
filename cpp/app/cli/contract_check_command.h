#pragma once

class QApplication;
class QWidget;

namespace imgsli::app {
class CanvasWidget;
class CustomWindow;
}  // namespace imgsli::app

namespace imgsli::app::cli {

// Runs the full --contract-check assertion battery exercised by ctest
// phase3_contracts. Returns 0 on success or a non-zero exit code that
// pinpoints the failing contract.
int runContractCheck(QApplication &app, CustomWindow &window, QWidget *central,
                     CanvasWidget *canvas);

}  // namespace imgsli::app::cli

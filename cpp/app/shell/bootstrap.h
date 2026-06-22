#pragma once

class QApplication;
class QVBoxLayout;
class QWidget;

namespace imgsli::app {
class CanvasWidget;
class CustomWindow;
namespace cli {
struct StartupOptions;
}
}  // namespace imgsli::app

namespace imgsli::app::shell {

// Builds the live application UI: store, controllers, toolbar, theme
// switcher, workspace tabs, settings/help flyouts, and wires per-CLI
// commands that need a constructed controller (video transcode, analysis
// snapshot, comparison restore, session blueprint restore).
//
// Returns 0 on success or a non-zero exit code when a startup option
// (e.g. invalid session blueprint) failed to apply.
int buildMainUi(QApplication &app, CustomWindow &window, QWidget *central,
                QVBoxLayout *layout, CanvasWidget *canvas,
                const cli::StartupOptions &options);

}  // namespace imgsli::app::shell

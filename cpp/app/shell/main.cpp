// ImgSLI C++/Rust port — entry point.
//
// Everything Qt-touching stays on this side. Rust never sees QObject types.
// The bulk of the application wiring lives in shell/bootstrap.cpp; the
// --contract-check assertion battery exercised by ctest phase3_contracts
// lives in cli/contract_check_command.cpp.

#include <QApplication>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

#include "cli/contract_check_command.h"
#include "cli/snapshot_command.h"
#include "cli/startup_options.h"
#include "cli/benchmark_command.h"
#include "shell/bootstrap.h"
#include "shell/custom_window.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/theme.h"
#include "ui/canvas/canvas_widget.h"

int main(int argc, char **argv) {
  QApplication app(argc, argv);

  const imgsli::app::cli::StartupOptions options =
      imgsli::app::cli::StartupOptions::parse(app.arguments());
  if (!options.valid) {
    qCritical("%s", qPrintable(options.error));
    return 64;
  }

  sli::toolkit::Theme::apply(app, sli::toolkit::Theme::Mode::Light);
  imgsli::app::initI18n(QStringLiteral(IMGSLI_I18N_ROOT));
  imgsli::app::setLanguage(QStringLiteral("en"));

  imgsli::app::CustomWindow window;
  window.setTitleText(QStringLiteral("Improve ImgSLI"));

  auto *central = new QWidget(&window);
  auto *layout = new QVBoxLayout(central);
  auto *canvas = new imgsli::app::CanvasWidget(central);
  layout->addWidget(canvas);

  imgsli::app::cli::installSnapshotCommand(app, canvas, options);

  if (options.contractCheck) {
    return imgsli::app::cli::runContractCheck(app, window, central, canvas);
  }

  imgsli::app::cli::installBenchmarkCommand(app, canvas, options.benchmarkFrames);

  if (const int rc = imgsli::app::shell::buildMainUi(app, window, central,
                                                     layout, canvas, options);
      rc != 0) {
    return rc;
  }

  return app.exec();
}

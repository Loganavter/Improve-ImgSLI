// Application composer — mirror of Python `composer.py` + part of
// `window.py`. Widget construction lives in `ui.{h,cpp}`, layout in
// `layouts.{h,cpp}`. This file wires controllers, plugin services, CLI
// commands and toolbar QObject::connect calls.

#include "shell/bootstrap.h"

#include <QAbstractButton>
#include <QApplication>
#include <QDir>
#include <QFileDialog>
#include <QImage>
#include <QPainter>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QStandardPaths>
#include <QString>
#include <QTabWidget>
#include <QVBoxLayout>
#include <QVariant>
#include <QVariantMap>
#include <QWidget>

#include "cli/analysis_snapshot_command.h"
#include "cli/comparison_command.h"
#include "cli/session_blueprint_command.h"
#include "cli/startup_options.h"
#include "cli/video_transcode_command.h"
#include "core/plugin_registry.h"
#include "core/store.h"
#include "core/tab_registry.h"
#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"
#include "plugins/settings/application_service.h"
#include "plugins/settings/dialog.h"
#include "plugins/video_editor/controller.h"
#include "shell/custom_window.h"
#include "shell/i18n_helper.h"
#include "shell/layouts.h"
#include "shell/ui.h"
#include "sli/toolkit/atomic/slider.h"
#include "sli/toolkit/buttons/button.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app::shell {

namespace {

QString defaultSavePath() {
  const QString dir =
      QStandardPaths::writableLocation(QStandardPaths::PicturesLocation);
  return QDir(dir).filePath(QStringLiteral("imgsli-comparison.png"));
}

void invokeSaveCurrent(CustomWindow* window, CanvasWidget* canvas) {
  const QString path = QFileDialog::getSaveFileName(
      window, QStringLiteral("Save current comparison"), defaultSavePath(),
      QStringLiteral("PNG image (*.png);;JPEG image (*.jpg *.jpeg)"));
  if (path.isEmpty()) {
    return;
  }
  PluginRegistry::instance().callService(
      QStringLiteral("export.save_canvas"),
      {{QStringLiteral("path"), path},
       {QStringLiteral("canvas"), QVariant::fromValue<QObject*>(canvas)},
       {QStringLiteral("source_resolution"), true}});
}

}  // namespace

int buildMainUi(QApplication& app, CustomWindow& window, QWidget* central,
                QVBoxLayout* layout, CanvasWidget* canvas,
                const cli::StartupOptions& options) {
  // The QVBoxLayout passed in already owns the canvas — pull it out so the
  // composer can re-insert it at the right slot.
  layout->removeWidget(canvas);

  // -------- stage 1: widget construction (mirror Python ui.py) ----------
  MainWindowUi ui;
  ui.setupUi(central);

  // -------- stage 2: layout assembly (mirror Python layouts.py) ----------
  LayoutComposer composer(ui, canvas);
  composer.build(central, layout);

  // -------- stage 3: controller wiring (mirror Python composer.py) ------
  auto* store = new Store(central);
  PluginRegistry::instance().activateAll(store);
  auto* comparisonController =
      new ComparisonController(store, canvas, central);
  auto* analysisController =
      new AnalysisController(store, comparisonController, central);
  auto* videoEditorController = new VideoEditorController(central);
  QObject::connect(&app, &QApplication::aboutToQuit,
                   []() { PluginRegistry::instance().deactivateAll(); });

  // -------- stage 4: toolbar QObject::connect (Python presenter signals) -
  QObject::connect(ui.btnImage1, &QAbstractButton::clicked, comparisonController,
                   [comparisonController, &window]() {
                     comparisonController->openDialog(&window);
                   });
  QObject::connect(ui.btnImage2, &QAbstractButton::clicked, comparisonController,
                   [comparisonController, &window]() {
                     comparisonController->openDialog(&window);
                   });

  QObject::connect(ui.sliderSplit, &QAbstractSlider::valueChanged,
                   canvas, [comparisonController](int value) {
                     comparisonController->setSplit(value / 1000.0F);
                   });
  QObject::connect(ui.btnOrientation, &QAbstractButton::toggled, canvas,
                   [comparisonController](bool enabled) {
                     comparisonController->setHorizontal(enabled);
                   });
  QObject::connect(ui.btnMagnifier, &QAbstractButton::toggled, canvas,
                   [comparisonController](bool enabled) {
                     comparisonController->setMagnifierEnabled(enabled);
                   });
  QObject::connect(ui.btnMagnifierGuides, &QAbstractButton::toggled, canvas,
                   [comparisonController](bool enabled) {
                     comparisonController->setGuidesEnabled(enabled);
                   });

  // Python's «tabs that open» — toggle buttons gate side-panel visibility.
  QObject::connect(ui.btnMagnifier, &QAbstractButton::toggled,
                   ui.magnifierSettingsPanel, &QWidget::setVisible);
  QWidget* filenameRow = ui.btnFileNames->property("__filenameEditRow")
                              .value<QWidget*>();
  if (filenameRow != nullptr) {
    QObject::connect(ui.btnFileNames, &QAbstractButton::toggled, filenameRow,
                     &QWidget::setVisible);
  }

  // Save action — uses the export plugin's canvas-save service so it shares
  // the offscreen renderer the Export tab uses.
  QObject::connect(ui.btnSave, &QAbstractButton::clicked, &window,
                   [&window, canvas]() { invokeSaveCurrent(&window, canvas); });
  QObject::connect(ui.btnQuickSave, &QAbstractButton::clicked, &window,
                   [&window, canvas]() { invokeSaveCurrent(&window, canvas); });

  // -------- stage 5: plugin service bindings ----------------------------
  auto* qsettings = new QSettings(QStringLiteral("ImgSLI"),
                                  QStringLiteral("ImgSLI"), &window);
  auto* settingsService =
      new SettingsApplicationService(store, qsettings, &window);
  PluginRegistry::instance().callService(
      QStringLiteral("settings.bind_service"),
      {{QStringLiteral("service"), QVariant::fromValue(settingsService)}});
  PluginRegistry::instance().callService(
      QStringLiteral("video_editor.bind_canvas"),
      {{QStringLiteral("canvas"), QVariant::fromValue<QObject*>(canvas)}});
  PluginRegistry::instance().callService(
      QStringLiteral("video_editor.bind_comparison"),
      {{QStringLiteral("controller"),
        QVariant::fromValue<QObject*>(comparisonController)}});

  QObject::connect(ui.helpButton, &QAbstractButton::clicked, &window,
                   [&window]() {
                     PluginRegistry::instance().callService(
                         QStringLiteral("help.show"),
                         {{QStringLiteral("parent"),
                           QVariant::fromValue<QObject*>(&window)}});
                   });
  QObject::connect(ui.btnSettings, &QAbstractButton::clicked, &window,
                   [&window]() {
                     SettingsDialog dialog(&window);
                     const QString prevJson = dialog.normalizedJson();
                     if (dialog.exec() == QDialog::Accepted) {
                       const QString nextJson = dialog.normalizedJson();
                       PluginRegistry::instance().callService(
                           QStringLiteral("settings.apply_dialog_diff"),
                           {{QStringLiteral("prev"), prevJson},
                            {QStringLiteral("next"), nextJson}});
                       const QJsonObject next =
                           QJsonDocument::fromJson(nextJson.toUtf8()).object();
                       const QString mode =
                           next.value(QStringLiteral("ui_mode"))
                               .toString(QStringLiteral("beginner"));
                       PluginRegistry::instance().callService(
                           QStringLiteral("layout.apply_mode"),
                           {{QStringLiteral("mode"), mode}});
                       const QString language =
                           next.value(QStringLiteral("language"))
                               .toString(QStringLiteral("en"));
                       setLanguage(language);
                       PluginRegistry::instance().callService(
                           QStringLiteral("help.set_language"),
                           {{QStringLiteral("language"), language}});
                     }
                   });

  // Plugin TabRegistry pages are constructed off-screen so plugins receive
  // their `bindServices` lifecycle even though Python's main window has no
  // tab strip. Tracked in TOOLKIT_PORT_AUDIT under «plugin surfaces».
  const auto& registeredTabs = TabRegistry::instance().tabs();
  if (!registeredTabs.empty()) {
    auto* hiddenHost = new QTabWidget(central);
    hiddenHost->hide();
    for (auto* tab : registeredTabs) {
      tab->bindServices(
          {{QStringLiteral("canvas"), QVariant::fromValue<QObject*>(canvas)},
           {QStringLiteral("comparisonController"),
            QVariant::fromValue<QObject*>(comparisonController)},
           {QStringLiteral("analysisController"),
            QVariant::fromValue<QObject*>(analysisController)},
           {QStringLiteral("videoEditorController"),
            QVariant::fromValue<QObject*>(videoEditorController)}});
      QWidget* page = tab->createPage(hiddenHost);
      hiddenHost->addTab(page, tab->displayName());
    }
  }

  const QVariantMap layoutControls{
      {QStringLiteral("split"),
       QVariant::fromValue<QObject*>(ui.sliderSplit)},
      {QStringLiteral("orientation"),
       QVariant::fromValue<QObject*>(ui.btnOrientation)},
      {QStringLiteral("magnifier"),
       QVariant::fromValue<QObject*>(ui.btnMagnifier)},
      {QStringLiteral("guides"),
       QVariant::fromValue<QObject*>(ui.btnMagnifierGuides)},
      {QStringLiteral("settings"),
       QVariant::fromValue<QObject*>(ui.btnSettings)},
      {QStringLiteral("help"),
       QVariant::fromValue<QObject*>(ui.helpButton)},
  };
  PluginRegistry::instance().callService(
      QStringLiteral("layout.bind_controls"),
      {{QStringLiteral("controls"), layoutControls},
       {QStringLiteral("mode"), QStringLiteral("beginner")}});

  // -------- stage 6: show window + apply CLI options --------------------
  window.setBody(central);
  window.resize(1280, 800);
  window.show();

  // Diagnostic — `IMGSLI_WINDOW_SNAPSHOT=/path/to.png` renders the live
  // composed window to a PNG immediately after show() so devs can inspect
  // shell paint output headless (QT_QPA_PLATFORM=offscreen). No effect
  // when the env var is unset.
  if (const QString snap =
          qEnvironmentVariable("IMGSLI_WINDOW_SNAPSHOT");
      !snap.isEmpty()) {
    QApplication::processEvents();
    QImage image(window.size(), QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::white);
    QPainter painter(&image);
    window.render(&painter);
    painter.end();
    image.save(snap, "PNG");
  }

  if (options.videoTranscode.has_value()) {
    cli::installVideoTranscodeCommand(app, videoEditorController,
                                       *options.videoTranscode);
  }
  cli::installAnalysisSnapshotCommand(app, analysisController, canvas,
                                       options.analysisSnapshotPath);
  cli::applyComparisonCommand(app, comparisonController, analysisController,
                               options);
  QString sessionBlueprintError;
  if (!cli::applySessionBlueprintCommand(
          store, comparisonController, analysisController,
          options.sessionBlueprintPath, &sessionBlueprintError)) {
    qCritical("%s", qPrintable(sessionBlueprintError));
    return 65;
  }
  return 0;
}

}  // namespace imgsli::app::shell

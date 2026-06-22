#include "cli/contract_check_command.h"

#include <QApplication>
#include <QCoreApplication>
#include <QEvent>
#include <QEventLoop>
#include <QFileInfo>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeyEvent>
#include <QKeySequence>
#include <QLabel>
#include <QMetaObject>
#include <QShortcut>
#include <QSlider>
#include <QString>
#include <QStringList>
#include <QStyle>
#include <QTemporaryDir>
#include <QTemporaryFile>
#include <QTimer>
#include <QVariant>
#include <QVariantMap>

#include <vector>

#include "cli/session_blueprint_command.h"
#include "cli/startup_options.h"
#include "core/feature_registry.h"
#include "core/plugin_registry.h"
#include "core/store.h"
#include "core/tab_registry.h"
#include "imgsli_core_bridge/bridge.h"
#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"
#include "plugins/video_editor/controller.h"
#include "plugins/video_editor/services/keyframe_policy.h"
#include "shell/custom_window.h"
#include "sli/toolkit/buttons/chip_group.h"
#include "sli/toolkit/composite/flyout.h"
#include "sli/toolkit/atomic/icon.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "sli/toolkit/composite/toolbar.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app::cli {

int runContractCheck(QApplication &app, CustomWindow &window, QWidget *central,
                     CanvasWidget *canvas) {
  const std::vector<imgsli::NormalizedBoundsF64> layoutRequirements{
      {.x_min = -0.125, .x_max = 1.125, .y_min = -0.25, .y_max = 1.5},
  };
  const imgsli::NormalizedBoundsF64 contentBounds{
      .x_min = 0.0, .x_max = 1.0, .y_min = 0.0, .y_max = 1.0};
  const imgsli::VirtualCanvasLayoutF64 virtualLayout =
      imgsli::resolve_virtual_canvas_layout(
          rust::Slice<const imgsli::NormalizedBoundsF64>(
              layoutRequirements.data(), layoutRequirements.size()),
          contentBounds);
  const imgsli::PaddingI32 virtualPadding =
      imgsli::resolve_virtual_canvas_padding(virtualLayout, 100, 50);
  const imgsli::ContentLayoutI32 contentLayout =
      imgsli::compute_content_layout(101, 100, 3, 2, false);
  if (virtualPadding.left != 12 || virtualPadding.right != 12 ||
      virtualPadding.top != 12 || virtualPadding.bottom != 25 ||
      contentLayout.content_width != 101 ||
      contentLayout.content_height != 67 || contentLayout.content_x != 0 ||
      contentLayout.content_y != 16) {
    qCritical("Rust virtual canvas layout contract failed");
    return 43;
  }

  const imgsli::app::cli::StartupOptions parserProbe =
      imgsli::app::cli::StartupOptions::parse(
          {QStringLiteral("imgsli_app"), QStringLiteral("--compare"),
           QStringLiteral("left.png"), QStringLiteral("right.png"),
           QStringLiteral("--split"), QStringLiteral("1.5"),
           QStringLiteral("--horizontal"), QStringLiteral("--no-guides"),
           QStringLiteral("--video-transcode"), QStringLiteral("in.mkv"),
           QStringLiteral("out.mp4"), QStringLiteral("--video-size"),
           QStringLiteral("1280x720"), QStringLiteral("--video-fps"),
           QStringLiteral("30"), QStringLiteral("--session-blueprint"),
           QStringLiteral("session.json")});
  const imgsli::app::cli::StartupOptions invalidParserProbe =
      imgsli::app::cli::StartupOptions::parse({QStringLiteral("imgsli_app"),
                                                QStringLiteral("--split"),
                                                QStringLiteral("broken")});
  if (!parserProbe.valid ||
      parserProbe.compareLeftPath != QStringLiteral("left.png") ||
      parserProbe.compareRightPath != QStringLiteral("right.png") ||
      parserProbe.split != 1.0F || !parserProbe.horizontal ||
      parserProbe.guidesEnabled || !parserProbe.videoTranscode.has_value() ||
      parserProbe.videoTranscode->size != QSize(1280, 720) ||
      parserProbe.videoTranscode->fps != 30 ||
      parserProbe.sessionBlueprintPath != QStringLiteral("session.json") ||
      invalidParserProbe.valid) {
    qCritical("Typed CLI parser contract failed");
    return 42;
  }
  sli::toolkit::ChipGroup chipProbe;
  chipProbe.addChip(QStringLiteral("a"), QStringLiteral("A"));
  chipProbe.addChip(QStringLiteral("b"), QStringLiteral("B"));
  if (!chipProbe.setCurrentId(QStringLiteral("b")) ||
      chipProbe.currentId() != QStringLiteral("b") ||
      chipProbe.ids() !=
          QStringList{QStringLiteral("a"), QStringLiteral("b")}) {
    qCritical("Toolkit ChipGroup selection contract failed");
    return 39;
  }
  sli::toolkit::Icon iconProbe(
      app.style()->standardIcon(QStyle::SP_DialogOpenButton));
  iconProbe.setIconSize(QSize(20, 20));
  if (iconProbe.icon().isNull() || iconProbe.sizeHint().width() < 20) {
    qCritical("Toolkit Icon contract failed");
    return 40;
  }
  QWidget flyoutHost;
  QWidget flyoutAnchor(&flyoutHost);
  flyoutAnchor.resize(40, 24);
  sli::toolkit::Flyout firstFlyout(&flyoutHost);
  sli::toolkit::Flyout secondFlyout(&flyoutHost);
  firstFlyout.addWidget(new QLabel(QStringLiteral("First")));
  secondFlyout.addWidget(new QLabel(QStringLiteral("Second")));
  firstFlyout.showAligned(&flyoutAnchor);
  secondFlyout.showAligned(&flyoutAnchor);
  QKeyEvent escapeEvent(QEvent::KeyPress, Qt::Key_Escape, Qt::NoModifier);
  QCoreApplication::sendEvent(&secondFlyout, &escapeEvent);
  if (!firstFlyout.isHidden() || !secondFlyout.isHidden()) {
    qCritical("Toolkit Flyout active/Escape contract failed");
    return 41;
  }

  sli::toolkit::Toolbar toolbarProbe;
  toolbarProbe.addWidget(new QLabel(QStringLiteral("A"), &toolbarProbe));
  toolbarProbe.addSeparator();
  toolbarProbe.addWidget(new QLabel(QStringLiteral("B"), &toolbarProbe));
  if (toolbarProbe.findChildren<QWidget *>(QStringLiteral("sliDivider"),
                                            Qt::FindChildrenRecursively)
          .size() != 1) {
    qCritical("Toolkit Toolbar separator contract failed");
    return 38;
  }

  auto *maximizeButton =
      window.findChild<QWidget *>(QStringLiteral("customMaximizeButton"));
  auto *titleBar =
      window.findChild<QWidget *>(QStringLiteral("customTitleBar"));
  if (maximizeButton == nullptr || titleBar == nullptr ||
      !maximizeButton->property("hoverRippleEnabled").toBool() ||
      !titleBar->property("dragToRestoreEnabled").toBool() ||
      maximizeButton->property("windowStateGlyph").toString() !=
          QStringLiteral("maximize")) {
    qCritical("Custom title bar maximize control is not initialized");
    return 25;
  }
  window.showMaximized();
  app.processEvents();
  if (!window.isMaximized() ||
      maximizeButton->property("windowStateGlyph").toString() !=
          QStringLiteral("restore")) {
    qCritical("Custom title bar did not switch to the restore glyph");
    return 26;
  }
  window.showNormal();
  app.processEvents();
  if (window.isMaximized() ||
      maximizeButton->property("windowStateGlyph").toString() !=
          QStringLiteral("maximize")) {
    qCritical("Custom title bar did not restore the maximize glyph");
    return 27;
  }
  const auto shortcutMatches = [&window](const QString &name,
                                          const QString &sequence) {
    const auto *shortcut = window.findChild<QShortcut *>(name);
    return shortcut != nullptr && shortcut->key() == QKeySequence(sequence) &&
           shortcut->context() == Qt::WindowShortcut;
  };
  if (!shortcutMatches(QStringLiteral("customMinimizeShortcut"),
                       QStringLiteral("Alt+F9")) ||
      !shortcutMatches(QStringLiteral("customMaximizeShortcut"),
                       QStringLiteral("Alt+F10")) ||
      !shortcutMatches(QStringLiteral("customCloseShortcut"),
                       QStringLiteral("Alt+F4"))) {
    qCritical("Custom title bar keyboard accelerators are incomplete");
    return 28;
  }
  auto *maximizeShortcut =
      window.findChild<QShortcut *>(QStringLiteral("customMaximizeShortcut"));
  QMetaObject::invokeMethod(maximizeShortcut, "activated", Qt::DirectConnection);
  app.processEvents();
  if (!window.isMaximized()) {
    qCritical("Custom title bar maximize accelerator is not wired");
    return 29;
  }
  QMetaObject::invokeMethod(maximizeShortcut, "activated", Qt::DirectConnection);
  app.processEvents();
  if (window.isMaximized()) {
    qCritical("Custom title bar restore accelerator is not wired");
    return 30;
  }

  const QStringList requiredPasses{
      QStringLiteral("background"),       QStringLiteral("divider"),
      QStringLiteral("magnifier"),        QStringLiteral("guides"),
      QStringLiteral("filename_overlay"), QStringLiteral("capture"),
      QStringLiteral("paste_overlay"),
  };
  const QStringList requiredFeatures{
      QStringLiteral("divider"), QStringLiteral("magnifier"),
      QStringLiteral("guides"),  QStringLiteral("filename_overlay"),
      QStringLiteral("capture"), QStringLiteral("paste_overlay"),
  };
  const QStringList passNames = canvas->renderPassNames();
  const QStringList featureNames =
      imgsli::app::FeatureRegistry::instance().names();
  for (const QString &name : requiredPasses) {
    if (!passNames.contains(name)) {
      qCritical("Missing render pass: %s", qPrintable(name));
      return 2;
    }
  }
  for (const QString &name : requiredFeatures) {
    if (!featureNames.contains(name)) {
      qCritical("Missing canvas feature: %s", qPrintable(name));
      return 3;
    }
  }
  const auto &features = imgsli::app::FeatureRegistry::instance().features();
  const auto hasCommand = [&features](const QString &featureName,
                                       const QString &command) {
    for (const auto &feature : features) {
      if (feature->name() == featureName) {
        return feature->commandIds().contains(command);
      }
    }
    return false;
  };
  if (!hasCommand(QStringLiteral("divider"), QStringLiteral("set_split")) ||
      !hasCommand(QStringLiteral("magnifier"), QStringLiteral("set_x")) ||
      !hasCommand(QStringLiteral("guides"), QStringLiteral("set_enabled"))) {
    qCritical("Required feature commands are not registered");
    return 4;
  }
  const QStringList requiredTabs{QStringLiteral("multi_compare"),
                                  QStringLiteral("video_editor"),
                                  QStringLiteral("export")};
  for (const QString &sessionType : requiredTabs) {
    if (imgsli::app::TabRegistry::instance().find(sessionType) == nullptr) {
      qCritical("Missing tab: %s", qPrintable(sessionType));
      return 6;
    }
  }
  const QStringList requiredPlugins{
      QStringLiteral("analysis"),  QStringLiteral("comparison"),
      QStringLiteral("export"),    QStringLiteral("settings"),
      QStringLiteral("video_editor"), QStringLiteral("help"),
      QStringLiteral("layout"),    QStringLiteral("offscreen_renderer")};
  for (const QString &pluginId : requiredPlugins) {
    if (imgsli::app::PluginRegistry::instance().find(pluginId) == nullptr) {
      qCritical("Missing plugin: %s", qPrintable(pluginId));
      return 7;
    }
  }

  imgsli::app::Store checkStore(&app);
  int settingsUpdates = 0;
  int splitUpdates = 0;
  checkStore.subscribe(
      imgsli::app::StoreScope::settings(), &app,
      [&settingsUpdates](const imgsli::app::StoreUpdate &update) {
        if (update.payload.value(QStringLiteral("theme")).toString() ==
            QStringLiteral("dark")) {
          ++settingsUpdates;
        }
      });
  checkStore.subscribe(
      imgsli::app::StoreScope::viewport(QStringLiteral("split")), &app,
      [&splitUpdates](const imgsli::app::StoreUpdate &update) {
        const double split = update.payload.value(QStringLiteral("view_state"))
                                 .toObject()
                                 .value(QStringLiteral("split_position"))
                                 .toDouble();
        if (qAbs(split - 0.75) <= 0.0001) {
          ++splitUpdates;
        }
      });
  imgsli::app::AnalysisController subscriptionAnalysis(&checkStore, nullptr);
  imgsli::app::PluginRegistry::instance().activateAll(&checkStore);
  checkStore.dispatch(QStringLiteral(R"({"SetTheme":"dark"})"));
  const QVariant ok = imgsli::app::PluginRegistry::instance().callService(
      QStringLiteral("comparison.set_split"),
      {{QStringLiteral("value"), 0.75F}});
  checkStore.dispatch(QStringLiteral(R"({"SetDiffMode":"highlight"})"));
  app.processEvents();
  if (!ok.isValid() || !ok.toBool()) {
    qCritical("Plugin service routing failed for comparison.set_split");
    return 8;
  }
  if (settingsUpdates != 1 || splitUpdates != 1) {
    qCritical("Typed Store scoped subscription routing failed");
    return 32;
  }
  if (subscriptionAnalysis.diffMode() != QStringLiteral("highlight")) {
    qCritical("AnalysisController did not consume its Store subscription");
    return 33;
  }
  imgsli::app::ComparisonController subscriptionComparison(&checkStore, canvas);
  subscriptionComparison.setMagnifierEnabled(false);
  subscriptionComparison.setGuidesEnabled(true);
  subscriptionComparison.setPasteOverlayEnabled(true);
  const QJsonObject typedState =
      QJsonDocument::fromJson(checkStore.stateJson().toUtf8()).object();
  const QJsonObject typedFeatures = typedState.value(QStringLiteral("viewport"))
                                        .toObject()
                                        .value(QStringLiteral("view_state"))
                                        .toObject()
                                        .value(QStringLiteral("feature_state"))
                                        .toObject();
  if (subscriptionComparison.magnifierEnabled() ||
      !subscriptionComparison.guidesEnabled() ||
      !subscriptionComparison.pasteOverlayEnabled() ||
      typedFeatures.value(QStringLiteral("magnifier"))
              .toObject()
              .value(QStringLiteral("visible"))
              .toBool(true) ||
      typedFeatures.value(QStringLiteral("capture"))
          .toObject()
          .value(QStringLiteral("visible"))
          .toBool(true) ||
      !typedFeatures.value(QStringLiteral("guides"))
           .toObject()
           .value(QStringLiteral("visible"))
           .toBool() ||
      !typedFeatures.value(QStringLiteral("paste_overlay"))
           .toObject()
           .value(QStringLiteral("visible"))
           .toBool()) {
    qCritical("ComparisonController bypassed typed feature actions");
    return 34;
  }
  const QJsonObject sessionBlueprint{
      {QStringLiteral("session_type"), QStringLiteral("video_compare")},
      {QStringLiteral("plugin_name"), QStringLiteral("video_editor")},
      {QStringLiteral("title"), QStringLiteral("Video Compare")},
      {QStringLiteral("state_slots"),
       QJsonArray{
           QJsonObject{
               {QStringLiteral("name"), QStringLiteral("video.timeline")},
               {QStringLiteral("default"),
                QJsonObject{{QStringLiteral("position_ms"), 0}}},
           },
       }},
      {QStringLiteral("resource_namespaces"),
       QJsonArray{
           QJsonObject{
               {QStringLiteral("namespace"), QStringLiteral("thumbnails")},
               {QStringLiteral("entries"), QJsonObject{}},
           },
       }},
      {QStringLiteral("metadata_defaults"),
       QJsonObject{
           {QStringLiteral("plugin"), QStringLiteral("video_editor")},
       }},
  };
  if (!checkStore.createSessionFromBlueprint(sessionBlueprint)) {
    qCritical("Session blueprint dispatch failed");
    return 44;
  }
  const QJsonObject blueprintState =
      QJsonDocument::fromJson(checkStore.stateJson().toUtf8()).object();
  const QJsonObject blueprintSession =
      blueprintState.value(QStringLiteral("workspace"))
          .toObject()
          .value(QStringLiteral("sessions"))
          .toArray()
          .last()
          .toObject();
  if (blueprintSession.value(QStringLiteral("session_type")).toString() !=
          QStringLiteral("video_compare") ||
      blueprintSession.value(QStringLiteral("state_slots"))
              .toObject()
              .value(QStringLiteral("video.timeline"))
              .toObject()
              .value(QStringLiteral("position_ms"))
              .toInt(-1) != 0 ||
      !blueprintSession.value(QStringLiteral("resources"))
           .toObject()
           .contains(QStringLiteral("thumbnails")) ||
      blueprintSession.value(QStringLiteral("metadata"))
              .toObject()
              .value(QStringLiteral("plugin"))
              .toString() != QStringLiteral("video_editor")) {
    qCritical("Session blueprint defaults were not hydrated");
    return 45;
  }
  QTemporaryFile blueprintFile;
  if (!blueprintFile.open()) {
    qCritical("Could not create session blueprint contract fixture");
    return 46;
  }
  const QJsonObject fileBlueprint{
      {QStringLiteral("session_type"), QStringLiteral("image_compare")},
      {QStringLiteral("plugin_name"), QStringLiteral("comparison")},
      {QStringLiteral("title"), QStringLiteral("Restored Compare")},
      {QStringLiteral("comparison"),
       QJsonObject{
           {QStringLiteral("split"), 0.2},
           {QStringLiteral("horizontal"), true},
           {QStringLiteral("magnifier"), false},
           {QStringLiteral("guides"), false},
           {QStringLiteral("paste_overlay"), true},
           {QStringLiteral("diff_mode"), QStringLiteral("edges")},
           {QStringLiteral("channel_mode"), QStringLiteral("B")},
       }},
  };
  blueprintFile.write(
      QJsonDocument(fileBlueprint).toJson(QJsonDocument::Compact));
  blueprintFile.flush();
  QString blueprintError;
  if (!imgsli::app::cli::applySessionBlueprintCommand(
          &checkStore, &subscriptionComparison, &subscriptionAnalysis,
          blueprintFile.fileName(), &blueprintError) ||
      qAbs(subscriptionComparison.split() - 0.2F) > 0.0001F ||
      !subscriptionComparison.horizontal() ||
      subscriptionComparison.magnifierEnabled() ||
      subscriptionComparison.guidesEnabled() ||
      !subscriptionComparison.pasteOverlayEnabled() ||
      subscriptionAnalysis.diffMode() != QStringLiteral("edges") ||
      subscriptionAnalysis.channelMode() != QStringLiteral("B")) {
    qCritical("Session blueprint visual restore failed: %s",
              qPrintable(blueprintError));
    return 47;
  }
  const QVariant backend = imgsli::app::PluginRegistry::instance().callService(
      QStringLiteral("video_editor.backend"), {});
  if (backend.toString() != QStringLiteral("ffmpeg-cli")) {
    qCritical("Plugin service routing failed for video_editor.backend");
    return 9;
  }
  const QVariant newIndex = imgsli::app::PluginRegistry::instance().callService(
      QStringLiteral("comparison.playlist_remove_at"),
      {{QStringLiteral("len_before"), 5},
       {QStringLiteral("current"), 3},
       {QStringLiteral("removed_at"), 1}});
  if (newIndex.toInt() != 2) {
    qCritical(
        "Plugin service routing failed for comparison.playlist_remove_at (got "
        "%d, expected 2)",
        newIndex.toInt());
    return 10;
  }
  const QVariant projectJson =
      imgsli::app::PluginRegistry::instance().callService(
          QStringLiteral("video_editor.project_default"), {});
  if (!projectJson.toString().contains(QStringLiteral("\"fps\":60"))) {
    qCritical(
        "Plugin service routing failed for video_editor.project_default");
    return 11;
  }
  const QVariant advanced = imgsli::app::PluginRegistry::instance().callService(
      QStringLiteral("video_editor.timeline_advance"),
      {{QStringLiteral("position"), 5}, {QStringLiteral("step"), 3}});
  if (advanced.toLongLong() != 8) {
    qCritical(
        "Plugin service routing failed for video_editor.timeline_advance");
    return 12;
  }

  const QVariant recorderState =
      imgsli::app::PluginRegistry::instance().callService(
          QStringLiteral("video_editor.recorder_state"), {});
  if (recorderState.toString() != QStringLiteral("idle")) {
    qCritical("Recorder default state is not idle");
    return 22;
  }
  const QVariant recorderCount =
      imgsli::app::PluginRegistry::instance().callService(
          QStringLiteral("video_editor.recorder_snapshot_count"), {});
  if (recorderCount.toInt() != 0) {
    qCritical("Recorder snapshot count is not zero by default");
    return 23;
  }
  const QVariant recorderFps =
      imgsli::app::PluginRegistry::instance().callService(
          QStringLiteral("video_editor.recorder_set_fps"),
          {{QStringLiteral("fps"), 30}});
  if (recorderFps.toInt() != 30) {
    qCritical("Recorder set_fps did not echo 30");
    return 24;
  }

  QTemporaryDir exportDir;
  const QString exportPath =
      exportDir.filePath(QStringLiteral("contract-export.png"));
  QImage exportProbe(8, 6, QImage::Format_RGBA8888);
  exportProbe.fill(QColor(12, 34, 56, 255));
  const QVariant exportSaved =
      imgsli::app::PluginRegistry::instance().callService(
          QStringLiteral("export.save_image"),
          {{QStringLiteral("path"), exportPath},
           {QStringLiteral("image"), exportProbe},
           {QStringLiteral("format"), QStringLiteral("PNG")}});
  if (!exportSaved.toBool() || !QFileInfo::exists(exportPath)) {
    qCritical("Plugin service execution failed for export.save_image");
    return 13;
  }

  QImage analysisLeft(8, 8, QImage::Format_RGBA8888);
  QImage analysisRight(8, 8, QImage::Format_RGBA8888);
  analysisLeft.fill(QColor(0, 0, 0, 255));
  analysisRight.fill(QColor(255, 255, 255, 255));
  const QVariantMap metricProbe =
      imgsli::app::PluginRegistry::instance()
          .callService(QStringLiteral("analysis.metrics"),
                       {{QStringLiteral("left"), analysisLeft},
                        {QStringLiteral("right"), analysisRight}})
          .toMap();
  const QImage diffProbe =
      imgsli::app::PluginRegistry::instance()
          .callService(QStringLiteral("analysis.diff"),
                       {{QStringLiteral("left"), analysisLeft},
                        {QStringLiteral("right"), analysisRight},
                        {QStringLiteral("mode"), QStringLiteral("highlight")},
                        {QStringLiteral("channel"), QStringLiteral("RGB")}})
          .value<QImage>();
  if (!metricProbe.contains(QStringLiteral("psnr")) ||
      metricProbe.value(QStringLiteral("ssim")).toDouble() >= 0.01 ||
      diffProbe.size() != QSize(8, 8)) {
    qCritical("Analysis plugin metrics/diff contract failed");
    return 24;
  }

  canvas->registerImage(501, analysisLeft);
  canvas->registerImage(502, analysisRight);
  canvas->setRenderPlan({
      .texture1Id = 501,
      .texture2Id = 502,
      .canvasWidth = 8,
      .canvasHeight = 8,
      .split = 0.5F,
      .dividerEnabled = true,
  });
  QObject *offscreenRenderer =
      imgsli::app::PluginRegistry::instance()
          .callService(QStringLiteral("offscreen_renderer.instance"), {})
          .value<QObject *>();
  QObject *sameOffscreenRenderer =
      imgsli::app::PluginRegistry::instance()
          .callService(QStringLiteral("offscreen_renderer.instance"), {})
          .value<QObject *>();
  const auto *offscreenPlugin = imgsli::app::PluginRegistry::instance().find(
      QStringLiteral("offscreen_renderer"));
  const QStringList offscreenCommands =
      offscreenPlugin == nullptr ? QStringList{}
                                  : offscreenPlugin->definition().commandIds;
  if (offscreenRenderer == nullptr ||
      sameOffscreenRenderer != offscreenRenderer ||
      !offscreenCommands.contains(
          QStringLiteral("offscreen_renderer.render_canvas")) ||
      !offscreenCommands.contains(
          QStringLiteral("offscreen_renderer.render_plan")) ||
      !offscreenCommands.contains(
          QStringLiteral("offscreen_renderer.render_batch")) ||
      !offscreenCommands.contains(
          QStringLiteral("offscreen_renderer.cache_size")) ||
      !offscreenCommands.contains(
          QStringLiteral("offscreen_renderer.cache_clear")) ||
      !imgsli::app::PluginRegistry::instance()
           .callService(QStringLiteral("offscreen_renderer.cache_clear"), {})
           .toBool() ||
      imgsli::app::PluginRegistry::instance()
              .callService(QStringLiteral("offscreen_renderer.cache_size"), {})
              .toInt() != 0) {
    qCritical("Shared offscreen renderer contract failed");
    return 31;
  }
  if (qEnvironmentVariable("IMGSLI_RHI_BACKEND") != QStringLiteral("null")) {
    const QVariantMap renderArgs{
        {QStringLiteral("canvas"), QVariant::fromValue<QObject *>(canvas)},
        {QStringLiteral("width"), 8},
        {QStringLiteral("height"), 8},
    };
    const QImage firstCachedRender =
        imgsli::app::PluginRegistry::instance()
            .callService(QStringLiteral("offscreen_renderer.render_canvas"),
                         renderArgs)
            .value<QImage>();
    const QImage secondCachedRender =
        imgsli::app::PluginRegistry::instance()
            .callService(QStringLiteral("offscreen_renderer.render_canvas"),
                         renderArgs)
            .value<QImage>();
    const int cacheSize =
        imgsli::app::PluginRegistry::instance()
            .callService(QStringLiteral("offscreen_renderer.cache_size"), {})
            .toInt();
    if (firstCachedRender.size() != QSize(8, 8) ||
        secondCachedRender != firstCachedRender || cacheSize != 1) {
      qCritical("Shared offscreen renderer cache contract failed");
      return 36;
    }
  }

  auto *exportTab =
      imgsli::app::TabRegistry::instance().find(QStringLiteral("export"));
  exportTab->bindServices(
      {{QStringLiteral("canvas"), QVariant::fromValue<QObject *>(canvas)}});
  QWidget *exportPage = exportTab->createPage(central);
  const bool exportUiReady =
      exportPage->findChild<QWidget *>(QStringLiteral("exportPath")) !=
          nullptr &&
      exportPage->findChild<QWidget *>(QStringLiteral("exportFormat")) !=
          nullptr &&
      exportPage->findChild<QWidget *>(QStringLiteral("exportSave")) != nullptr;
  delete exportPage;
  if (!exportUiReady) {
    qCritical("Export tab did not create its required controls");
    return 14;
  }

  imgsli::app::ComparisonController comparisonCheck(nullptr, canvas);
  imgsli::app::AnalysisController analysisCheck(nullptr, &comparisonCheck);
  auto *multiCompareTab = imgsli::app::TabRegistry::instance().find(
      QStringLiteral("multi_compare"));
  multiCompareTab->bindServices(
      {{QStringLiteral("comparisonController"),
        QVariant::fromValue<QObject *>(&comparisonCheck)},
       {QStringLiteral("analysisController"),
        QVariant::fromValue<QObject *>(&analysisCheck)}});
  QWidget *multiComparePage = multiCompareTab->createPage(central);
  auto *multiCompareSplit = multiComparePage->findChild<QSlider *>(
      QStringLiteral("multiCompareSplit"));
  const bool multiCompareUiReady =
      multiComparePage->findChild<QWidget *>(
          QStringLiteral("multiCompareOpen")) != nullptr &&
      multiCompareSplit != nullptr &&
      multiComparePage->findChild<QWidget *>(
          QStringLiteral("multiCompareMagnifier")) != nullptr;
  QEventLoop comparisonLoadLoop;
  bool comparisonReady = false;
  QObject::connect(
      &comparisonCheck,
      &imgsli::app::ComparisonController::comparisonChanged,
      &comparisonLoadLoop, [&comparisonLoadLoop, &comparisonReady]() {
        comparisonReady = true;
        comparisonLoadLoop.quit();
      });
  if (!multiCompareUiReady ||
      !comparisonCheck.openPair(exportPath, exportPath)) {
    delete multiComparePage;
    qCritical("Multi Compare tab did not create a working control surface");
    return 16;
  }
  QTimer::singleShot(5000, &comparisonLoadLoop, &QEventLoop::quit);
  comparisonLoadLoop.exec();
  if (!comparisonReady) {
    delete multiComparePage;
    qCritical("Multi Compare async image loading timed out");
    return 48;
  }
  multiCompareSplit->setValue(250);
  const bool splitApplied = qAbs(canvas->renderPlan().split - 0.25F) <= 0.0001F;
  delete multiComparePage;
  if (!splitApplied) {
    qCritical("Multi Compare split control did not reach the canvas");
    return 17;
  }

  imgsli::app::VideoEditorController videoCheck;
  auto *videoTab = imgsli::app::TabRegistry::instance().find(
      QStringLiteral("video_editor"));
  videoTab->bindServices(
      {{QStringLiteral("videoEditorController"),
        QVariant::fromValue<QObject *>(&videoCheck)}});
  QWidget *videoPage = videoTab->createPage(central);
  auto *videoWidth = videoPage->findChild<sli::toolkit::SpinBox *>(
      QStringLiteral("videoWidth"));
  auto *videoTimeline =
      videoPage->findChild<QSlider *>(QStringLiteral("videoTimeline"));
  const bool videoUiReady =
      videoWidth != nullptr && videoTimeline != nullptr &&
      videoPage->findChild<QWidget *>(QStringLiteral("videoStartExport")) !=
          nullptr &&
      videoPage->findChild<QWidget *>(QStringLiteral("videoExportProgress")) !=
          nullptr &&
      videoPage->findChild<QWidget *>(
          QStringLiteral("videoKeyframe_magnifier")) != nullptr;
  const int videoSectionCount =
      videoPage
          ->findChildren<QWidget *>(QStringLiteral("sliSectionHeader"),
                                     Qt::FindChildrenRecursively)
          .size();
  const int videoDividerCount =
      videoPage
          ->findChildren<QWidget *>(QStringLiteral("sliDivider"),
                                     Qt::FindChildrenRecursively)
          .size();
  if (!videoUiReady) {
    delete videoPage;
    qCritical("Video Editor tab did not create its required controls");
    return 18;
  }
  if (videoSectionCount < 5 || videoDividerCount < 4) {
    delete videoPage;
    qCritical("Video Editor did not use toolkit section primitives");
    return 37;
  }
  videoWidth->setValue(1280);
  videoTimeline->setValue(42);
  videoCheck.setKeyframeFeatureEnabled(QStringLiteral("magnifier"), false);
  videoCheck.setSelection(90, 30);
  const QJsonObject videoProject =
      QJsonDocument::fromJson(videoCheck.projectJson().toUtf8()).object();
  const QStringList videoArgs =
      imgsli::app::PluginRegistry::instance()
          .callService(
              QStringLiteral("video_editor.export_arguments"),
              {{QStringLiteral("input"), QStringLiteral("in.mp4")},
               {QStringLiteral("output"), QStringLiteral("out.mp4")},
               {QStringLiteral("project"), videoCheck.projectJson()}})
          .toStringList();
  delete videoPage;
  if (videoProject.value(QStringLiteral("width")).toInt() != 1280 ||
      videoCheck.timelinePosition() != 42 ||
      videoCheck.selectionStart() != 30 || videoCheck.selectionEnd() != 90 ||
      videoCheck.keyframeFeatureEnabled(QStringLiteral("magnifier")) ||
      !videoArgs.contains(QStringLiteral("scale=1280:720")) ||
      !videoArgs.contains(QStringLiteral("-progress"))) {
    qCritical("Video Editor controller/plugin roundtrip failed");
    return 19;
  }

  imgsli::app::CanvasRenderPlan baselinePlan;
  baselinePlan.split = 0.2F;
  baselinePlan.magnifierX = 0.1F;
  baselinePlan.guidesEnabled = false;
  imgsli::app::CanvasRenderPlan beforePlan = baselinePlan;
  imgsli::app::CanvasRenderPlan afterPlan = baselinePlan;
  afterPlan.split = 0.8F;
  afterPlan.magnifierX = 0.9F;
  afterPlan.guidesEnabled = true;
  const imgsli::app::CanvasRenderPlan policyProbe =
      imgsli::app::interpolateVideoPlan(
          beforePlan, afterPlan, baselinePlan,
          QJsonObject{
              {QStringLiteral("split"), true},
              {QStringLiteral("magnifier"), false},
              {QStringLiteral("guides"), false},
          },
          0.5);
  if (qAbs(policyProbe.split - 0.5F) > 0.0001F ||
      qAbs(policyProbe.magnifierX - baselinePlan.magnifierX) > 0.0001F ||
      policyProbe.guidesEnabled != baselinePlan.guidesEnabled) {
    qCritical("Video keyframe feature policy interpolation failed");
    return 35;
  }

  const int helpSections =
      imgsli::app::PluginRegistry::instance()
          .callService(QStringLiteral("help.section_count"),
                       {{QStringLiteral("language"), QStringLiteral("en")},
                        {QStringLiteral("parent"),
                         QVariant::fromValue<QObject *>(central)}})
          .toInt();
  if (helpSections < 8) {
    qCritical("Help plugin did not load the markdown section set");
    return 22;
  }

  QWidget beginnerOnly;
  QWidget expertOnly;
  const QVariant layoutBound =
      imgsli::app::PluginRegistry::instance().callService(
          QStringLiteral("layout.bind_controls"),
          {{QStringLiteral("controls"),
            QVariantMap{{QStringLiteral("open"),
                          QVariant::fromValue<QObject *>(&beginnerOnly)},
                         {QStringLiteral("state"),
                          QVariant::fromValue<QObject *>(&expertOnly)}}},
           {QStringLiteral("mode"), QStringLiteral("beginner")}});
  imgsli::app::PluginRegistry::instance().callService(
      QStringLiteral("layout.apply_mode"),
      {{QStringLiteral("mode"), QStringLiteral("expert")}});
  if (layoutBound.toInt() != 2 || beginnerOnly.isHidden() ||
      expertOnly.isHidden()) {
    qCritical("Layout plugin bind/apply contract failed");
    return 23;
  }
  imgsli::app::PluginRegistry::instance().deactivateAll();

  canvas->setRenderPlan({
      .texture1Id = 1,
      .texture2Id = 2,
      .dividerEnabled = true,
      .magnifierEnabled = true,
      .guidesEnabled = true,
  });
  if (!canvas->executeFeatureCommand(QStringLiteral("divider"),
                                     QStringLiteral("set_split"), 0.25F) ||
      qAbs(canvas->renderPlan().split - 0.25F) > 0.0001F) {
    qCritical("Divider feature command roundtrip failed");
    return 5;
  }
  qInfo("Phase 3 contracts registered: %lld passes, %lld features",
        static_cast<long long>(passNames.size()),
        static_cast<long long>(featureNames.size()));
  return 0;
}

}  // namespace imgsli::app::cli

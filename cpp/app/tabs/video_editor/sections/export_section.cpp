#include <QFileDialog>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPair>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QSignalBlocker>
#include <QString>
#include <QVBoxLayout>
#include <QVariantMap>
#include <QWidget>

#include <algorithm>

#include "core/plugin_registry.h"
#include "plugins/video_editor/controller.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/atomic/section_header.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "tabs/video_editor/sections/sections.h"

namespace imgsli::app::video_editor_sections {

namespace {

void syncProjectFields(const QString& json, PageContext& ctx) {
  const QJsonObject project = QJsonDocument::fromJson(json.toUtf8()).object();
  const QSignalBlocker b1(ctx.width);
  const QSignalBlocker b2(ctx.height);
  const QSignalBlocker b3(ctx.fps);
  const QSignalBlocker b4(ctx.aspectLock);
  const QSignalBlocker b5(ctx.container);
  const QSignalBlocker b6(ctx.codec);
  const QSignalBlocker b7(ctx.qualityMode);
  const QSignalBlocker b8(ctx.crf);
  const QSignalBlocker b9(ctx.bitrate);
  const QSignalBlocker b10(ctx.preset);
  ctx.width->setValue(project.value(QStringLiteral("width")).toInt(1920));
  ctx.height->setValue(project.value(QStringLiteral("height")).toInt(1080));
  ctx.fps->setValue(project.value(QStringLiteral("fps")).toInt(60));
  ctx.aspectLock->setChecked(
      project.value(QStringLiteral("aspect_ratio_locked")).toBool(true));
  ctx.container->setCurrentText(
      project.value(QStringLiteral("container")).toString());
  ctx.codec->setCurrentText(project.value(QStringLiteral("codec")).toString());
  ctx.qualityMode->setCurrentText(
      project.value(QStringLiteral("quality_mode")).toString());
  ctx.crf->setValue(project.value(QStringLiteral("crf")).toInt(23));
  ctx.bitrate->setText(project.value(QStringLiteral("bitrate")).toString());
  ctx.preset->setCurrentText(project.value(QStringLiteral("preset")).toString());
}

void syncKeyframeControls(const QString& json, PageContext& ctx) {
  const QJsonObject features = QJsonDocument::fromJson(json.toUtf8())
                                    .object()
                                    .value(QStringLiteral("keyframe_features"))
                                    .toObject();
  for (const auto& [featureId, control] : ctx.keyframeControls) {
    const QSignalBlocker blocker(control);
    control->setChecked(features.value(featureId).toBool(true));
  }
}

}  // namespace

void buildExportSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;
  VideoEditorController* controller = ctx.controller;

  layout->addWidget(new sli::toolkit::SectionHeader(
      tr(QStringLiteral("video_editor.section_export")),
      tr(QStringLiteral("video_editor.section_export_description")), root));
  auto* exportForm = new QFormLayout();
  ctx.input = new QLineEdit(root);
  ctx.input->setObjectName(QStringLiteral("videoInput"));
  auto* output = new QLineEdit(root);
  output->setObjectName(QStringLiteral("videoOutput"));
  exportForm->addRow(tr(QStringLiteral("video_editor.input")), ctx.input);
  exportForm->addRow(tr(QStringLiteral("video_editor.output")), output);
  layout->addLayout(exportForm);

  auto* exportButtons = new QWidget(root);
  auto* exportButtonsLayout = new QHBoxLayout(exportButtons);
  exportButtonsLayout->setContentsMargins(0, 0, 0, 0);
  auto* browseInput = makeButton(root,
                                   QStringLiteral("video_editor.browse_input"),
                                   QStringLiteral("videoBrowseInput"));
  auto* browseOutput =
      makeButton(root, QStringLiteral("video_editor.browse_output"),
                  QStringLiteral("videoBrowseOutput"));
  auto* startExport =
      makeButton(root, QStringLiteral("video_editor.start_export"),
                  QStringLiteral("videoStartExport"));
  auto* cancelExport =
      makeButton(root, QStringLiteral("video_editor.cancel_export"),
                  QStringLiteral("videoCancelExport"));
  cancelExport->setEnabled(false);
  auto* exportRecording =
      makeButton(root, QStringLiteral("video_editor.export_recording"),
                  QStringLiteral("videoExportRecording"));
  exportButtonsLayout->addWidget(browseInput);
  exportButtonsLayout->addWidget(browseOutput);
  exportButtonsLayout->addWidget(startExport);
  exportButtonsLayout->addWidget(cancelExport);
  exportButtonsLayout->addWidget(exportRecording);
  layout->addWidget(exportButtons);

  auto* progress = new QProgressBar(root);
  progress->setObjectName(QStringLiteral("videoExportProgress"));
  progress->setRange(0, 100);
  auto* status = new QLabel(root);
  status->setObjectName(QStringLiteral("videoExportStatus"));
  auto* log = new QPlainTextEdit(root);
  log->setObjectName(QStringLiteral("videoExportLog"));
  log->setReadOnly(true);
  log->setMaximumBlockCount(500);
  layout->addWidget(progress);
  layout->addWidget(status);
  layout->addWidget(log, 1);

  if (controller == nullptr) {
    status->setText(
        tr(QStringLiteral("video_editor.controller_unavailable")));
    root->setEnabled(false);
    return;
  }

  syncProjectFields(controller->projectJson(), ctx);
  syncKeyframeControls(controller->projectJson(), ctx);

  QObject::connect(ctx.width, &sli::toolkit::SpinBox::valueChanged, controller,
                    &VideoEditorController::setWidth);
  QObject::connect(ctx.height, &sli::toolkit::SpinBox::valueChanged, controller,
                    &VideoEditorController::setHeight);
  QObject::connect(ctx.fps, &sli::toolkit::SpinBox::valueChanged, controller,
                    &VideoEditorController::setFps);
  QObject::connect(ctx.aspectLock, &sli::toolkit::Button::toggled, controller,
                    &VideoEditorController::setAspectRatioLocked);
  QObject::connect(ctx.container, &sli::toolkit::ComboBox::currentTextChanged,
                    controller, &VideoEditorController::setContainer);
  QObject::connect(ctx.codec, &sli::toolkit::ComboBox::currentTextChanged,
                    controller, &VideoEditorController::setCodec);
  QObject::connect(ctx.qualityMode,
                    &sli::toolkit::ComboBox::currentTextChanged, controller,
                    &VideoEditorController::setQualityMode);
  QObject::connect(ctx.crf, &sli::toolkit::SpinBox::valueChanged, controller,
                    &VideoEditorController::setCrf);
  QObject::connect(ctx.bitrate, &QLineEdit::textChanged, controller,
                    &VideoEditorController::setBitrate);
  QObject::connect(ctx.preset, &sli::toolkit::ComboBox::currentTextChanged,
                    controller, &VideoEditorController::setPreset);
  for (const auto& [featureId, control] : ctx.keyframeControls) {
    QObject::connect(control, &sli::toolkit::CheckBox::toggled, controller,
                      [controller, featureId](bool enabled) {
                        controller->setKeyframeFeatureEnabled(featureId,
                                                                enabled);
                      });
  }
  // Capture every widget pointer by value — `ctx` itself lives on the
  // stack of the caller's createPage and would dangle once the
  // connection outlives it.
  auto* widthCap = ctx.width;
  auto* heightCap = ctx.height;
  auto* fpsCap = ctx.fps;
  auto* aspectLockCap = ctx.aspectLock;
  auto* containerCap = ctx.container;
  auto* codecCap = ctx.codec;
  auto* qualityModeCap = ctx.qualityMode;
  auto* crfCap = ctx.crf;
  auto* bitrateCap = ctx.bitrate;
  auto* presetCap = ctx.preset;
  auto keyframeCap = ctx.keyframeControls;
  QObject::connect(
      controller, &VideoEditorController::projectChanged, root,
      [widthCap, heightCap, fpsCap, aspectLockCap, containerCap, codecCap,
       qualityModeCap, crfCap, bitrateCap, presetCap, keyframeCap](
          const QString& json) {
        const QJsonObject project =
            QJsonDocument::fromJson(json.toUtf8()).object();
        const QSignalBlocker b1(widthCap);
        const QSignalBlocker b2(heightCap);
        const QSignalBlocker b3(fpsCap);
        const QSignalBlocker b4(aspectLockCap);
        const QSignalBlocker b5(containerCap);
        const QSignalBlocker b6(codecCap);
        const QSignalBlocker b7(qualityModeCap);
        const QSignalBlocker b8(crfCap);
        const QSignalBlocker b9(bitrateCap);
        const QSignalBlocker b10(presetCap);
        widthCap->setValue(project.value(QStringLiteral("width")).toInt(1920));
        heightCap->setValue(project.value(QStringLiteral("height")).toInt(1080));
        fpsCap->setValue(project.value(QStringLiteral("fps")).toInt(60));
        aspectLockCap->setChecked(
            project.value(QStringLiteral("aspect_ratio_locked")).toBool(true));
        containerCap->setCurrentText(
            project.value(QStringLiteral("container")).toString());
        codecCap->setCurrentText(
            project.value(QStringLiteral("codec")).toString());
        qualityModeCap->setCurrentText(
            project.value(QStringLiteral("quality_mode")).toString());
        crfCap->setValue(project.value(QStringLiteral("crf")).toInt(23));
        bitrateCap->setText(
            project.value(QStringLiteral("bitrate")).toString());
        presetCap->setCurrentText(
            project.value(QStringLiteral("preset")).toString());
        const QJsonObject features =
            project.value(QStringLiteral("keyframe_features")).toObject();
        for (const auto& [featureId, control] : keyframeCap) {
          const QSignalBlocker blocker(control);
          control->setChecked(features.value(featureId).toBool(true));
        }
      });

  QLineEdit* input = ctx.input;
  QObject::connect(browseInput, &sli::toolkit::Button::clicked, root,
                    [root, input]() {
                      const QString path = QFileDialog::getOpenFileName(
                          root,
                          tr(QStringLiteral("video_editor.select_input")), {},
                          QStringLiteral("Video files (*.*)"));
                      if (!path.isEmpty()) {
                        input->setText(path);
                      }
                    });
  QObject::connect(browseOutput, &sli::toolkit::Button::clicked, root,
                    [root, output]() {
                      const QString path = QFileDialog::getSaveFileName(
                          root,
                          tr(QStringLiteral("video_editor.select_output")), {},
                          QStringLiteral("Video files (*.*)"));
                      if (!path.isEmpty()) {
                        output->setText(path);
                      }
                    });
  sli::toolkit::SpinBox* fps = ctx.fps;
  QObject::connect(
      startExport, &sli::toolkit::Button::clicked, controller,
      [controller, fps, output, status, input]() {
        double startSeconds = -1.0;
        double durationSeconds = -1.0;
        if (controller->hasSelection()) {
          const int projectFps = std::max(1, fps->value());
          startSeconds = controller->selectionStart() /
                          static_cast<double>(projectFps);
          durationSeconds =
              (controller->selectionEnd() - controller->selectionStart() + 1) /
              static_cast<double>(projectFps);
        }
        if (!controller->startExport(input->text(), output->text(),
                                       startSeconds, durationSeconds)) {
          status->setText(
              tr(QStringLiteral("video_editor.start_failed")));
        }
      });
  QObject::connect(cancelExport, &sli::toolkit::Button::clicked, controller,
                    &VideoEditorController::cancelExport);
  QObject::connect(
      exportRecording, &sli::toolkit::Button::clicked, controller,
      [controller, output, status]() {
        const QString path = output->text();
        if (path.isEmpty()) {
          status->setText(
              tr(QStringLiteral("video_editor.recording_no_output")));
          return;
        }
        const QVariantMap result =
            PluginRegistry::instance()
                .callService(
                    QStringLiteral("video_editor.export_recording"),
                    {{QStringLiteral("output"), path},
                      {QStringLiteral("project"), controller->projectJson()}})
                .toMap();
        if (result.value(QStringLiteral("ok")).toBool()) {
          status->setText(
              tr(QStringLiteral("video_editor.recording_exported"))
                  .arg(result.value(QStringLiteral("frames_written")).toInt())
                  .arg(path));
        } else {
          status->setText(
              tr(QStringLiteral("video_editor.recording_export_failed"))
                  .arg(result.value(QStringLiteral("error")).toString()));
        }
      });
  QObject::connect(controller, &VideoEditorController::exportStarted, root,
                    [progress, startExport, cancelExport, status]() {
                      progress->setValue(0);
                      startExport->setEnabled(false);
                      cancelExport->setEnabled(true);
                      status->setText(
                          tr(QStringLiteral("video_editor.exporting")));
                    });
  QObject::connect(controller, &VideoEditorController::exportProgress, progress,
                    &QProgressBar::setValue);
  QObject::connect(controller, &VideoEditorController::exportLog, log,
                    &QPlainTextEdit::appendPlainText);
  QObject::connect(controller, &VideoEditorController::exportFinished, root,
                    [startExport, cancelExport, status](
                        bool ok, const QString& message) {
                      startExport->setEnabled(true);
                      cancelExport->setEnabled(false);
                      status->setText(
                          ok
                              ? tr(QStringLiteral("video_editor.export_done"))
                              : message);
                    });
}

}  // namespace imgsli::app::video_editor_sections

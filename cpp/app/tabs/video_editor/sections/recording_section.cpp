#include <QFormLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QString>
#include <QVBoxLayout>
#include <QVariantMap>
#include <QWidget>

#include "core/plugin_registry.h"
#include "plugins/video_editor/services/recorder.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/atomic/divider.h"
#include "sli/toolkit/atomic/section_header.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "tabs/video_editor/sections/sections.h"

namespace imgsli::app::video_editor_sections {

void buildRecordingSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;

  layout->addWidget(new sli::toolkit::SectionHeader(
      tr(QStringLiteral("video_editor.section_recording")),
      tr(QStringLiteral("video_editor.section_recording_description")), root));
  auto* recordingForm = new QFormLayout();
  auto* recordingRow = new QWidget(root);
  auto* recordingRowLayout = new QHBoxLayout(recordingRow);
  recordingRowLayout->setContentsMargins(0, 0, 0, 0);
  auto* recordStart = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.record_start")),
      sli::toolkit::Button::Variant::Default, root);
  recordStart->setObjectName(QStringLiteral("videoRecordStart"));
  auto* recordPause = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.record_pause")),
      sli::toolkit::Button::Variant::Surface, root);
  recordPause->setObjectName(QStringLiteral("videoRecordPause"));
  recordPause->setEnabled(false);
  auto* recordStop = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.record_stop")),
      sli::toolkit::Button::Variant::Surface, root);
  recordStop->setObjectName(QStringLiteral("videoRecordStop"));
  recordStop->setEnabled(false);
  auto* recordClear = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.record_clear")),
      sli::toolkit::Button::Variant::Surface, root);
  recordClear->setObjectName(QStringLiteral("videoRecordClear"));
  recordingRowLayout->addWidget(recordStart);
  recordingRowLayout->addWidget(recordPause);
  recordingRowLayout->addWidget(recordStop);
  recordingRowLayout->addWidget(recordClear);
  auto* recordFps = makeSpin(root, QStringLiteral("videoRecordFps"), 1, 144, 60);
  recordingForm->addRow(QString(), recordingRow);
  recordingForm->addRow(tr(QStringLiteral("video_editor.record_fps")),
                         recordFps);
  auto* recordStatus = new QLabel(root);
  recordStatus->setObjectName(QStringLiteral("videoRecordStatus"));
  recordStatus->setText(tr(QStringLiteral("video_editor.record_status_idle"))
                              .arg(0)
                              .arg(0.0, 0, 'f', 2));
  recordingForm->addRow(QString(), recordStatus);
  layout->addLayout(recordingForm);
  layout->addWidget(new sli::toolkit::Divider(Qt::Horizontal, root));

  auto& plugins = PluginRegistry::instance();
  auto* recorder = qobject_cast<VideoRecorder*>(
      plugins.callService(QStringLiteral("video_editor.recorder_object"), {})
          .value<QObject*>());
  ctx.recorder = recorder;
  if (recorder == nullptr) {
    recordStart->setEnabled(false);
    recordPause->setEnabled(false);
    recordStop->setEnabled(false);
    recordClear->setEnabled(false);
    return;
  }

  const auto refreshStatus = [recordStatus, recorder]() {
    const double seconds = recorder->durationMs() / 1000.0;
    const QString key =
        recorder->state() == VideoRecorder::State::Recording
            ? QStringLiteral("video_editor.record_status_recording")
            : recorder->state() == VideoRecorder::State::Paused
                  ? QStringLiteral("video_editor.record_status_paused")
                  : QStringLiteral("video_editor.record_status_idle");
    recordStatus->setText(
        tr(key).arg(recorder->snapshotCount()).arg(seconds, 0, 'f', 2));
  };
  QObject::connect(recorder, &VideoRecorder::snapshotCaptured, root,
                    [refreshStatus](int) { refreshStatus(); });
  QObject::connect(recorder, &VideoRecorder::cleared, root, refreshStatus);
  QObject::connect(
      recorder, &VideoRecorder::stateChanged, root,
      [recordStart, recordPause, recordStop, refreshStatus](
          VideoRecorder::State state) {
        recordStart->setEnabled(state == VideoRecorder::State::Idle);
        recordPause->setEnabled(state == VideoRecorder::State::Recording ||
                                state == VideoRecorder::State::Paused);
        recordStop->setEnabled(state != VideoRecorder::State::Idle);
        refreshStatus();
      });
  QObject::connect(recordStart, &sli::toolkit::Button::clicked, root, []() {
    PluginRegistry::instance().callService(
        QStringLiteral("video_editor.recorder_start"), {});
  });
  QObject::connect(recordPause, &sli::toolkit::Button::clicked, root,
                    [recorder]() {
                      if (recorder->state() == VideoRecorder::State::Recording) {
                        PluginRegistry::instance().callService(
                            QStringLiteral("video_editor.recorder_pause"), {});
                      } else {
                        PluginRegistry::instance().callService(
                            QStringLiteral("video_editor.recorder_resume"), {});
                      }
                    });
  QObject::connect(recordStop, &sli::toolkit::Button::clicked, root, []() {
    PluginRegistry::instance().callService(
        QStringLiteral("video_editor.recorder_stop"), {});
  });
  QObject::connect(recordClear, &sli::toolkit::Button::clicked, root, []() {
    PluginRegistry::instance().callService(
        QStringLiteral("video_editor.recorder_clear"), {});
  });
  QObject::connect(recordFps,
                    qOverload<int>(&sli::toolkit::SpinBox::valueChanged), root,
                    [](int value) {
                      PluginRegistry::instance().callService(
                          QStringLiteral("video_editor.recorder_set_fps"),
                          {{QStringLiteral("fps"), value}});
                    });
}

}  // namespace imgsli::app::video_editor_sections

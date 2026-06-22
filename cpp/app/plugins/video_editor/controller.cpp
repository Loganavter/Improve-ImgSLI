#include "plugins/video_editor/controller.h"

#include <QJsonDocument>
#include <QProcess>
#include <QVariantMap>

#include <algorithm>

#include "core/plugin_registry.h"

namespace imgsli::app {

VideoEditorController::VideoEditorController(QObject* parent)
    : QObject(parent) {
  const QString defaults =
      PluginRegistry::instance()
          .callService(QStringLiteral("video_editor.project_default"), {})
          .toString();
  project_ = QJsonDocument::fromJson(defaults.toUtf8()).object();
}

QString VideoEditorController::projectJson() const {
  return QString::fromUtf8(
      QJsonDocument(project_).toJson(QJsonDocument::Compact));
}

bool VideoEditorController::exporting() const {
  return process_ != nullptr &&
         process_->state() != QProcess::NotRunning;
}

bool VideoEditorController::keyframeFeatureEnabled(
    const QString& featureId) const {
  return project_.value(QStringLiteral("keyframe_features"))
      .toObject()
      .value(featureId)
      .toBool(true);
}

void VideoEditorController::setResolution(int width, int height) {
  project_.insert(QStringLiteral("width"), std::max(2, width));
  project_.insert(QStringLiteral("height"), std::max(2, height));
  if (!project_.value(QStringLiteral("aspect_ratio_locked")).toBool() &&
      height > 0) {
    project_.insert(QStringLiteral("original_ratio"),
                    static_cast<double>(width) / height);
  }
  emitProject();
}

void VideoEditorController::setWidth(int width) {
  width = std::max(2, width);
  int height = project_.value(QStringLiteral("height")).toInt(1080);
  project_.insert(QStringLiteral("width"), width);
  if (project_.value(QStringLiteral("aspect_ratio_locked")).toBool()) {
    height = PluginRegistry::instance()
                 .callService(
                     QStringLiteral("video_editor.project_adjust_height"),
                     {{QStringLiteral("project"), projectJson()},
                      {QStringLiteral("width"), width}})
                 .toInt();
    project_.insert(QStringLiteral("height"), std::max(2, height));
  }
  emitProject();
}

void VideoEditorController::setHeight(int height) {
  height = std::max(2, height);
  int width = project_.value(QStringLiteral("width")).toInt(1920);
  project_.insert(QStringLiteral("height"), height);
  if (project_.value(QStringLiteral("aspect_ratio_locked")).toBool()) {
    width = PluginRegistry::instance()
                .callService(
                    QStringLiteral("video_editor.project_adjust_width"),
                    {{QStringLiteral("project"), projectJson()},
                     {QStringLiteral("height"), height}})
                .toInt();
    project_.insert(QStringLiteral("width"), std::max(2, width));
  }
  emitProject();
}

void VideoEditorController::setFps(int fps) {
  project_.insert(QStringLiteral("fps"), std::clamp(fps, 1, 240));
  emitProject();
}

void VideoEditorController::setAspectRatioLocked(bool locked) {
  project_.insert(QStringLiteral("aspect_ratio_locked"), locked);
  if (!locked) {
    const int width = project_.value(QStringLiteral("width")).toInt(1920);
    const int height = project_.value(QStringLiteral("height")).toInt(1080);
    project_.insert(QStringLiteral("original_ratio"),
                    static_cast<double>(width) / std::max(1, height));
  }
  emitProject();
}

#define IMGSLI_PROJECT_STRING_SETTER(Method, Key)             \
  void VideoEditorController::Method(const QString& value) {  \
    project_.insert(QStringLiteral(Key), value);               \
    emitProject();                                             \
  }

IMGSLI_PROJECT_STRING_SETTER(setContainer, "container")
IMGSLI_PROJECT_STRING_SETTER(setCodec, "codec")
IMGSLI_PROJECT_STRING_SETTER(setQualityMode, "quality_mode")
IMGSLI_PROJECT_STRING_SETTER(setBitrate, "bitrate")
IMGSLI_PROJECT_STRING_SETTER(setPreset, "preset")
IMGSLI_PROJECT_STRING_SETTER(setPixelFormat, "pix_fmt")
IMGSLI_PROJECT_STRING_SETTER(setManualArguments, "manual_args")

#undef IMGSLI_PROJECT_STRING_SETTER

void VideoEditorController::setCrf(int crf) {
  project_.insert(QStringLiteral("crf"), std::clamp(crf, 0, 51));
  emitProject();
}

void VideoEditorController::setManualMode(bool enabled) {
  project_.insert(QStringLiteral("manual_mode"), enabled);
  emitProject();
}

void VideoEditorController::setKeyframeFeatureEnabled(
    const QString& featureId, bool enabled) {
  static const QStringList kFeatureIds{
      QStringLiteral("split"),
      QStringLiteral("divider"),
      QStringLiteral("magnifier"),
      QStringLiteral("capture"),
      QStringLiteral("guides"),
      QStringLiteral("filename_overlay"),
      QStringLiteral("paste_overlay"),
  };
  if (!kFeatureIds.contains(featureId)) {
    return;
  }
  QJsonObject features =
      project_.value(QStringLiteral("keyframe_features")).toObject();
  features.insert(featureId, enabled);
  project_.insert(QStringLiteral("keyframe_features"), features);
  emitProject();
}

void VideoEditorController::seek(int frame) {
  timelinePosition_ = std::max(0, frame);
  emit timelineChanged(timelinePosition_);
}

void VideoEditorController::advance(int step) {
  timelinePosition_ =
      PluginRegistry::instance()
          .callService(QStringLiteral("video_editor.timeline_advance"),
                       {{QStringLiteral("position"), timelinePosition_},
                        {QStringLiteral("step"), step}})
          .toInt();
  emit timelineChanged(timelinePosition_);
}

void VideoEditorController::setSelection(int start, int end) {
  const QString json =
      PluginRegistry::instance()
          .callService(QStringLiteral("video_editor.selection_set"),
                       {{QStringLiteral("start"), start},
                        {QStringLiteral("end"), end}})
          .toString();
  const QJsonObject selection =
      QJsonDocument::fromJson(json.toUtf8()).object();
  selectionStart_ = selection.value(QStringLiteral("start")).toInt();
  selectionEnd_ = selection.value(QStringLiteral("end")).toInt();
  hasSelection_ = selection.contains(QStringLiteral("start"));
  emit selectionChanged(selectionStart_, selectionEnd_, hasSelection_);
}

void VideoEditorController::clearSelection() {
  PluginRegistry::instance().callService(
      QStringLiteral("video_editor.selection_set"), {});
  selectionStart_ = 0;
  selectionEnd_ = 0;
  hasSelection_ = false;
  emit selectionChanged(0, 0, false);
}

bool VideoEditorController::startExport(const QString& input,
                                        const QString& output,
                                        double startSeconds,
                                        double durationSeconds) {
  if (exporting() || input.isEmpty() || output.isEmpty()) {
    return false;
  }
  QVariantMap args{{QStringLiteral("input"), input},
                   {QStringLiteral("output"), output},
                   {QStringLiteral("project"), projectJson()},
                   {QStringLiteral("parent"),
                    QVariant::fromValue<QObject*>(this)}};
  if (startSeconds >= 0.0) {
    args.insert(QStringLiteral("start"), startSeconds);
  }
  if (durationSeconds > 0.0) {
    args.insert(QStringLiteral("duration"), durationSeconds);
  }
  auto* process = qobject_cast<QProcess*>(
      PluginRegistry::instance()
          .callService(QStringLiteral("video_editor.export_start"), args)
          .value<QObject*>());
  if (process == nullptr) {
    return false;
  }
  attachProcess(process, durationSeconds);
  emit exportStarted();
  return true;
}

void VideoEditorController::cancelExport() {
  if (process_ == nullptr) {
    return;
  }
  PluginRegistry::instance().callService(
      QStringLiteral("video_editor.export_cancel"),
      {{QStringLiteral("process"),
        QVariant::fromValue<QObject*>(process_)}});
}

void VideoEditorController::emitProject() {
  emit projectChanged(projectJson());
}

void VideoEditorController::attachProcess(QProcess* process,
                                          double expectedDuration) {
  process_ = process;
  progressBuffer_.clear();
  expectedDuration_ = std::max(0.0, expectedDuration);
  connect(process_, &QProcess::readyReadStandardOutput, this,
          &VideoEditorController::consumeProgressOutput);
  connect(process_, &QProcess::readyReadStandardError, this, [this]() {
    if (process_ != nullptr) {
      emit exportLog(
          QString::fromUtf8(process_->readAllStandardError()));
    }
  });
  connect(process_, &QProcess::errorOccurred, this,
          [this](QProcess::ProcessError error) {
            emit exportFinished(
                false, QStringLiteral("ffmpeg process error %1").arg(error));
          });
  connect(process_, qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
          this, [this](int exitCode, QProcess::ExitStatus status) {
            const bool ok =
                status == QProcess::NormalExit && exitCode == 0;
            emit exportProgress(ok ? 100 : 0);
            emit exportFinished(
                ok, ok ? QStringLiteral("Export complete")
                       : QStringLiteral("ffmpeg exited with code %1")
                             .arg(exitCode));
            process_ = nullptr;
          });
}

void VideoEditorController::consumeProgressOutput() {
  if (process_ == nullptr) {
    return;
  }
  progressBuffer_.append(process_->readAllStandardOutput());
  qsizetype newline = -1;
  while ((newline = progressBuffer_.indexOf('\n')) >= 0) {
    const QByteArray line = progressBuffer_.left(newline).trimmed();
    progressBuffer_.remove(0, newline + 1);
    if (!line.startsWith("out_time_ms=") || expectedDuration_ <= 0.0) {
      continue;
    }
    bool ok = false;
    const qint64 microseconds = line.mid(sizeof("out_time_ms=") - 1).toLongLong(&ok);
    if (ok) {
      const double seconds = microseconds / 1'000'000.0;
      emit exportProgress(
          std::clamp(qRound(seconds / expectedDuration_ * 100.0), 0, 99));
    }
  }
}

}  // namespace imgsli::app

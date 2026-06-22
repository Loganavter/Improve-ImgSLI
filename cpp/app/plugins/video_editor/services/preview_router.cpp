#include "plugins/video_editor/services/preview_router.h"

#include <QByteArray>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QString>
#include <QStringList>

#include <algorithm>

#include "core/plugin_registry.h"
#include "plugins/video_editor/services/export_router.h"
#include "plugins/video_editor/services/keyframe_policy.h"
#include "plugins/video_editor/services/plugin_state.h"
#include "plugins/video_editor/services/project_router.h"
#include "plugins/video_editor/services/recorder.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app::video_editor_services {

namespace {

QImage renderPlanOffscreen(PluginState& state, const CanvasRenderPlan& plan,
                            QSize target) {
  if (target.isEmpty() || state.recorderCanvas == nullptr) {
    return {};
  }
  return PluginRegistry::instance()
      .callService(
          QStringLiteral("offscreen_renderer.render_plan"),
          {{QStringLiteral("canvas"),
            QVariant::fromValue<QObject*>(state.recorderCanvas.data())},
           {QStringLiteral("plan"), QVariant::fromValue(plan)},
           {QStringLiteral("width"), target.width()},
           {QStringLiteral("height"), target.height()}})
      .value<QImage>();
}

QImage previewRenderFrame(PluginState& state, const QVariantMap& args) {
  const int frameIndex = args.value(QStringLiteral("frame_index")).toInt();
  const int width = args.value(QStringLiteral("width"), 0).toInt();
  const int height = args.value(QStringLiteral("height"), 0).toInt();
  if (width <= 0 || height <= 0) {
    return {};
  }
  VideoRecorder* rec = ensureRecorder(state);
  if (rec == nullptr) {
    return {};
  }
  const auto& snapshots = rec->snapshots();
  if (frameIndex < 0 || frameIndex >= snapshots.size()) {
    return {};
  }
  return renderPlanOffscreen(state, snapshots[frameIndex].plan,
                              QSize(width, height));
}

QImage previewRenderTimeMs(PluginState& state, const QVariantMap& args) {
  const qint64 timeMs = args.value(QStringLiteral("time_ms")).toLongLong();
  const int width = args.value(QStringLiteral("width"), 0).toInt();
  const int height = args.value(QStringLiteral("height"), 0).toInt();
  if (width <= 0 || height <= 0) {
    return {};
  }
  VideoRecorder* rec = ensureRecorder(state);
  if (rec == nullptr || rec->snapshotCount() == 0 ||
      state.recorderCanvas == nullptr) {
    return {};
  }
  const auto lookup = rec->lookupTimeMs(timeMs);
  if (lookup.indexBefore < 0) {
    return {};
  }
  const auto& snaps = rec->snapshots();
  const QJsonObject project =
      QJsonDocument::fromJson(
          args.value(QStringLiteral("project")).toString().toUtf8())
          .object();
  const QJsonObject policy =
      project.value(QStringLiteral("keyframe_features")).toObject();
  const CanvasRenderPlan plan = interpolateVideoPlan(
      snaps[lookup.indexBefore].plan, snaps[lookup.indexAfter].plan,
      snaps.first().plan, policy, lookup.t);
  return renderPlanOffscreen(state, plan, QSize(width, height));
}

QVariantMap exportRecording(PluginState& state, const QVariantMap& args) {
  QVariantMap result{
      {QStringLiteral("ok"), false},
      {QStringLiteral("output"),
       args.value(QStringLiteral("output")).toString()},
      {QStringLiteral("frames_written"), 0},
  };
  const QString output = args.value(QStringLiteral("output")).toString();
  const QString projectJson = args.value(QStringLiteral("project")).toString();
  if (output.isEmpty() || projectJson.isEmpty()) {
    result.insert(QStringLiteral("error"),
                   QStringLiteral("output and project are required"));
    return result;
  }
  const QJsonObject project =
      QJsonDocument::fromJson(projectJson.toUtf8()).object();
  const int width = project.value(QStringLiteral("width")).toInt();
  const int height = project.value(QStringLiteral("height")).toInt();
  const int fps = project.value(QStringLiteral("fps")).toInt();
  if (width <= 0 || height <= 0 || fps <= 0) {
    result.insert(
        QStringLiteral("error"),
        QStringLiteral("project must define positive width, height, and fps"));
    return result;
  }
  VideoRecorder* rec = ensureRecorder(state);
  const auto& snapshots = rec->snapshots();
  if (snapshots.isEmpty()) {
    result.insert(QStringLiteral("error"),
                   QStringLiteral("no recorded snapshots"));
    return result;
  }
  if (state.recorderCanvas == nullptr) {
    result.insert(QStringLiteral("error"),
                   QStringLiteral("recorder is not bound to a canvas"));
    return result;
  }

  QStringList ff{QStringLiteral("-y"),
                  QStringLiteral("-hide_banner"),
                  QStringLiteral("-loglevel"),
                  QStringLiteral("error"),
                  QStringLiteral("-f"),
                  QStringLiteral("rawvideo"),
                  QStringLiteral("-pix_fmt"),
                  QStringLiteral("rgba"),
                  QStringLiteral("-s"),
                  QStringLiteral("%1x%2").arg(width).arg(height),
                  QStringLiteral("-r"),
                  QString::number(fps),
                  QStringLiteral("-i"),
                  QStringLiteral("pipe:0")};
  const QVariant codecArgs =
      projectFfmpegArgs({{QStringLiteral("project"), projectJson}});
  if (codecArgs.canConvert<QStringList>()) {
    ff << codecArgs.toStringList();
  }
  ff << output;

  QProcess proc;
  proc.setProcessChannelMode(QProcess::SeparateChannels);
  proc.start(QStringLiteral("ffmpeg"), ff);
  if (!proc.waitForStarted(3000)) {
    result.insert(QStringLiteral("error"),
                   QStringLiteral("ffmpeg failed to start"));
    return result;
  }

  int framesWritten = 0;
  const qint64 durationMs = rec->durationMs();
  const qint64 frameStepMs = 1000 / fps;
  for (qint64 t = 0; t < durationMs; t += frameStepMs) {
    const QImage frame = previewRenderTimeMs(
        state, {{QStringLiteral("time_ms"), QVariant::fromValue<qlonglong>(t)},
                 {QStringLiteral("width"), width},
                 {QStringLiteral("height"), height},
                 {QStringLiteral("project"), projectJson}});
    if (frame.isNull()) {
      const int i = static_cast<int>(t / std::max<qint64>(1, frameStepMs));
      proc.closeWriteChannel();
      proc.waitForFinished(5000);
      result.insert(QStringLiteral("error"),
                     QStringLiteral("frame %1 render returned a null image")
                         .arg(i));
      result.insert(QStringLiteral("frames_written"), framesWritten);
      return result;
    }
    const QImage rgba = frame.convertToFormat(QImage::Format_RGBA8888);
    const qint64 expected =
        static_cast<qint64>(rgba.width()) * rgba.height() * 4;
    const qint64 written =
        proc.write(reinterpret_cast<const char*>(rgba.constBits()), expected);
    if (written != expected || !proc.waitForBytesWritten(10000)) {
      proc.closeWriteChannel();
      proc.waitForFinished(5000);
      result.insert(QStringLiteral("error"),
                     QStringLiteral("ffmpeg stdin write failed at frame %1")
                         .arg(framesWritten));
      result.insert(QStringLiteral("frames_written"), framesWritten);
      return result;
    }
    ++framesWritten;
  }
  proc.closeWriteChannel();
  proc.waitForFinished(60000);
  const bool ok =
      proc.exitStatus() == QProcess::NormalExit && proc.exitCode() == 0;
  result.insert(QStringLiteral("ok"), ok);
  result.insert(QStringLiteral("frames_written"), framesWritten);
  if (!ok) {
    const QByteArray err = proc.readAllStandardError();
    result.insert(QStringLiteral("error"),
                   QString::fromUtf8(err.isEmpty()
                                         ? QByteArrayLiteral(
                                               "ffmpeg exited with non-zero "
                                               "code")
                                         : err));
  }
  return result;
}

}  // namespace

std::optional<QVariant> routePreviewService(const QString& id,
                                             const QVariantMap& args,
                                             PluginState& state) {
  if (id == QStringLiteral("video_editor.preview_render_frame")) {
    return QVariant::fromValue(previewRenderFrame(state, args));
  }
  if (id == QStringLiteral("video_editor.preview_render_time_ms")) {
    return QVariant::fromValue(previewRenderTimeMs(state, args));
  }
  if (id == QStringLiteral("video_editor.export_recording")) {
    return QVariant{exportRecording(state, args)};
  }
  return std::nullopt;
}

}  // namespace imgsli::app::video_editor_services

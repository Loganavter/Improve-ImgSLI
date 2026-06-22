#include "plugins/video_editor/services/export_router.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QTimer>

#include "plugins/video_editor/services/project_router.h"

namespace imgsli::app::video_editor_services {

namespace {

QVariant exportRun(const QVariantMap& args) {
  const QStringList ffmpegArgs = buildExportArguments(args);
  if (ffmpegArgs.isEmpty()) {
    return false;
  }
  QProcess proc;
  proc.start(QStringLiteral("ffmpeg"), ffmpegArgs);
  if (!proc.waitForStarted()) {
    return false;
  }
  proc.waitForFinished(-1);
  return proc.exitStatus() == QProcess::NormalExit && proc.exitCode() == 0;
}

QVariant exportStart(const QVariantMap& args) {
  const QStringList ffmpegArgs = buildExportArguments(args);
  if (ffmpegArgs.isEmpty()) {
    return {};
  }
  QObject* parent = args.value(QStringLiteral("parent")).value<QObject*>();
  auto* process = new QProcess(parent);
  process->setProcessChannelMode(QProcess::SeparateChannels);
  QTimer::singleShot(0, process, [process, ffmpegArgs]() {
    process->start(QStringLiteral("ffmpeg"), ffmpegArgs);
  });
  return QVariant::fromValue<QObject*>(process);
}

QVariant exportCancel(const QVariantMap& args) {
  auto* process = qobject_cast<QProcess*>(
      args.value(QStringLiteral("process")).value<QObject*>());
  if (process == nullptr || process->state() == QProcess::NotRunning) {
    return false;
  }
  process->terminate();
  if (!process->waitForFinished(1500)) {
    process->kill();
  }
  return true;
}

}  // namespace

QStringList buildExportArguments(const QVariantMap& args) {
  const QString input = args.value(QStringLiteral("input")).toString();
  const QString output = args.value(QStringLiteral("output")).toString();
  const QString projectJson = args.value(QStringLiteral("project")).toString();
  if (input.isEmpty() || output.isEmpty()) {
    return {};
  }
  QStringList ffmpegArgs{
      QStringLiteral("-y"),       QStringLiteral("-hide_banner"),
      QStringLiteral("-progress"), QStringLiteral("pipe:1"),
      QStringLiteral("-nostats")};
  if (args.contains(QStringLiteral("start"))) {
    ffmpegArgs << QStringLiteral("-ss")
               << QString::number(
                      args.value(QStringLiteral("start")).toDouble());
  }
  if (args.contains(QStringLiteral("duration"))) {
    ffmpegArgs << QStringLiteral("-t")
               << QString::number(
                      args.value(QStringLiteral("duration")).toDouble());
  }
  ffmpegArgs << QStringLiteral("-i") << input;
  if (!projectJson.isEmpty()) {
    const QJsonObject project =
        QJsonDocument::fromJson(projectJson.toUtf8()).object();
    const int width = project.value(QStringLiteral("width")).toInt();
    const int height = project.value(QStringLiteral("height")).toInt();
    const int fps = project.value(QStringLiteral("fps")).toInt();
    if (width > 0 && height > 0) {
      ffmpegArgs << QStringLiteral("-vf")
                 << QStringLiteral("scale=%1:%2").arg(width).arg(height);
    }
    if (fps > 0) {
      ffmpegArgs << QStringLiteral("-r") << QString::number(fps);
    }
    const QVariant raw = projectFfmpegArgs(
        {{QStringLiteral("project"), projectJson}});
    if (raw.canConvert<QStringList>()) {
      ffmpegArgs << raw.toStringList();
    }
  }
  ffmpegArgs << output;
  return ffmpegArgs;
}

std::optional<QVariant> routeExportService(const QString& id,
                                            const QVariantMap& args) {
  if (id == QStringLiteral("video_editor.export_arguments")) {
    return QVariant{buildExportArguments(args)};
  }
  if (id == QStringLiteral("video_editor.export_run")) {
    return exportRun(args);
  }
  if (id == QStringLiteral("video_editor.export_start")) {
    return exportStart(args);
  }
  if (id == QStringLiteral("video_editor.export_cancel")) {
    return exportCancel(args);
  }
  return std::nullopt;
}

}  // namespace imgsli::app::video_editor_services

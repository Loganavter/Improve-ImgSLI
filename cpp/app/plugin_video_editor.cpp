// Phase 5: video editor plugin.
//
// Public service surface backed by `imgsli_core::video_editor` for the
// pure-logic side (timeline cursor, selection range, project resolution
// + ffmpeg argument synthesis) and a Qt `QProcess` launcher for the
// ffmpeg-driven export.
//
// Service ids:
//   * "video_editor.timeline_advance"  args: { position: int, step: int }
//   * "video_editor.selection_set"     args: { start?: int, end?: int }
//   * "video_editor.project_default"
//   * "video_editor.project_ffmpeg_args"   args: { project: QString JSON }
//   * "video_editor.project_adjust_height" args: { project: QString JSON, width: int }
//   * "video_editor.project_adjust_width"  args: { project: QString JSON, height: int }
//   * "video_editor.export_run"  args: { input: QString, output: QString,
//                                        project: QString JSON,
//                                        start?: float, duration?: float }
//   * "video_editor.backend"     → "ffmpeg-cli"

#include <QByteArray>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonValue>
#include <QProcess>
#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantMap>

#include <exception>
#include <string>

#include "imgsli/contracts/plugin_contract.h"
#include "imgsli_core_bridge/bridge.h"
#include "plugin_registry.h"

namespace imgsli::app {
namespace {

QString rs_to_q(const rust::String& s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

class VideoEditorPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override {
    return QStringLiteral("video_editor");
  }
  QString displayName() const override {
    return QStringLiteral("Video Editor");
  }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {
        QStringLiteral("video_editor.timeline_advance"),
        QStringLiteral("video_editor.selection_set"),
        QStringLiteral("video_editor.project_default"),
        QStringLiteral("video_editor.project_ffmpeg_args"),
        QStringLiteral("video_editor.project_adjust_height"),
        QStringLiteral("video_editor.project_adjust_width"),
        QStringLiteral("video_editor.export_run"),
    };
    def.translationNamespaces = {QStringLiteral("video_editor")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    static const QStringList kIds{
        QStringLiteral("video_editor.timeline_advance"),
        QStringLiteral("video_editor.selection_set"),
        QStringLiteral("video_editor.project_default"),
        QStringLiteral("video_editor.project_ffmpeg_args"),
        QStringLiteral("video_editor.project_adjust_height"),
        QStringLiteral("video_editor.project_adjust_width"),
        QStringLiteral("video_editor.export_run"),
        QStringLiteral("video_editor.backend"),
    };
    return kIds.contains(serviceId);
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    if (serviceId == QStringLiteral("video_editor.backend")) {
      return QStringLiteral("ffmpeg-cli");
    }
    if (serviceId == QStringLiteral("video_editor.timeline_advance")) {
      const qint64 pos = args.value(QStringLiteral("position")).toLongLong();
      const qint64 step = args.value(QStringLiteral("step"), 1).toLongLong();
      return QVariant::fromValue<qlonglong>(
          imgsli::video_timeline_advance(pos, step));
    }
    if (serviceId == QStringLiteral("video_editor.selection_set")) {
      const bool hasStart = args.contains(QStringLiteral("start"));
      const bool hasEnd = args.contains(QStringLiteral("end"));
      const qint64 start =
          args.value(QStringLiteral("start"), 0).toLongLong();
      const qint64 end =
          args.value(QStringLiteral("end"), 0).toLongLong();
      return rs_to_q(imgsli::video_selection_set_json(start, hasStart, end,
                                                     hasEnd));
    }
    if (serviceId == QStringLiteral("video_editor.project_default")) {
      return rs_to_q(imgsli::video_project_default_json());
    }
    if (serviceId == QStringLiteral("video_editor.project_ffmpeg_args")) {
      return projectFfmpegArgs(args);
    }
    if (serviceId == QStringLiteral("video_editor.project_adjust_height")) {
      return projectAdjustHeight(args);
    }
    if (serviceId == QStringLiteral("video_editor.project_adjust_width")) {
      return projectAdjustWidth(args);
    }
    if (serviceId == QStringLiteral("video_editor.export_run")) {
      return exportRun(args);
    }
    return {};
  }

 private:
  static QVariant projectFfmpegArgs(const QVariantMap& args) {
    const QString project = args.value(QStringLiteral("project")).toString();
    if (project.isEmpty()) {
      return {};
    }
    try {
      const QByteArray utf8 = project.toUtf8();
      const rust::String out = imgsli::video_project_ffmpeg_args_json(
          std::string(utf8.constData(),
                      static_cast<std::size_t>(utf8.size())));
      const QString json = rs_to_q(out);
      const QJsonArray arr = QJsonDocument::fromJson(json.toUtf8()).array();
      QStringList list;
      list.reserve(arr.size());
      for (const QJsonValue& v : arr) {
        list << v.toString();
      }
      return list;
    } catch (const std::exception&) {
      return {};
    }
  }

  static QVariant projectAdjustHeight(const QVariantMap& args) {
    const QString project = args.value(QStringLiteral("project")).toString();
    const int width = args.value(QStringLiteral("width")).toInt();
    if (project.isEmpty()) {
      return -1;
    }
    try {
      const QByteArray utf8 = project.toUtf8();
      return imgsli::video_project_adjust_height(
          std::string(utf8.constData(),
                      static_cast<std::size_t>(utf8.size())),
          width);
    } catch (const std::exception&) {
      return -1;
    }
  }

  static QVariant projectAdjustWidth(const QVariantMap& args) {
    const QString project = args.value(QStringLiteral("project")).toString();
    const int height = args.value(QStringLiteral("height")).toInt();
    if (project.isEmpty()) {
      return -1;
    }
    try {
      const QByteArray utf8 = project.toUtf8();
      return imgsli::video_project_adjust_width(
          std::string(utf8.constData(),
                      static_cast<std::size_t>(utf8.size())),
          height);
    } catch (const std::exception&) {
      return -1;
    }
  }

  /// Synchronous ffmpeg export. Used both directly and as the
  /// implementation behind the export plugin's video-export service.
  /// Returns true on a clean exit; the caller is responsible for showing
  /// progress or routing stderr to the log.
  static QVariant exportRun(const QVariantMap& args) {
    const QString input = args.value(QStringLiteral("input")).toString();
    const QString output = args.value(QStringLiteral("output")).toString();
    const QString projectJson =
        args.value(QStringLiteral("project")).toString();
    if (input.isEmpty() || output.isEmpty()) {
      return false;
    }
    QStringList ffmpegArgs{QStringLiteral("-y"),
                           QStringLiteral("-hide_banner")};
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
      const QVariant raw = projectFfmpegArgs(
          {{QStringLiteral("project"), projectJson}});
      if (raw.canConvert<QStringList>()) {
        ffmpegArgs << raw.toStringList();
      }
    }
    ffmpegArgs << output;

    QProcess proc;
    proc.start(QStringLiteral("ffmpeg"), ffmpegArgs);
    if (!proc.waitForStarted()) {
      return false;
    }
    proc.waitForFinished(-1);
    return proc.exitStatus() == QProcess::NormalExit &&
           proc.exitCode() == 0;
  }
};

IMGSLI_REGISTER_PLUGIN(VideoEditorPlugin);

}  // namespace
}  // namespace imgsli::app

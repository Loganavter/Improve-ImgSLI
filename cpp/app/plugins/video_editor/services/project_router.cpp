#include "plugins/video_editor/services/project_router.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonValue>
#include <QStringList>

#include <exception>
#include <string>

#include "imgsli_core_bridge/bridge.h"

namespace imgsli::app::video_editor_services {

namespace {

QString rs_to_q(const rust::String& s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

QVariant projectAdjustHeight(const QVariantMap& args) {
  const QString project = args.value(QStringLiteral("project")).toString();
  const int width = args.value(QStringLiteral("width")).toInt();
  if (project.isEmpty()) {
    return -1;
  }
  try {
    const QByteArray utf8 = project.toUtf8();
    return imgsli::video_project_adjust_height(
        std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())),
        width);
  } catch (const std::exception&) {
    return -1;
  }
}

QVariant projectAdjustWidth(const QVariantMap& args) {
  const QString project = args.value(QStringLiteral("project")).toString();
  const int height = args.value(QStringLiteral("height")).toInt();
  if (project.isEmpty()) {
    return -1;
  }
  try {
    const QByteArray utf8 = project.toUtf8();
    return imgsli::video_project_adjust_width(
        std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())),
        height);
  } catch (const std::exception&) {
    return -1;
  }
}

}  // namespace

QVariant projectFfmpegArgs(const QVariantMap& args) {
  const QString project = args.value(QStringLiteral("project")).toString();
  if (project.isEmpty()) {
    return {};
  }
  try {
    const QByteArray utf8 = project.toUtf8();
    const rust::String out = imgsli::video_project_ffmpeg_args_json(
        std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())));
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

std::optional<QVariant> routeProjectService(const QString& id,
                                             const QVariantMap& args) {
  if (id == QStringLiteral("video_editor.project_default")) {
    return QVariant{rs_to_q(imgsli::video_project_default_json())};
  }
  if (id == QStringLiteral("video_editor.project_ffmpeg_args")) {
    return projectFfmpegArgs(args);
  }
  if (id == QStringLiteral("video_editor.project_adjust_height")) {
    return projectAdjustHeight(args);
  }
  if (id == QStringLiteral("video_editor.project_adjust_width")) {
    return projectAdjustWidth(args);
  }
  return std::nullopt;
}

}  // namespace imgsli::app::video_editor_services

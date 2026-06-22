#pragma once

#include <QString>
#include <QVariant>
#include <QVariantMap>

#include <optional>

namespace imgsli::app::video_editor_services {

// Routes project-model ids backed by the Rust core's video_editor module:
//   * video_editor.project_default
//   * video_editor.project_ffmpeg_args
//   * video_editor.project_adjust_height
//   * video_editor.project_adjust_width
std::optional<QVariant> routeProjectService(const QString& id,
                                             const QVariantMap& args);

// Reused by routeExportService and exportRecording.
QVariant projectFfmpegArgs(const QVariantMap& args);

}  // namespace imgsli::app::video_editor_services

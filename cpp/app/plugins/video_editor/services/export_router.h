#pragma once

#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantMap>

#include <optional>

namespace imgsli::app::video_editor_services {

// Routes ffmpeg-driven export ids:
//   * video_editor.export_arguments
//   * video_editor.export_run
//   * video_editor.export_start
//   * video_editor.export_cancel
std::optional<QVariant> routeExportService(const QString& id,
                                            const QVariantMap& args);

// Reused by exportRecording in preview_router.
QStringList buildExportArguments(const QVariantMap& args);

}  // namespace imgsli::app::video_editor_services

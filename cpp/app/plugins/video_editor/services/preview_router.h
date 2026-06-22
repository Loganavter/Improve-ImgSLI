#pragma once

#include <QString>
#include <QVariant>
#include <QVariantMap>

#include <optional>

namespace imgsli::app::video_editor_services {

struct PluginState;

// Routes preview-render and full-recording-export ids:
//   * video_editor.preview_render_frame
//   * video_editor.preview_render_time_ms
//   * video_editor.export_recording
std::optional<QVariant> routePreviewService(const QString& id,
                                             const QVariantMap& args,
                                             PluginState& state);

}  // namespace imgsli::app::video_editor_services

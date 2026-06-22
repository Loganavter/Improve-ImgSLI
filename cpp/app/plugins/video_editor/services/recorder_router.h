#pragma once

#include <QString>
#include <QVariant>
#include <QVariantMap>

#include <optional>

namespace imgsli::app::video_editor_services {

struct PluginState;

// Routes recorder lifecycle, snapshot mutation, and bind ids:
//   * video_editor.bind_canvas, bind_comparison
//   * video_editor.recorder_start/stop/pause/resume/clear
//   * video_editor.recorder_state/snapshot_count/duration_ms/fps/set_fps/object
//   * video_editor.recorder_delete_at/delete_range/trim
//   * video_editor.recorder_undo/redo/can_undo/can_redo
std::optional<QVariant> routeRecorderService(const QString& id,
                                              const QVariantMap& args,
                                              PluginState& state);

}  // namespace imgsli::app::video_editor_services

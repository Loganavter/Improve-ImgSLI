// Video editor plugin (Phase 5).
//
// Surface registration + a thin dispatch over five service routers.
// Pure logic lives in `imgsli_core::video_editor`; per-group routing
// lives in `plugins/video_editor/services/*_router.{h,cpp}`, mirroring
// `src/plugins/video_editor/services/`.
//
// Service ids and their owning router:
//   * timeline   — timeline_advance, selection_set
//   * project    — project_default, project_ffmpeg_args, project_adjust_*
//   * export     — export_run, export_start, export_cancel, export_arguments
//   * recorder   — bind_canvas, bind_comparison, recorder_*
//   * preview    — preview_render_frame, preview_render_time_ms,
//                  export_recording
//   * video_editor.backend → handled inline (constant string).

#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantMap>

#include <optional>

#include "core/plugin_registry.h"
#include "imgsli/contracts/plugin_contract.h"
#include "plugins/video_editor/services/export_router.h"
#include "plugins/video_editor/services/plugin_state.h"
#include "plugins/video_editor/services/preview_router.h"
#include "plugins/video_editor/services/project_router.h"
#include "plugins/video_editor/services/recorder_router.h"
#include "plugins/video_editor/services/timeline_router.h"

namespace imgsli::app {
namespace {

const QStringList& serviceIds() {
  static const QStringList kIds{
      QStringLiteral("video_editor.timeline_advance"),
      QStringLiteral("video_editor.selection_set"),
      QStringLiteral("video_editor.project_default"),
      QStringLiteral("video_editor.project_ffmpeg_args"),
      QStringLiteral("video_editor.project_adjust_height"),
      QStringLiteral("video_editor.project_adjust_width"),
      QStringLiteral("video_editor.export_run"),
      QStringLiteral("video_editor.export_start"),
      QStringLiteral("video_editor.export_cancel"),
      QStringLiteral("video_editor.export_arguments"),
      QStringLiteral("video_editor.backend"),
      QStringLiteral("video_editor.bind_canvas"),
      QStringLiteral("video_editor.bind_comparison"),
      QStringLiteral("video_editor.recorder_start"),
      QStringLiteral("video_editor.recorder_stop"),
      QStringLiteral("video_editor.recorder_pause"),
      QStringLiteral("video_editor.recorder_resume"),
      QStringLiteral("video_editor.recorder_clear"),
      QStringLiteral("video_editor.recorder_state"),
      QStringLiteral("video_editor.recorder_snapshot_count"),
      QStringLiteral("video_editor.recorder_duration_ms"),
      QStringLiteral("video_editor.recorder_fps"),
      QStringLiteral("video_editor.recorder_set_fps"),
      QStringLiteral("video_editor.recorder_object"),
      QStringLiteral("video_editor.preview_render_frame"),
      QStringLiteral("video_editor.export_recording"),
      QStringLiteral("video_editor.recorder_delete_at"),
      QStringLiteral("video_editor.recorder_delete_range"),
      QStringLiteral("video_editor.recorder_trim"),
      QStringLiteral("video_editor.recorder_undo"),
      QStringLiteral("video_editor.recorder_redo"),
      QStringLiteral("video_editor.recorder_can_undo"),
      QStringLiteral("video_editor.recorder_can_redo"),
      QStringLiteral("video_editor.preview_render_time_ms"),
  };
  return kIds;
}

class VideoEditorPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override { return QStringLiteral("video_editor"); }
  QString displayName() const override { return QStringLiteral("Video Editor"); }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    // `backend` is queried via providesService but not declared as a
    // controlled command — matches the previous shape of this plugin.
    def.commandIds = serviceIds();
    def.commandIds.removeAll(QStringLiteral("video_editor.backend"));
    def.translationNamespaces = {QStringLiteral("video_editor")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceIds().contains(serviceId);
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    if (serviceId == QStringLiteral("video_editor.backend")) {
      return QStringLiteral("ffmpeg-cli");
    }
    using namespace video_editor_services;
    if (auto v = routeTimelineService(serviceId, args); v.has_value()) {
      return *v;
    }
    if (auto v = routeProjectService(serviceId, args); v.has_value()) {
      return *v;
    }
    if (auto v = routeExportService(serviceId, args); v.has_value()) {
      return *v;
    }
    if (auto v = routeRecorderService(serviceId, args, state_);
        v.has_value()) {
      return *v;
    }
    if (auto v = routePreviewService(serviceId, args, state_); v.has_value()) {
      return *v;
    }
    return {};
  }

 private:
  video_editor_services::PluginState state_;
};

IMGSLI_REGISTER_PLUGIN(VideoEditorPlugin);

}  // namespace
}  // namespace imgsli::app

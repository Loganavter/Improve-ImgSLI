#include "plugins/video_editor/services/recorder_router.h"

#include "plugins/comparison/controller.h"
#include "plugins/video_editor/services/plugin_state.h"
#include "plugins/video_editor/services/recorder.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app::video_editor_services {

std::optional<QVariant> routeRecorderService(const QString& id,
                                              const QVariantMap& args,
                                              PluginState& state) {
  if (id == QStringLiteral("video_editor.bind_canvas")) {
    auto* canvas = qobject_cast<CanvasWidget*>(
        args.value(QStringLiteral("canvas")).value<QObject*>());
    ensureRecorder(state)->bindCanvas(canvas);
    state.recorderCanvas = canvas;
    return canvas != nullptr;
  }
  if (id == QStringLiteral("video_editor.bind_comparison")) {
    auto* controller = qobject_cast<ComparisonController*>(
        args.value(QStringLiteral("controller")).value<QObject*>());
    ensureRecorder(state)->bindComparisonController(controller);
    return controller != nullptr;
  }
  if (id == QStringLiteral("video_editor.recorder_start")) {
    return ensureRecorder(state)->start();
  }
  if (id == QStringLiteral("video_editor.recorder_stop")) {
    ensureRecorder(state)->stop();
    return true;
  }
  if (id == QStringLiteral("video_editor.recorder_pause")) {
    return ensureRecorder(state)->pause();
  }
  if (id == QStringLiteral("video_editor.recorder_resume")) {
    return ensureRecorder(state)->resume();
  }
  if (id == QStringLiteral("video_editor.recorder_clear")) {
    ensureRecorder(state)->clear();
    return true;
  }
  if (id == QStringLiteral("video_editor.recorder_state")) {
    switch (ensureRecorder(state)->state()) {
      case VideoRecorder::State::Idle:
        return QVariant{QStringLiteral("idle")};
      case VideoRecorder::State::Recording:
        return QVariant{QStringLiteral("recording")};
      case VideoRecorder::State::Paused:
        return QVariant{QStringLiteral("paused")};
    }
    return QVariant{QStringLiteral("idle")};
  }
  if (id == QStringLiteral("video_editor.recorder_snapshot_count")) {
    return ensureRecorder(state)->snapshotCount();
  }
  if (id == QStringLiteral("video_editor.recorder_duration_ms")) {
    return QVariant::fromValue<qlonglong>(
        ensureRecorder(state)->durationMs());
  }
  if (id == QStringLiteral("video_editor.recorder_fps")) {
    return ensureRecorder(state)->fps();
  }
  if (id == QStringLiteral("video_editor.recorder_set_fps")) {
    ensureRecorder(state)->setFps(args.value(QStringLiteral("fps")).toInt());
    return ensureRecorder(state)->fps();
  }
  if (id == QStringLiteral("video_editor.recorder_object")) {
    return QVariant::fromValue<QObject*>(ensureRecorder(state));
  }
  if (id == QStringLiteral("video_editor.recorder_delete_at")) {
    return ensureRecorder(state)->deleteAt(
        args.value(QStringLiteral("index")).toInt());
  }
  if (id == QStringLiteral("video_editor.recorder_delete_range")) {
    return ensureRecorder(state)->deleteRange(
        args.value(QStringLiteral("start")).toInt(),
        args.value(QStringLiteral("end")).toInt());
  }
  if (id == QStringLiteral("video_editor.recorder_trim")) {
    return ensureRecorder(state)->trim(
        args.value(QStringLiteral("start")).toInt(),
        args.value(QStringLiteral("end")).toInt());
  }
  if (id == QStringLiteral("video_editor.recorder_undo")) {
    return ensureRecorder(state)->undo();
  }
  if (id == QStringLiteral("video_editor.recorder_redo")) {
    return ensureRecorder(state)->redo();
  }
  if (id == QStringLiteral("video_editor.recorder_can_undo")) {
    return ensureRecorder(state)->canUndo();
  }
  if (id == QStringLiteral("video_editor.recorder_can_redo")) {
    return ensureRecorder(state)->canRedo();
  }
  return std::nullopt;
}

}  // namespace imgsli::app::video_editor_services

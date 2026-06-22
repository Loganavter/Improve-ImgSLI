#pragma once

#include <QPointer>

namespace imgsli::app {
class CanvasWidget;
class VideoRecorder;
}  // namespace imgsli::app

namespace imgsli::app::video_editor_services {

// Shared state owned by the video_editor plugin and consumed by every
// router. Mirrors the per-service module layout in
// `src/plugins/video_editor/services/`.
struct PluginState {
  VideoRecorder* recorder = nullptr;
  QPointer<CanvasWidget> recorderCanvas;
};

VideoRecorder* ensureRecorder(PluginState& state);

}  // namespace imgsli::app::video_editor_services

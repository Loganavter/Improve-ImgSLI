#include "plugins/video_editor/services/plugin_state.h"

#include "plugins/video_editor/services/recorder.h"

namespace imgsli::app::video_editor_services {

VideoRecorder* ensureRecorder(PluginState& state) {
  if (state.recorder == nullptr) {
    state.recorder = new VideoRecorder();
  }
  return state.recorder;
}

}  // namespace imgsli::app::video_editor_services

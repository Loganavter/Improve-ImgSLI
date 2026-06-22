#pragma once

class QApplication;

namespace imgsli::app {
class VideoEditorController;
}

namespace imgsli::app::cli {

struct VideoTranscodeOptions;

void installVideoTranscodeCommand(QApplication& app,
                                  VideoEditorController* controller,
                                  const VideoTranscodeOptions& options);

}  // namespace imgsli::app::cli

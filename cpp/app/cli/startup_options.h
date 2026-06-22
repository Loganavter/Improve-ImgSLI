#pragma once

#include <QSize>
#include <QString>
#include <QStringList>

#include <optional>

namespace imgsli::app::cli {

struct VideoTranscodeOptions {
  QString input;
  QString output;
  std::optional<QSize> size;
  std::optional<int> fps;
};

struct StartupOptions {
  bool valid = true;
  QString error;

  bool smokeExit = false;
  bool contractCheck = false;
  int benchmarkFrames = 0;
  QString snapshotPath;

  std::optional<VideoTranscodeOptions> videoTranscode;
  QString analysisSnapshotPath;
  QString sessionBlueprintPath;

  QString compareLeftPath;
  QString compareRightPath;
  QString openPath;
  float split = 0.5F;
  bool splitSpecified = false;
  bool horizontal = false;
  bool magnifierEnabled = true;
  bool guidesEnabled = true;
  bool pasteOverlayEnabled = false;
  QString diffMode;
  QString channelMode;

  static StartupOptions parse(const QStringList& arguments);
};

}  // namespace imgsli::app::cli

#include "startup_options.h"

#include <QtGlobal>

namespace imgsli::app::cli {
namespace {

QString valueAfter(const QStringList& arguments, const QString& flag,
                   StartupOptions* options) {
  const qsizetype index = arguments.indexOf(flag);
  if (index < 0) {
    return {};
  }
  if (index + 1 >= arguments.size() ||
      arguments[index + 1].startsWith(QStringLiteral("--"))) {
    options->valid = false;
    options->error = QStringLiteral("%1 requires a value").arg(flag);
    return {};
  }
  return arguments[index + 1];
}

bool parsePositiveInt(const QString& text, const QString& flag, int* output,
                      StartupOptions* options) {
  bool ok = false;
  const int value = text.toInt(&ok);
  if (!ok || value <= 0) {
    options->valid = false;
    options->error =
        QStringLiteral("%1 requires a positive integer").arg(flag);
    return false;
  }
  *output = value;
  return true;
}

}  // namespace

StartupOptions StartupOptions::parse(const QStringList& arguments) {
  StartupOptions options;
  options.smokeExit =
      arguments.contains(QStringLiteral("--smoke-exit"));
  options.contractCheck =
      arguments.contains(QStringLiteral("--contract-check"));
  options.horizontal = arguments.contains(QStringLiteral("--horizontal"));
  options.magnifierEnabled =
      !arguments.contains(QStringLiteral("--no-magnifier"));
  options.guidesEnabled =
      !arguments.contains(QStringLiteral("--no-guides"));
  options.pasteOverlayEnabled =
      arguments.contains(QStringLiteral("--show-paste"));

  options.snapshotPath =
      valueAfter(arguments, QStringLiteral("--snapshot"), &options);
  if (!options.valid) return options;
  options.analysisSnapshotPath =
      valueAfter(arguments, QStringLiteral("--analysis-snapshot"), &options);
  if (!options.valid) return options;
  options.sessionBlueprintPath =
      valueAfter(arguments, QStringLiteral("--session-blueprint"), &options);
  if (!options.valid) return options;
  options.diffMode =
      valueAfter(arguments, QStringLiteral("--diff"), &options);
  if (!options.valid) return options;
  options.channelMode =
      valueAfter(arguments, QStringLiteral("--channel"), &options);
  if (!options.valid) return options;
  options.openPath =
      valueAfter(arguments, QStringLiteral("--open"), &options);
  if (!options.valid) return options;

  const QString benchmark =
      valueAfter(arguments, QStringLiteral("--benchmark-frames"), &options);
  if (!options.valid) return options;
  if (!benchmark.isEmpty() &&
      !parsePositiveInt(benchmark, QStringLiteral("--benchmark-frames"),
                        &options.benchmarkFrames, &options)) {
    return options;
  }

  const QString split =
      valueAfter(arguments, QStringLiteral("--split"), &options);
  if (!options.valid) return options;
  if (!split.isEmpty()) {
    bool ok = false;
    const float value = split.toFloat(&ok);
    if (!ok) {
      options.valid = false;
      options.error = QStringLiteral("--split requires a number");
      return options;
    }
    options.split = qBound(0.0F, value, 1.0F);
    options.splitSpecified = true;
  }

  const qsizetype compareIndex =
      arguments.indexOf(QStringLiteral("--compare"));
  if (compareIndex >= 0) {
    if (compareIndex + 2 >= arguments.size() ||
        arguments[compareIndex + 1].startsWith(QStringLiteral("--")) ||
        arguments[compareIndex + 2].startsWith(QStringLiteral("--"))) {
      options.valid = false;
      options.error =
          QStringLiteral("--compare requires left and right image paths");
      return options;
    }
    options.compareLeftPath = arguments[compareIndex + 1];
    options.compareRightPath = arguments[compareIndex + 2];
  }

  const qsizetype transcodeIndex =
      arguments.indexOf(QStringLiteral("--video-transcode"));
  if (transcodeIndex >= 0) {
    if (transcodeIndex + 2 >= arguments.size() ||
        arguments[transcodeIndex + 1].startsWith(QStringLiteral("--")) ||
        arguments[transcodeIndex + 2].startsWith(QStringLiteral("--"))) {
      options.valid = false;
      options.error =
          QStringLiteral("--video-transcode requires input and output paths");
      return options;
    }
    VideoTranscodeOptions transcode{
        .input = arguments[transcodeIndex + 1],
        .output = arguments[transcodeIndex + 2],
    };
    const QString videoSize =
        valueAfter(arguments, QStringLiteral("--video-size"), &options);
    if (!options.valid) return options;
    if (!videoSize.isEmpty()) {
      const QStringList parts = videoSize.split(u'x');
      bool widthOk = false;
      bool heightOk = false;
      const int width = parts.value(0).toInt(&widthOk);
      const int height = parts.value(1).toInt(&heightOk);
      if (parts.size() != 2 || !widthOk || !heightOk || width <= 0 ||
          height <= 0) {
        options.valid = false;
        options.error =
            QStringLiteral("--video-size requires WIDTHxHEIGHT");
        return options;
      }
      transcode.size = QSize(width, height);
    }
    const QString videoFps =
        valueAfter(arguments, QStringLiteral("--video-fps"), &options);
    if (!options.valid) return options;
    if (!videoFps.isEmpty()) {
      int fps = 0;
      if (!parsePositiveInt(videoFps, QStringLiteral("--video-fps"), &fps,
                            &options)) {
        return options;
      }
      transcode.fps = fps;
    }
    options.videoTranscode = transcode;
  }

  return options;
}

}  // namespace imgsli::app::cli

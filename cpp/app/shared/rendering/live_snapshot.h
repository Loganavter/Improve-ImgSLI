#pragma once

#include <QString>
#include <QStringList>

namespace imgsli::app::shared::rendering {

// Plain-data mirror of Python's `FrameSnapshot` (`plugins.video_editor.services
// .keyframing.types.FrameSnapshot`) restricted to the fields the C++ shell
// actually consumes today. The full viewport/settings freeze lives in the
// Rust project model; this struct is the C++ side glue.
struct LiveFrameSnapshot {
  double timestamp = 0.0;
  QString image1Path;
  QString image2Path;
  QString name1;
  QString name2;
};

// Picks the path from `items[index]` if in range. `items` may be QStringList
// (path-only) — the helper is provided so the snapshot builder mirrors the
// Python helper's tolerance to missing indices.
QString pathAtIndex(const QStringList& items, int index);

}  // namespace imgsli::app::shared::rendering

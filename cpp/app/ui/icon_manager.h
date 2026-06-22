#pragma once

#include <QIcon>
#include <QString>

namespace imgsli::app::ui {

enum class AppIcon {
  Settings,
  Save,
  QuickSave,
  Help,
  Photo,
  Sync,
  Delete,
  TextManipulator,
  VerticalSplit,
  HorizontalSplit,
  Magnifier,
  Freeze,
  TextFilename,
  HighlightDifferences,
  DividerVisible,
  DividerHidden,
  DividerColor,
  DividerWidth,
  Add,
  AddCircle,
  Remove,
  Close,
  Check,

  Record,
  Stop,
  Pause,
  Play,
  ExportVideo,
  VideoEdit,
  Undo,
  Redo,
  Scissors,
  CropIn,
  CropOut,

  Link,
  Unlink,
  MagnifierGuides,
  CaptureAreaColor,
  MagnifierBorderColor,
};

// Returns the SVG basename for the given AppIcon (e.g. "settings.svg").
QString appIconFile(AppIcon icon);

// Loads the themed icon from `<IMGSLI_RESOURCE_ROOT>/assets/icons/<theme>/<file>`,
// where theme is "dark" or "light" depending on the active palette. Returns an
// empty QIcon if not found.
QIcon getAppIcon(AppIcon icon);
QIcon getAppIcon(const QString& fileName);

}  // namespace imgsli::app::ui

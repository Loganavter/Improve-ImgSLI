#include "ui/icon_manager.h"

#include "utils/resource_loader.h"

#include <QApplication>
#include <QDir>
#include <QFileInfo>
#include <QHash>
#include <QPalette>

namespace imgsli::app::ui {

QString appIconFile(AppIcon icon) {
  switch (icon) {
    case AppIcon::Settings: return QStringLiteral("settings.svg");
    case AppIcon::Save: return QStringLiteral("save_icon.svg");
    case AppIcon::QuickSave: return QStringLiteral("quick_save.svg");
    case AppIcon::Help: return QStringLiteral("help.svg");
    case AppIcon::Photo: return QStringLiteral("photo_icon.svg");
    case AppIcon::Sync: return QStringLiteral("sync.svg");
    case AppIcon::Delete: return QStringLiteral("delete.svg");
    case AppIcon::TextManipulator: return QStringLiteral("text-manipulator.svg");
    case AppIcon::VerticalSplit: return QStringLiteral("vertical_split.svg");
    case AppIcon::HorizontalSplit: return QStringLiteral("horizontal_split.svg");
    case AppIcon::Magnifier: return QStringLiteral("magnifier.svg");
    case AppIcon::Freeze: return QStringLiteral("freeze.svg");
    case AppIcon::TextFilename: return QStringLiteral("text_filename.svg");
    case AppIcon::HighlightDifferences: return QStringLiteral("highlight_diff_icon.svg");
    case AppIcon::DividerVisible: return QStringLiteral("divider_visible.svg");
    case AppIcon::DividerHidden: return QStringLiteral("divider_hidden.svg");
    case AppIcon::DividerColor: return QStringLiteral("divider_color.svg");
    case AppIcon::DividerWidth: return QStringLiteral("divider_width.svg");
    case AppIcon::Add: return QStringLiteral("add.svg");
    case AppIcon::AddCircle: return QStringLiteral("add_circle.svg");
    case AppIcon::Remove: return QStringLiteral("remove.svg");
    case AppIcon::Close: return QStringLiteral("close.svg");
    case AppIcon::Check: return QStringLiteral("check.svg");
    case AppIcon::Record: return QStringLiteral("record.svg");
    case AppIcon::Stop: return QStringLiteral("stop.svg");
    case AppIcon::Pause: return QStringLiteral("pause.svg");
    case AppIcon::Play: return QStringLiteral("play.svg");
    case AppIcon::ExportVideo: return QStringLiteral("video.svg");
    case AppIcon::VideoEdit: return QStringLiteral("edit_video.svg");
    case AppIcon::Undo: return QStringLiteral("undo.svg");
    case AppIcon::Redo: return QStringLiteral("redo.svg");
    case AppIcon::Scissors: return QStringLiteral("scissors.svg");
    case AppIcon::CropIn: return QStringLiteral("crop_in.svg");
    case AppIcon::CropOut: return QStringLiteral("crop_out.svg");
    case AppIcon::Link: return QStringLiteral("link.svg");
    case AppIcon::Unlink: return QStringLiteral("unlink.svg");
    case AppIcon::MagnifierGuides: return QStringLiteral("laser.svg");
    case AppIcon::CaptureAreaColor: return QStringLiteral("circle_outline.svg");
    case AppIcon::MagnifierBorderColor: return QStringLiteral("magnifier.svg");
  }
  return {};
}

namespace {

bool paletteIsDark() {
  if (auto* app = qobject_cast<QApplication*>(QCoreApplication::instance())) {
    const QColor bg = app->palette().color(QPalette::Window);
    return bg.lightness() < 128;
  }
  return false;
}

QIcon loadFromFile(const QString& fileName) {
  if (fileName.isEmpty()) {
    return {};
  }
  const QString theme = paletteIsDark() ? QStringLiteral("dark") : QStringLiteral("light");
  const QString primary =
      utils::resourcePath(QStringLiteral("assets/icons/%1/%2").arg(theme, fileName));
  if (QFileInfo::exists(primary)) {
    return QIcon(primary);
  }
  const QString fallback = utils::resourcePath(
      QStringLiteral("assets/icons/%1/%2")
          .arg(theme == QStringLiteral("dark") ? QStringLiteral("light")
                                               : QStringLiteral("dark"),
               fileName));
  if (QFileInfo::exists(fallback)) {
    return QIcon(fallback);
  }
  return {};
}

}  // namespace

QIcon getAppIcon(AppIcon icon) { return loadFromFile(appIconFile(icon)); }

QIcon getAppIcon(const QString& fileName) { return loadFromFile(fileName); }

}  // namespace imgsli::app::ui

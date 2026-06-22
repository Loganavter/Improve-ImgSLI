#include "services/system/clipboard.h"

#include <QApplication>
#include <QClipboard>
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QImage>
#include <QMimeData>
#include <QStandardPaths>
#include <QUrl>

namespace imgsli::app::services::system {

namespace {

bool isHttpUrl(const QString& s) {
  return s.startsWith(QStringLiteral("http://")) ||
         s.startsWith(QStringLiteral("https://"));
}

}  // namespace

QStringList collectClipboardImageItems() {
  QStringList items;
  QClipboard* clipboard = QApplication::clipboard();
  if (!clipboard) {
    return items;
  }
  const QMimeData* mime = clipboard->mimeData();
  if (!mime) {
    return items;
  }

  const QString text = mime->text();
  if (!text.isEmpty()) {
    for (const QString& rawLine : text.split(QLatin1Char('\n'))) {
      const QString line = rawLine.trimmed();
      if (line.isEmpty()) {
        continue;
      }
      if (line.startsWith(QStringLiteral("file://"))) {
        const QString path = QUrl(line).toLocalFile();
        if (QFileInfo::exists(path)) {
          items.append(path);
        }
      } else if (QFileInfo::exists(line)) {
        items.append(line);
      } else if (isHttpUrl(line)) {
        items.append(line);
      }
    }
  }

  if (mime->hasUrls()) {
    for (const QUrl& url : mime->urls()) {
      if (url.isLocalFile()) {
        items.append(url.toLocalFile());
      } else {
        const QString s = url.toString();
        if (isHttpUrl(s)) {
          items.append(s);
        }
      }
    }
  }

  if (items.isEmpty() && mime->hasImage()) {
    const QImage img = clipboard->image();
    if (!img.isNull()) {
      const QString tempDir = QStandardPaths::writableLocation(QStandardPaths::TempLocation);
      const QString name = QStringLiteral("clip_%1.png")
                               .arg(QDateTime::currentMSecsSinceEpoch());
      const QString path = QDir(tempDir).filePath(name);
      if (img.save(path, "PNG")) {
        items.append(path);
      }
    }
  }

  return items;
}

}  // namespace imgsli::app::services::system

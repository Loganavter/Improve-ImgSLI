#include "utils/resource_loader.h"

#include <QCoreApplication>
#include <QDir>

#include <algorithm>

namespace imgsli::app::utils {

namespace {

QString findLongestPrefix(const QString& text, int availableWidth, int maxChars,
                          const QFont& font, const GetSizeFn& getSize) {
  QString best;
  int low = 0;
  int high = std::min(static_cast<int>(text.size()), maxChars);
  while (low <= high) {
    const int mid = (low + high) / 2;
    const QString prefix = text.left(mid);
    const QSize sz = getSize(prefix, font);
    if (sz.width() <= availableWidth) {
      best = prefix;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return best;
}

}  // namespace

QString resourcePath(const QString& relativePath) {
  const QByteArray root = qgetenv("IMGSLI_RESOURCE_ROOT");
  QString base;
  if (!root.isEmpty()) {
    base = QString::fromUtf8(root);
  } else {
#ifdef IMGSLI_DEFAULT_RESOURCE_ROOT
    base = QStringLiteral(IMGSLI_DEFAULT_RESOURCE_ROOT);
#else
    base = QCoreApplication::applicationDirPath();
#endif
  }
  return QDir(base).filePath(relativePath);
}

QString truncateText(const QString& text, int availableWidth, int maxLen,
                     const QFont& font, const GetSizeFn& getSize) {
  if (text.isEmpty() || availableWidth <= 5) {
    return QString();
  }
  if (text.size() <= maxLen) {
    if (getSize(text, font).width() <= availableWidth) {
      return text;
    }
  }
  for (const QString& ellipsis :
       {QStringLiteral("..."), QStringLiteral(".."), QStringLiteral(".")}) {
    if (maxLen < ellipsis.size()) {
      continue;
    }
    const int ellipsisW = getSize(ellipsis, font).width();
    if (ellipsisW > availableWidth) {
      continue;
    }
    const int availForText = availableWidth - ellipsisW;
    const int maxCharsForText = maxLen - ellipsis.size();
    const QString base =
        findLongestPrefix(text, availForText, maxCharsForText, font, getSize);
    if (!base.isNull()) {
      return base + ellipsis;
    }
  }
  return findLongestPrefix(text, availableWidth, maxLen, font, getSize);
}

QSize scaledPixmapDimensions(const QSize& image1, const QSize& image2,
                             int targetWidth, int targetHeight) {
  if (image1.isEmpty() || image2.isEmpty() || image1.width() <= 0 ||
      image1.height() <= 0 || image2.width() <= 0 || image2.height() <= 0) {
    return QSize(targetWidth, targetHeight);
  }
  const double s1 = std::min(static_cast<double>(targetWidth) / image1.width(),
                              static_cast<double>(targetHeight) / image1.height());
  const double s2 = std::min(static_cast<double>(targetWidth) / image2.width(),
                              static_cast<double>(targetHeight) / image2.height());
  const double s = std::min(s1, s2);
  return QSize(static_cast<int>(std::round(image1.width() * s)),
               static_cast<int>(std::round(image1.height() * s)));
}

}  // namespace imgsli::app::utils

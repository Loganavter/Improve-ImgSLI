#pragma once

#include <QIcon>
#include <QPixmap>
#include <QSize>

namespace sli::toolkit {

/// Normalize an icon pixmap by cropping transparent padding and
/// rescaling. Mirrors Python `normalized_icon_pixmap()` from
/// `icon_pixmap.py`. The QIcon overload mirrors the Python path
/// where a QIcon is passed directly.
QPixmap normalizedIconPixmap(const QIcon& icon, int size);
QPixmap normalizedIconPixmap(const QIcon& icon, const QSize& size);

/// Origin-based overload — accepts a QVariant that may be a
/// QIcon, string name, or null, mirroring Python's flexible
/// icon_value argument. Falls back to empty QPixmap if the
/// variant cannot be resolved.
QPixmap normalizedIconPixmap(const QVariant& iconValue, int size);
QPixmap normalizedIconPixmap(const QVariant& iconValue, const QSize& size);

/// Clear the internal LRU pixmap cache.
void clearIconPixmapCache();

}  // namespace sli::toolkit
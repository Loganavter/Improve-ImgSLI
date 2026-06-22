#include "sli/toolkit/helpers/icon_pixmap.h"

#include <QIcon>
#include <QImage>
#include <QPainter>
#include <QSize>
#include <QVariant>

#include <algorithm>
#include <map>
#include <tuple>

namespace sli::toolkit {

namespace {

constexpr int kPixmapCacheMax = 512;

// LRU cache: ordered map of (cacheKey, width, height) -> QPixmap.
struct CacheEntry {
    QPixmap pixmap;
    int64_t accessOrder;
};

std::map<std::tuple<int64_t, int, int>, CacheEntry>& pixmapCache()
{
    static std::map<std::tuple<int64_t, int, int>, CacheEntry> cache;
    return cache;
}

int64_t g_accessCounter = 0;

QPixmap cachePixmap(const std::tuple<int64_t, int, int>& key, QPixmap pixmap)
{
    auto& cache = pixmapCache();
    cache[key] = {pixmap, g_accessCounter++};

    // Evict LRU if over limit
    while (cache.size() > kPixmapCacheMax) {
        auto lruIt = cache.begin();
        int64_t lruOrder = lruIt->second.accessOrder;
        auto lru = lruIt;
        for (auto it = cache.begin(); it != cache.end(); ++it) {
            if (it->second.accessOrder < lruOrder) {
                lruOrder = it->second.accessOrder;
                lru = it;
            }
        }
        cache.erase(lru);
    }
    return pixmap;
}

// Find bounding box of non-transparent pixels.
std::optional<std::tuple<int, int, int, int>> alphaBBox(const QPixmap& pixmap)
{
    QImage image = pixmap.toImage();
    int w = image.width();
    int h = image.height();
    int left = w, top = h, right = -1, bottom = -1;

    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            if (image.pixelColor(x, y).alpha() > 0) {
                left = std::min(left, x);
                top = std::min(top, y);
                right = std::max(right, x);
                bottom = std::max(bottom, y);
            }
        }
    }

    if (right < left || bottom < top)
        return std::nullopt;
    return std::make_tuple(left, top, right, bottom);
}

QPixmap normalizedIconPixmapImpl(const QIcon& icon, int targetW, int targetH)
{
    targetW = std::max(1, targetW);
    targetH = std::max(1, targetH);

    int64_t cacheKey = icon.cacheKey();
    auto cacheKeyTup = std::make_tuple(cacheKey, targetW, targetH);
    auto& cache = pixmapCache();
    auto it = cache.find(cacheKeyTup);
    if (it != cache.end()) {
        it->second.accessOrder = g_accessCounter++;
        return it->second.pixmap;
    }

    constexpr int scale = 4;
    int sourceW = targetW * scale;
    int sourceH = targetH * scale;
    QPixmap pixmap = icon.pixmap(QSize(sourceW, sourceH));
    if (pixmap.isNull())
        return pixmap;

    auto bbox = alphaBBox(pixmap);
    if (!bbox.has_value())
        return cachePixmap(cacheKeyTup, icon.pixmap(QSize(targetW, targetH)));

    auto [left, top, right, bottom] = bbox.value();
    int contentW = right - left + 1;
    int contentH = bottom - top + 1;
    if (contentW <= 0 || contentH <= 0)
        return cachePixmap(cacheKeyTup, icon.pixmap(QSize(targetW, targetH)));

    // Only normalize genuinely padded sources. Filled glyphs such as pause/play
    // intentionally occupy about half of a 24px canvas; cropping and rescaling
    // them makes strokes/bars look much heavier than the source icon.
    double contentRatio = std::max(
        static_cast<double>(contentW) / sourceW,
        static_cast<double>(contentH) / sourceH);
    if (contentRatio >= 0.5)
        return cachePixmap(cacheKeyTup, icon.pixmap(QSize(targetW, targetH)));

    int targetContentW = targetW - 2;
    int targetContentH = targetH - 2;
    int sourceContentLimitW = targetContentW * scale;
    int sourceContentLimitH = targetContentH * scale;
    if (contentW >= sourceContentLimitW && contentH >= sourceContentLimitH)
        return cachePixmap(cacheKeyTup, icon.pixmap(QSize(targetW, targetH)));

    QPixmap cropped = pixmap.copy(left, top, contentW, contentH);
    int maxW = std::max(1, targetContentW);
    int maxH = std::max(1, targetContentH);
    QPixmap scaled = cropped.scaled(
        maxW, maxH,
        Qt::KeepAspectRatio,
        Qt::SmoothTransformation);

    QPixmap result(targetW, targetH);
    result.fill(Qt::transparent);
    {
        QPainter p(&result);
        p.setRenderHint(QPainter::SmoothPixmapTransform);
        int x = (targetW - scaled.width()) / 2;
        int y = (targetH - scaled.height()) / 2;
        p.drawPixmap(x, y, scaled);
    }

    return cachePixmap(cacheKeyTup, result);
}

} // anonymous namespace

QPixmap normalizedIconPixmap(const QIcon& icon, int size)
{
    return normalizedIconPixmapImpl(icon, size, size);
}

QPixmap normalizedIconPixmap(const QIcon& icon, const QSize& size)
{
    return normalizedIconPixmapImpl(icon,
                                    std::max(1, size.width()),
                                    std::max(1, size.height()));
}

QPixmap normalizedIconPixmap(const QVariant& iconValue, int size)
{
    if (iconValue.canConvert<QIcon>()) {
        QIcon icon = iconValue.value<QIcon>();
        return normalizedIconPixmap(icon, size);
    }
    if (iconValue.isNull() || !iconValue.isValid())
        return QPixmap();
    return QPixmap();
}

QPixmap normalizedIconPixmap(const QVariant& iconValue, const QSize& size)
{
    if (iconValue.canConvert<QIcon>()) {
        QIcon icon = iconValue.value<QIcon>();
        return normalizedIconPixmap(icon, size);
    }
    if (iconValue.isNull() || !iconValue.isValid())
        return QPixmap();
    return QPixmap();
}

void clearIconPixmapCache()
{
    pixmapCache().clear();
}

}  // namespace sli::toolkit
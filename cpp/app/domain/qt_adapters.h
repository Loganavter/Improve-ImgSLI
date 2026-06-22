#pragma once

#include <QColor>
#include <QPoint>
#include <QPointF>
#include <QRect>
#include <QString>

#include "domain/types.h"

namespace imgsli::app::domain {

inline QPointF toQPointF(const Point& p) { return QPointF(p.x, p.y); }
inline Point fromQPointF(const QPointF& q) { return Point{q.x(), q.y()}; }

inline QPoint toQPoint(const Point& p) {
  return QPoint(static_cast<int>(p.x), static_cast<int>(p.y));
}
inline Point fromQPoint(const QPoint& q) {
  return Point{static_cast<double>(q.x()), static_cast<double>(q.y())};
}

inline QColor toQColor(const Color& c) { return QColor(c.r, c.g, c.b, c.a); }
inline Color fromQColor(const QColor& q) {
  return Color{q.red(), q.green(), q.blue(), q.alpha()};
}

inline QRect toQRect(const Rect& r) { return QRect(r.x, r.y, r.w, r.h); }
inline Rect fromQRect(const QRect& q) {
  return Rect{q.x(), q.y(), q.width(), q.height()};
}

inline Color hexToColor(const QString& hex) {
  QColor q(hex);
  return Color{q.red(), q.green(), q.blue(), q.alpha()};
}

inline QString colorToHex(const Color& c) {
  return QColor(c.r, c.g, c.b, c.a).name(QColor::HexArgb);
}

}  // namespace imgsli::app::domain

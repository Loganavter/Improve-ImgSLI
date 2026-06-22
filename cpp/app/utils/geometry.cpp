#include "utils/geometry.h"

#include <QStringList>

#include <algorithm>

namespace imgsli::app::utils {

namespace {

constexpr int kMinWidth = 200;
constexpr int kMinHeight = 150;

}  // namespace

GeometryManager::GeometryManager(QWidget* window, QSettings* settings,
                                 Store* store, QObject* parent)
    : QObject(parent), window_(window), settings_(settings), store_(store) {}

void GeometryManager::loadAndApply() {
  if (window_ == nullptr || settings_ == nullptr) {
    return;
  }

  const bool wasMaximized =
      settings_->value(QStringLiteral("window_was_maximized"), false).toBool();
  const QByteArray savedNormalGeom =
      settings_->value(QStringLiteral("normal_geometry"), QByteArray())
          .toByteArray();
  const QString savedNormalRectStr =
      settings_->value(QStringLiteral("normal_rect"), QString()).toString();

  bool restored = false;
  if (!savedNormalRectStr.isEmpty()) {
    const QStringList parts = savedNormalRectStr.split(QLatin1Char(','));
    if (parts.size() == 4) {
      bool ok = true;
      const int x = parts[0].toInt(&ok);
      const int y = parts[1].toInt(&ok);
      const int w = parts[2].toInt(&ok);
      const int h = parts[3].toInt(&ok);
      if (ok) {
        window_->setGeometry(x, y, std::max(kMinWidth, w),
                              std::max(kMinHeight, h));
        normalRectStr_ = savedNormalRectStr;
        restored = true;
      }
    }
  }

  if (!restored) {
    if (!savedNormalGeom.isNull()) {
      normalGeometry_ = savedNormalGeom;
      window_->restoreGeometry(savedNormalGeom);
    } else {
      window_->setGeometry(100, 100, 1024, 768);
      normalGeometry_ = window_->saveGeometry();
    }
  }

  freezeNormalUpdates_ = wasMaximized;

  const Qt::WindowStates state = window_->windowState();
  if (wasMaximized) {
    window_->setWindowState(state | Qt::WindowMaximized);
  } else {
    window_->setWindowState(state & ~Qt::WindowMaximized);
  }
}

void GeometryManager::updateNormalGeometryIfNeeded() {
  if (freezeNormalUpdates_ || window_ == nullptr) {
    return;
  }
  if (!window_->isMaximized() && !window_->isFullScreen()) {
    normalGeometry_ = window_->saveGeometry();
    const QRect g = window_->geometry();
    normalRectStr_ = QStringLiteral("%1,%2,%3,%4")
                          .arg(g.x())
                          .arg(g.y())
                          .arg(g.width())
                          .arg(g.height());
  }
}

void GeometryManager::saveOnClose() {
  if (window_ == nullptr || settings_ == nullptr) {
    return;
  }
  const bool isMaximized = window_->isMaximized() || window_->isFullScreen();
  settings_->setValue(QStringLiteral("window_was_maximized"), isMaximized);
  if (normalGeometry_.has_value() && !normalGeometry_->isNull()) {
    settings_->setValue(QStringLiteral("normal_geometry"), *normalGeometry_);
  }
  if (normalRectStr_.has_value() && !normalRectStr_->isEmpty()) {
    settings_->setValue(QStringLiteral("normal_rect"), *normalRectStr_);
  }
  settings_->sync();
}

void GeometryManager::onLeftMaximizedState() {
  freezeNormalUpdates_ = false;
  updateNormalGeometryIfNeeded();
}

void GeometryManager::beginMaximizeTransition() {
  if (window_ == nullptr) {
    return;
  }
  const QRect g = window_->geometry();
  normalRectStr_ = QStringLiteral("%1,%2,%3,%4")
                        .arg(g.x())
                        .arg(g.y())
                        .arg(g.width())
                        .arg(g.height());
  freezeNormalUpdates_ = true;
}

}  // namespace imgsli::app::utils

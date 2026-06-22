#pragma once

#include <QByteArray>
#include <QObject>
#include <QSettings>
#include <QString>
#include <QWidget>

#include <optional>

namespace imgsli::app {
class Store;
}

namespace imgsli::app::utils {

// Mirrors Python `utils/geometry.GeometryManager`. Owns the window's
// "normal" (non-maximized) geometry persistence: save on close, restore on
// open, freeze updates during a maximize transition.
class GeometryManager : public QObject {
  Q_OBJECT

 public:
  GeometryManager(QWidget* window, QSettings* settings, Store* store = nullptr,
                  QObject* parent = nullptr);

  void loadAndApply();
  void updateNormalGeometryIfNeeded();
  void saveOnClose();
  void onLeftMaximizedState();
  void beginMaximizeTransition();

 private:
  QWidget* window_ = nullptr;
  QSettings* settings_ = nullptr;
  Store* store_ = nullptr;
  std::optional<QByteArray> normalGeometry_;
  std::optional<QString> normalRectStr_;
  bool freezeNormalUpdates_ = false;
};

}  // namespace imgsli::app::utils

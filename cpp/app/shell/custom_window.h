#pragma once

#include <QMainWindow>
#include <QString>

class QHBoxLayout;
class QLabel;
class QMouseEvent;
class QVBoxLayout;
class QWidget;

namespace imgsli::app {

/// Frameless top-level window with a custom client-side title bar and
/// edge resize hot zones. Used because Qt-Wayland 6.11 + QRhiWidget +
/// Mutter never engages the Adwaita decoration plugin for our top-level
/// (see docs/dev/CPP_PORT_HARDENING.md). Telegram Desktop, Discord and
/// other Qt apps use the same approach. Resize and move are delegated
/// to the compositor through QWindow::startSystemResize / startSystemMove,
/// so Mutter's snap-to-edge gestures keep working.
class CustomWindow final : public QMainWindow {
  Q_OBJECT

 public:
  explicit CustomWindow(QWidget *parent = nullptr);

  void setBody(QWidget *body);
  void setTitleText(const QString &text);

 protected:
  bool event(QEvent *e) override;

 private:
  enum Edge {
    EdgeNone = 0,
    EdgeLeft = 1 << 0,
    EdgeRight = 1 << 1,
    EdgeTop = 1 << 2,
    EdgeBottom = 1 << 3,
  };

  int detectEdges(const QPoint &localPos) const;
  void updateCursorForEdges(int edges);
  void onStateChanged();

  QWidget *outerCentral_ = nullptr;
  QVBoxLayout *outerLayout_ = nullptr;
  QWidget *titleBar_ = nullptr;
  QLabel *titleLabel_ = nullptr;
  QWidget *body_ = nullptr;
  int resizeMargin_ = 6;
};

}  // namespace imgsli::app

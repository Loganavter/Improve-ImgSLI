#pragma once

#include <QWidget>

class QGraphicsOpacityEffect;
class QPixmap;

namespace sli::toolkit {

/// Ghost image widget shown during drag operations.
/// Mirrors Python's DragGhostWidget.
class DragGhostWidget : public QWidget {
  Q_OBJECT

 public:
  explicit DragGhostWidget(QWidget* parent);

  void setPixmap(const QPixmap& pixmap);
  void setOpacity(qreal opacity);

  // Override QWidget::move to handle global -> parent-relative mapping.
  void move(const QPoint& pos);
  using QWidget::move;

 protected:
  void paintEvent(QPaintEvent* event) override;

 private:
  QPixmap pixmap_;
  QGraphicsOpacityEffect* opacityEffect_ = nullptr;
};

}  // namespace sli::toolkit
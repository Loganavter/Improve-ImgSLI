#pragma once

#include <QColor>
#include <QWidget>

namespace imgsli::app::ui::widgets {

// Child widget that paints its own AA rounded background. Mirror of Python
// `src/ui/widgets/rounded_overlay.py`. Works correctly above an OpenGL/QRhi
// surface, where QSS `border-radius` on a child widget leaves a leaking
// rectangle outside the rounded shape.
class RoundedOverlayWidget : public QWidget {
  Q_OBJECT
 public:
  explicit RoundedOverlayWidget(QWidget* parent = nullptr,
                                QColor bgColor = QColor(0, 0, 0, 140),
                                qreal radius = 6.0);

  void setBackgroundColor(const QColor& color);
  void setRadius(qreal radius);

 protected:
  void paintEvent(QPaintEvent* event) override;

 private:
  QColor bgColor_;
  qreal radius_;
};

}  // namespace imgsli::app::ui::widgets

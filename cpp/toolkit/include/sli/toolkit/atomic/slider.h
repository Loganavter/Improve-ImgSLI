#pragma once

#include <QPropertyAnimation>
#include <QSlider>

namespace sli::toolkit {

// QSlider subclass with theme-aware paint, hover-grown handle, and an
// animated inner-knob scale. Mirrors Python atomic/slider.py.
class Slider final : public QSlider {
  Q_OBJECT
  Q_PROPERTY(double innerScale READ innerScale WRITE setInnerScale)

 public:
  static constexpr int kTrackHeight = 5;
  static constexpr int kHandleRadius = 8;
  static constexpr int kMarginH = 10;

  explicit Slider(Qt::Orientation orientation = Qt::Horizontal,
                  QWidget* parent = nullptr);

  double innerScale() const { return innerScale_; }
  void setInnerScale(double value);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void enterEvent(QEnterEvent* event) override;
  void leaveEvent(QEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void mouseReleaseEvent(QMouseEvent* event) override;

 private:
  void animateInnerScale(double target);

  bool hovered_ = false;
  bool pressed_ = false;
  double innerScale_ = 0.50;
  QPropertyAnimation animInner_;
};

}  // namespace sli::toolkit

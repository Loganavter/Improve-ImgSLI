#pragma once

#include <QWidget>

namespace sli::toolkit {

/// Theme-aware one-pixel separator for section and toolbar layouts.
class Divider final : public QWidget {
  Q_OBJECT

 public:
  explicit Divider(Qt::Orientation orientation = Qt::Horizontal,
                   QWidget* parent = nullptr);

  Qt::Orientation orientation() const { return orientation_; }
  void setOrientation(Qt::Orientation orientation);

  QSize sizeHint() const override;

 protected:
  void paintEvent(QPaintEvent* event) override;

 private:
  Qt::Orientation orientation_;
};

}  // namespace sli::toolkit

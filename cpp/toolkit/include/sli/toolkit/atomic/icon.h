#pragma once

#include <QColor>
#include <QIcon>
#include <QWidget>

namespace sli::toolkit {

/// Theme-compatible icon view with optional monochrome tint.
class Icon final : public QWidget {
  Q_OBJECT

 public:
  explicit Icon(const QIcon& icon = {}, QWidget* parent = nullptr);

  QIcon icon() const { return icon_; }
  void setIcon(const QIcon& icon);
  QSize iconSize() const { return iconSize_; }
  void setIconSize(const QSize& size);
  QColor tintColor() const { return tintColor_; }
  void setTintColor(const QColor& color);
  void clearTintColor();

  QSize sizeHint() const override;

 protected:
  void paintEvent(QPaintEvent* event) override;

 private:
  QIcon icon_;
  QSize iconSize_{18, 18};
  QColor tintColor_;
};

}  // namespace sli::toolkit

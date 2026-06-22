#pragma once

#include <QLineEdit>

#include <optional>

namespace sli::toolkit {

// QLineEdit with rounded corners, theme-aware paint, and an optional
// focused/unfocused underline accent.
class CustomLineEdit : public QLineEdit {
  Q_OBJECT

 public:
  static constexpr int kRadius = 6;
  static constexpr int kHPadding = 8;
  static constexpr int kVPadding = 4;

  explicit CustomLineEdit(QWidget* parent = nullptr);

  void setUnderlineColor(const QColor& color);
  void setFocusedUnderlineColor(const QColor& color);
  void setUnderlineThickness(double thickness);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void focusInEvent(QFocusEvent* event) override;
  void focusOutEvent(QFocusEvent* event) override;

 private:
  std::optional<QColor> underlineColor_;
  std::optional<QColor> focusedUnderlineColor_;
  double underlineThickness_ = 1.0;
};

}  // namespace sli::toolkit

#pragma once

#include <QLabel>
#include <QString>

#include <optional>

namespace sli::toolkit {

// Typed typography label. Variants map to font sizes / weights / colors
// the way Python `LabelVariantSpec` does.
class Label final : public QLabel {
  Q_OBJECT

 public:
  enum class Variant {
    Body,       // default text size
    Caption,    // small + muted
    Subhead,    // medium-emphasis
    Heading,    // bold + larger
    Display,    // largest + bold
  };

  explicit Label(const QString& text = {}, Variant variant = Variant::Body,
                 QWidget* parent = nullptr);

  void setVariant(Variant variant);
  Variant variant() const { return variant_; }

  void setElideMode(Qt::TextElideMode mode);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void changeEvent(QEvent* event) override;

 private:
  void applyVariantStyle();

  Variant variant_;
  std::optional<Qt::TextElideMode> elideMode_;
};

}  // namespace sli::toolkit

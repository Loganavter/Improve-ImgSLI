#include "sli/toolkit/atomic/text_labels.h"

#include <QEvent>
#include <QFont>
#include <QFontMetrics>
#include <QPainter>
#include <QPaintEvent>
#include <QRect>
#include <Qt>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

namespace {

struct VariantStyle {
  int pixelSize;
  bool bold;
  QString colorToken;
};

VariantStyle styleFor(Label::Variant v) {
  switch (v) {
    case Label::Variant::Caption:
      return {11, false, QStringLiteral("dialog.text")};
    case Label::Variant::Subhead:
      return {14, false, QStringLiteral("dialog.text")};
    case Label::Variant::Heading:
      return {18, true, QStringLiteral("dialog.text")};
    case Label::Variant::Display:
      return {24, true, QStringLiteral("dialog.text")};
    case Label::Variant::Body:
    default:
      return {13, false, QStringLiteral("dialog.text")};
  }
}

}  // namespace

Label::Label(const QString& text, Variant variant, QWidget* parent)
    : QLabel(text, parent), variant_(variant) {
  applyVariantStyle();
}

void Label::setVariant(Variant variant) {
  if (variant == variant_) {
    return;
  }
  variant_ = variant;
  applyVariantStyle();
  update();
}

void Label::setElideMode(Qt::TextElideMode mode) {
  elideMode_ = mode;
  update();
}

void Label::applyVariantStyle() {
  const VariantStyle s = styleFor(variant_);
  QFont f = font();
  f.setPixelSize(s.pixelSize);
  f.setBold(s.bold);
  setFont(f);
}

void Label::paintEvent(QPaintEvent* event) {
  if (!elideMode_.has_value()) {
    QLabel::paintEvent(event);
    return;
  }
  QPainter p(this);
  const VariantStyle s = styleFor(variant_);
  p.setPen(Theme::getColor(s.colorToken));
  QFontMetrics fm(font());
  const QString elided = fm.elidedText(text(), *elideMode_, width());
  p.drawText(rect(), static_cast<int>(alignment()), elided);
}

void Label::changeEvent(QEvent* event) {
  if (event->type() == QEvent::PaletteChange ||
      event->type() == QEvent::StyleChange) {
    applyVariantStyle();
  }
  QLabel::changeEvent(event);
}

}  // namespace sli::toolkit

#include "sli/toolkit/atomic/switch.h"

#include <QBrush>
#include <QColor>
#include <QEasingCurve>
#include <QEnterEvent>
#include <QFontMetrics>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPen>
#include <QRectF>
#include <Qt>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

Switch::Switch(QWidget* parent)
    : QWidget(parent),
      onText_(QStringLiteral("On")),
      offText_(QStringLiteral("Off")),
      animProgress_(this, "progress"),
      animHover_(this, "hover") {
  setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
  setMouseTracking(true);
  setFocusPolicy(Qt::StrongFocus);
  setCursor(Qt::PointingHandCursor);
  animProgress_.setDuration(160);
  animProgress_.setEasingCurve(QEasingCurve::OutCubic);
  animHover_.setDuration(120);
  animHover_.setEasingCurve(QEasingCurve::OutCubic);
}

void Switch::setChecked(bool checked) {
  if (checked == checked_) {
    return;
  }
  checked_ = checked;
  animProgress_.stop();
  animProgress_.setStartValue(progress_);
  animProgress_.setEndValue(checked_ ? 1.0 : 0.0);
  animProgress_.start();
  emit checkedChanged(checked_);
  emit toggled(checked_);
}

void Switch::setShowText(bool show) {
  showText_ = show;
  updateGeometry();
  update();
}

void Switch::setOnText(const QString& text) {
  onText_ = text;
  update();
}

void Switch::setOffText(const QString& text) {
  offText_ = text;
  update();
}

void Switch::setProgress(double p) {
  progress_ = std::clamp(p, 0.0, 1.0);
  update();
}

void Switch::setHover(double h) {
  hover_ = std::clamp(h, 0.0, 1.0);
  update();
}

QSize Switch::sizeHint() const {
  int w = kTrackWidth;
  if (showText_) {
    QFontMetrics fm(font());
    const int textW =
        std::max(fm.horizontalAdvance(onText_), fm.horizontalAdvance(offText_));
    w += kTextSpacing + textW;
  }
  return QSize(w, std::max(kTrackHeight, fontMetrics().height()));
}

void Switch::paintEvent(QPaintEvent*) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);

  const Palette& palette = Theme::palette();
  const QColor accent = palette.accent;
  const QRectF trackRect(0, (height() - kTrackHeight) / 2.0, kTrackWidth,
                         kTrackHeight);

  QColor offBg = palette.button;
  QColor trackColor(
      static_cast<int>(offBg.red() + (accent.red() - offBg.red()) * progress_),
      static_cast<int>(offBg.green() + (accent.green() - offBg.green()) * progress_),
      static_cast<int>(offBg.blue() + (accent.blue() - offBg.blue()) * progress_),
      255);
  p.setPen(QPen(palette.border, 1));
  p.setBrush(trackColor);
  p.drawRoundedRect(trackRect, kTrackHeight / 2.0, kTrackHeight / 2.0);

  if (hover_ > 0.0) {
    QColor halo = accent;
    halo.setAlphaF(0.15 * hover_);
    p.setPen(Qt::NoPen);
    p.setBrush(halo);
    p.drawRoundedRect(trackRect.adjusted(-2, -2, 2, 2),
                      (kTrackHeight + 4) / 2.0, (kTrackHeight + 4) / 2.0);
  }

  const double knobX = trackRect.left() + 2 +
                       (kTrackWidth - kKnobDiameter - 4) * progress_;
  const double knobY = trackRect.center().y() - kKnobDiameter / 2.0;
  p.setPen(Qt::NoPen);
  p.setBrush(checked_ ? palette.base : palette.windowText);
  p.drawEllipse(QRectF(knobX, knobY, kKnobDiameter, kKnobDiameter));

  if (showText_) {
    p.setPen(palette.windowText);
    p.drawText(QRectF(kTrackWidth + kTextSpacing, 0,
                      width() - kTrackWidth - kTextSpacing, height()),
               Qt::AlignVCenter | Qt::AlignLeft,
               checked_ ? onText_ : offText_);
  }
}

void Switch::mousePressEvent(QMouseEvent* event) {
  if (event->button() == Qt::LeftButton) {
    setChecked(!checked_);
    event->accept();
    return;
  }
  QWidget::mousePressEvent(event);
}

void Switch::keyPressEvent(QKeyEvent* event) {
  if (event->key() == Qt::Key_Space || event->key() == Qt::Key_Return) {
    setChecked(!checked_);
    event->accept();
    return;
  }
  QWidget::keyPressEvent(event);
}

void Switch::enterEvent(QEnterEvent* event) {
  animHover_.stop();
  animHover_.setStartValue(hover_);
  animHover_.setEndValue(1.0);
  animHover_.start();
  QWidget::enterEvent(event);
}

void Switch::leaveEvent(QEvent* event) {
  animHover_.stop();
  animHover_.setStartValue(hover_);
  animHover_.setEndValue(0.0);
  animHover_.start();
  QWidget::leaveEvent(event);
}

}  // namespace sli::toolkit

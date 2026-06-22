#include "sli/toolkit/atomic/time_line_edit.h"

#include <QFont>
#include <QFontMetrics>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QResizeEvent>
#include <QWheelEvent>
#include <QFocusEvent>
#include <QPen>
#include <QRect>
#include <QRectF>
#include <QSize>
#include <QSizePolicy>
#include <Qt>

#include <algorithm>
#include <memory>

#include "sli/toolkit/buttons/state.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// =============================================================================
//  StepButtonOverlayLayer
// =============================================================================

bool TimeLineEdit::StepButtonOverlayLayer::applies(
    const buttons::DrawContext& ctx) const {
  const auto states = ctx.effectiveStates();
  return states.testFlag(buttons::ButtonState::Hovered) ||
         states.testFlag(buttons::ButtonState::Pressed);
}

void TimeLineEdit::StepButtonOverlayLayer::draw(
    const buttons::DrawContext& ctx, const Theme& theme) const {
  const auto states = ctx.effectiveStates();
  QColor color = theme.getColor(QStringLiteral("accent"));
  color.setAlpha(states.testFlag(buttons::ButtonState::Pressed) ? 36 : 22);
  QRectF r = ctx.rect.adjusted(0.0, 0.0, 0.0, -2.0);
  ctx.painter->setPen(Qt::NoPen);
  ctx.painter->setBrush(color);
  ctx.painter->drawRect(r);
}

// =============================================================================
//  TimeLineStepButton
// =============================================================================

void TimeLineEdit::TimeLineStepButton::mousePressEvent(QMouseEvent* event) {
  Button::mousePressEvent(event);
  event->accept();
}

void TimeLineEdit::TimeLineStepButton::mouseReleaseEvent(QMouseEvent* event) {
  Button::mouseReleaseEvent(event);
  event->accept();
}

void TimeLineEdit::TimeLineStepButton::mouseDoubleClickEvent(
    QMouseEvent* event) {
  QWidget::mouseDoubleClickEvent(event);
  event->accept();
}

void TimeLineEdit::TimeLineStepButton::paintEvent(QPaintEvent* event) {
  // Base Button paint (default layers: BackgroundLayer, RippleLayer, Content,
  // etc.)
  Button::paintEvent(event);

  // Overlay on top — semi-transparent accent rect when hovered/pressed.
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);

  buttons::DrawContext ctx;
  ctx.widget = this;
  ctx.painter = &p;
  ctx.rect = QRectF(rect());

  if (!isEnabled()) {
    ctx.states.setFlag(buttons::ButtonState::Disabled, true);
  }
  if (underMouse()) {
    ctx.states.setFlag(buttons::ButtonState::Hovered, true);
  }
  if (isDown()) {
    ctx.states.setFlag(buttons::ButtonState::Pressed, true);
  }

  overlayLayer_.draw(ctx, Theme());
}

// =============================================================================
//  TimeLineEdit
// =============================================================================

TimeLineEdit::TimeLineEdit(const QString& initialTime, QWidget* parent,
                            Qt::Alignment alignment, bool showStepButtons,
                            bool wheelRequiresFocus,
                            const QColor& underlineColor,
                            double underlineThickness,
                            const QColor& focusedUnderlineColor,
                            double focusedUnderlineThickness)
    : CustomLineEdit(parent), wheelScrollPolicy_(wheelRequiresFocus) {
  // Forward parameters to CustomLineEdit.
  if (underlineColor.isValid()) {
    setUnderlineColor(underlineColor);
  }
  if (focusedUnderlineColor.isValid()) {
    setFocusedUnderlineColor(focusedUnderlineColor);
  }
  setUnderlineThickness(underlineThickness);
  Q_UNUSED(focusedUnderlineThickness);

  setObjectName(QStringLiteral("TimeLineEdit"));
  setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
  setPlaceholderText(QStringLiteral("HH:mm"));
  setMaxLength(5);
  showStepButtons_ = showStepButtons;
  lastValidText_ = QStringLiteral("00:05");
  activeStepDelta_ = 0;

  repeatStartTimer_ = new QTimer(this);
  repeatStartTimer_->setSingleShot(true);
  repeatStartTimer_->setInterval(REPEAT_START_DELAY_MS);
  connect(repeatStartTimer_, &QTimer::timeout, this,
          &TimeLineEdit::_start_repeat_timer);

  repeatTimer_ = new QTimer(this);
  repeatTimer_->setInterval(REPEAT_INTERVAL_MS);
  connect(repeatTimer_, &QTimer::timeout, this, &TimeLineEdit::_repeat_step);

  upButton_ = _create_step_button(QStringLiteral("\u25B2"), 1);   // ▲
  downButton_ = _create_step_button(QStringLiteral("\u25BC"), -1);  // ▼

  _sync_text_margins();
  _sync_step_buttons();
  setText(initialTime);

  connect(this, &QLineEdit::editingFinished, this,
          &TimeLineEdit::_normalize_or_restore);
}

// ---- Public API ----

void TimeLineEdit::setStepButtonsVisible(bool visible) {
  showStepButtons_ = visible;
  if (!showStepButtons_) {
    unsetCursor();
  }
  _sync_text_margins();
  _sync_step_buttons();
  updateGeometry();
  update();
}

bool TimeLineEdit::stepButtonsVisible() const { return showStepButtons_; }

void TimeLineEdit::set_step_buttons_visible(bool visible) {
  setStepButtonsVisible(visible);
}

bool TimeLineEdit::step_buttons_visible() const { return stepButtonsVisible(); }

QSize TimeLineEdit::sizeHint() const { return QSize(_content_width(), 32); }

QSize TimeLineEdit::minimumSizeHint() const {
  return QSize(_content_width(), 32);
}

void TimeLineEdit::setText(const QString& text) {
  QString normalized = _normalize_text(text);
  if (normalized.isNull()) {
    normalized = lastValidText_;
  }
  lastValidText_ = normalized;
  CustomLineEdit::setText(normalized);
}

QTime TimeLineEdit::time() const {
  return QTime::fromString(text(), QStringLiteral("HH:mm"));
}

void TimeLineEdit::setTime(const QTime& timeObj) {
  if (timeObj.isValid()) {
    setText(timeObj.toString(QStringLiteral("HH:mm")));
  }
}

// ---- Protected event overrides ----

void TimeLineEdit::paintEvent(QPaintEvent* event) {
  CustomLineEdit::paintEvent(event);

  if (!showStepButtons_) {
    return;
  }

  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  QRect buttonArea = _button_area_rect();
  QColor bg = Theme::getColor(QStringLiteral("accent"));
  bg.setAlpha(isEnabled() ? 22 : 10);
  painter.setPen(Qt::NoPen);
  painter.setBrush(bg);
  painter.drawRect(buttonArea);

  QColor divider = Theme::getColor(QStringLiteral("input.border.thin"));
  divider.setAlpha(
      std::max(32, static_cast<int>(divider.alpha() * 0.75)));
  painter.setPen(QPen(divider, 0.66));
  painter.drawLine(buttonArea.left(), 4, buttonArea.left(), height() - 5);
  painter.drawLine(_down_button_rect().left(), 4,
                   _down_button_rect().left(), height() - 5);
  painter.end();
}

void TimeLineEdit::keyPressEvent(QKeyEvent* event) {
  if (event->key() == Qt::Key_Up) {
    _step_minutes(1);
    event->accept();
    return;
  }
  if (event->key() == Qt::Key_Down) {
    _step_minutes(-1);
    event->accept();
    return;
  }
  const QString txt = event->text();
  if (!txt.isEmpty() && txt.at(0).isDigit()) {
    _insert_digit(txt);
    event->accept();
    return;
  }
  if (txt == QStringLiteral(":")) {
    _insert_colon();
    event->accept();
    return;
  }
  CustomLineEdit::keyPressEvent(event);
}

void TimeLineEdit::resizeEvent(QResizeEvent* event) {
  CustomLineEdit::resizeEvent(event);
  _sync_step_buttons();
}

bool TimeLineEdit::eventFilter(QObject* obj, QEvent* event) {
  if ((obj == upButton_ || obj == downButton_) &&
      (event->type() == QEvent::Leave ||
       event->type() == QEvent::MouseButtonRelease)) {
    _stop_repeat();
  }
  return CustomLineEdit::eventFilter(obj, event);
}

void TimeLineEdit::wheelEvent(QWheelEvent* event) {
  if (!wheelScrollPolicy_.shouldHandleWheelEvent(this, event)) {
    return;
  }

  int delta = event->angleDelta().y();
  if (delta == 0) {
    return;
  }

  _step_minutes(delta > 0 ? 1 : -1);
  event->accept();
}

void TimeLineEdit::focusOutEvent(QFocusEvent* event) {
  _stop_repeat();
  _normalize_or_restore();
  CustomLineEdit::focusOutEvent(event);
}

void TimeLineEdit::setEnabled(bool enabled) {
  CustomLineEdit::setEnabled(enabled);
  _sync_step_buttons();
}

// ---- Private helpers ----

TimeLineEdit::TimeLineStepButton* TimeLineEdit::_create_step_button(
    const QString& text, int delta) {
  Button::Config cfg;
  cfg.text = text;
  cfg.variant = Button::Variant::Ghost;
  cfg.size = QSize(STEP_BUTTON_WIDTH, std::max(1, height()));
  cfg.cornerRadius = 0;

  auto* button = new TimeLineStepButton(cfg, this);
  button->setAttribute(Qt::WA_TranslucentBackground, true);
  button->setAutoFillBackground(false);
  QFont font = button->font();
  font.setPixelSize(STEP_ARROW_SIZE);
  button->setFont(font);
  button->setCursor(Qt::ArrowCursor);

  connect(button, &Button::pressed, this,
          [this, delta]() { _start_step_hold(delta); });
  connect(button, &Button::released, this, &TimeLineEdit::_stop_repeat);
  button->installEventFilter(this);

  return button;
}

void TimeLineEdit::_insert_digit(const QString& digit) {
  const QString sel = selectedText();
  QString current = text();
  int cursor = cursorPosition();
  if (!sel.isEmpty()) {
    int start = selectionStart();
    current = current.left(start) + current.mid(start + sel.length());
    cursor = start;
  }
  const QString proposed =
      current.left(cursor) + digit + current.mid(cursor);
  _apply_edit_candidate(proposed, cursor + 1);
}

void TimeLineEdit::_insert_colon() {
  const QString current = text();
  if (current.contains(QChar(':'))) {
    return;
  }
  int cursor = cursorPosition();
  const QString proposed =
      current.left(cursor) + QStringLiteral(":") + current.mid(cursor);
  _apply_edit_candidate(proposed, cursor + 1);
}

void TimeLineEdit::_apply_edit_candidate(const QString& proposed,
                                         int cursor) {
  const QString p = proposed.left(5);
  if (_is_intermediate(p)) {
    CustomLineEdit::setText(p);
    setCursorPosition(std::min(static_cast<int>(cursor),
                               static_cast<int>(p.length())));
  }
}

void TimeLineEdit::_normalize_or_restore() {
  QString normalized = _normalize_text(text());
  if (normalized.isNull()) {
    normalized = lastValidText_;
  }
  lastValidText_ = normalized;
  if (text() != normalized) {
    CustomLineEdit::setText(normalized);
  }
}

void TimeLineEdit::_step_minutes(int delta) {
  QString normalized = _normalize_text(text());
  if (normalized.isNull()) {
    normalized = lastValidText_;
  }
  QTime timeObj = QTime::fromString(normalized, QStringLiteral("HH:mm"));
  if (!timeObj.isValid()) {
    timeObj = QTime(0, 0);
  }
  setText(timeObj.addSecs(delta * 60).toString(QStringLiteral("HH:mm")));
}

void TimeLineEdit::_start_step_hold(int delta) {
  setFocus(Qt::MouseFocusReason);
  activeStepDelta_ = delta;
  _step_minutes(delta);
  repeatStartTimer_->start();
}

void TimeLineEdit::_start_repeat_timer() {
  if (activeStepDelta_ != 0) {
    repeatTimer_->start();
  }
}

void TimeLineEdit::_repeat_step() {
  if (activeStepDelta_ != 0) {
    _step_minutes(activeStepDelta_);
  }
}

void TimeLineEdit::_stop_repeat() {
  repeatStartTimer_->stop();
  repeatTimer_->stop();
  activeStepDelta_ = 0;
}

void TimeLineEdit::_sync_text_margins() {
  const int stepMargin =
      showStepButtons_ ? STEP_BUTTON_WIDTH * 2 + STEP_BUTTON_GAP : 0;
  setTextMargins(kHPadding, kVPadding, kHPadding + stepMargin, kVPadding);
}

int TimeLineEdit::_content_width() const {
  const int textWidth =
      fontMetrics().horizontalAdvance(QStringLiteral("00:00"));
  const int stepButtons =
      showStepButtons_ ? STEP_BUTTON_WIDTH * 2 + STEP_BUTTON_GAP : 0;
  return std::max(96, textWidth + kHPadding * 2 + stepButtons + 8);
}

QRect TimeLineEdit::_up_button_rect() const {
  const int h = std::max(1, height());
  const int right = width();
  const int left = right - STEP_BUTTON_WIDTH * 2 - STEP_BUTTON_GAP;
  return QRect(left, 0, STEP_BUTTON_WIDTH + STEP_BUTTON_OVERLAP, h);
}

QRect TimeLineEdit::_down_button_rect() const {
  const int h = std::max(1, height());
  const int right = width();
  return QRect(right - STEP_BUTTON_WIDTH, 0, STEP_BUTTON_WIDTH, h);
}

QRect TimeLineEdit::_button_area_rect() const {
  const int left = _up_button_rect().left();
  return QRect(left, 1, std::max(1, width() - left - 1),
               std::max(1, height() - 2));
}

void TimeLineEdit::_sync_step_buttons() {
  for (auto* button : {upButton_, downButton_}) {
    button->setVisible(showStepButtons_);
    button->setEnabled(isEnabled() && showStepButtons_);
  }
  if (showStepButtons_) {
    const QRect upRect = _up_button_rect();
    const QRect downRect = _down_button_rect();
    upButton_->setFixedSize(upRect.size());
    downButton_->setFixedSize(downRect.size());
    upButton_->setGeometry(upRect);
    downButton_->setGeometry(downRect);
  }
}

namespace {

/// Returns true when every character in the string is a digit.
bool allDigits(const QString& s) {
  for (const QChar& c : s) {
    if (!c.isDigit()) return false;
  }
  return true;
}

}  // anonymous namespace

QString TimeLineEdit::_normalize_text(const QString& text) const {
  const QString raw = text.trimmed();
  if (raw.isEmpty()) {
    return lastValidText_;
  }

  int hour = 0;
  int minute = 0;

  if (raw.contains(QChar(':'))) {
    const QStringList parts = raw.split(QChar(':'));
    if (parts.size() != 2) return {};
    if (!allDigits(parts[0]) || !allDigits(parts[1])) return {};
    hour = parts[0].toInt();
    minute = parts[1].toInt();
  } else {
    if (!allDigits(raw)) return {};
    QString padded = raw.rightJustified(4, QChar('0')).right(4);
    hour = padded.left(2).toInt();
    minute = padded.mid(2, 2).toInt();
  }

  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return {};
  }

  return QStringLiteral("%1:%2")
      .arg(hour, 2, 10, QChar('0'))
      .arg(minute, 2, 10, QChar('0'));
}

bool TimeLineEdit::_is_intermediate(const QString& text) const {
  if (text.isEmpty()) return true;

  if (text.count(QChar(':')) > 1) return false;

  if (text.contains(QChar(':'))) {
    const QStringList parts = text.split(QChar(':'));
    if (parts.size() != 2) return false;
    const QString& hour = parts[0];
    const QString& minute = parts[1];
    if (hour.length() > 2 || minute.length() > 2) return false;
    if (!hour.isEmpty() && !allDigits(hour)) return false;
    if (!minute.isEmpty() && !allDigits(minute)) return false;
    return true;
  }

  return text.length() <= 4 && allDigits(text);
}

}  // namespace sli::toolkit
#include "sli/toolkit/composite/flyout.h"

#include <QApplication>
#include <QEvent>
#include <QGraphicsDropShadowEffect>
#include <QHideEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QVBoxLayout>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

QPointer<Flyout> Flyout::activeFlyout_;

Flyout::Flyout(QWidget* parent)
    : QWidget(parent), contentLayout_(new QVBoxLayout(this)) {
  Q_ASSERT(parent != nullptr);
  setObjectName(QStringLiteral("sliFlyout"));
  setAttribute(Qt::WA_TranslucentBackground);
  setFocusPolicy(Qt::StrongFocus);
  setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Preferred);
  contentLayout_->setContentsMargins(12, 12, 12, 12);
  contentLayout_->setSpacing(8);
  auto* shadow = new QGraphicsDropShadowEffect(this);
  shadow->setBlurRadius(16);
  shadow->setOffset(0, 4);
  shadow->setColor(QColor(0, 0, 0, 100));
  setGraphicsEffect(shadow);
  hide();
}

Flyout::~Flyout() {
  if (eventFilterInstalled_ && qApp != nullptr) {
    qApp->removeEventFilter(this);
  }
  if (activeFlyout_ == this) {
    activeFlyout_.clear();
  }
}

void Flyout::addWidget(QWidget* widget) {
  widget->setParent(this);
  contentLayout_->addWidget(widget);
}

void Flyout::showAligned(QWidget* anchor, const QString& anchorPoint,
                         const QString& flyoutPoint, int offset) {
  if (anchor == nullptr) {
    return;
  }
  if (activeFlyout_ != nullptr && activeFlyout_ != this) {
    activeFlyout_->hide();
  }
  activeFlyout_ = this;
  anchor_ = anchor;
  host_ = anchor->window();
  if (parentWidget() != host_) {
    setParent(host_);
  }
  adjustSize();
  const QRect anchorRect(anchor->mapTo(host_, QPoint(0, 0)), anchor->size());
  const QRect flyoutRect(QPoint(0, 0), sizeHint().expandedTo(minimumSizeHint()));
  QPoint position =
      alignedPoint(anchorRect, anchorPoint) - alignedPoint(flyoutRect, flyoutPoint);
  if (anchorPoint.startsWith(QStringLiteral("bottom"))) {
    position.ry() += offset;
  } else if (anchorPoint.startsWith(QStringLiteral("top"))) {
    position.ry() -= offset;
  } else if (anchorPoint.endsWith(QStringLiteral("right"))) {
    position.rx() += offset;
  } else if (anchorPoint.endsWith(QStringLiteral("left"))) {
    position.rx() -= offset;
  }
  const QRect available = host_->rect().adjusted(4, 4, -4, -4);
  position.setX(qBound(available.left(), position.x(),
                       available.right() - width() + 1));
  position.setY(qBound(available.top(), position.y(),
                       available.bottom() - height() + 1));
  move(position);
  show();
  raise();
  setFocus(Qt::PopupFocusReason);
  if (!eventFilterInstalled_ && qApp != nullptr) {
    qApp->installEventFilter(this);
    eventFilterInstalled_ = true;
  }
  emit opened();
}

bool Flyout::eventFilter(QObject* watched, QEvent* event) {
  Q_UNUSED(watched);
  if (!isVisible()) {
    return false;
  }
  if (event->type() == QEvent::WindowDeactivate) {
    hide();
  } else if (event->type() == QEvent::MouseButtonPress) {
    const auto* mouse = static_cast<QMouseEvent*>(event);
    if (!containsGlobal(mouse->globalPosition().toPoint()) &&
        (anchor_ == nullptr ||
         !QRect(anchor_->mapToGlobal(QPoint(0, 0)), anchor_->size())
              .contains(mouse->globalPosition().toPoint()))) {
      hide();
    }
  } else if ((event->type() == QEvent::Move ||
              event->type() == QEvent::Resize) &&
             (watched == anchor_ || watched == host_)) {
    hide();
  }
  return false;
}

void Flyout::keyPressEvent(QKeyEvent* event) {
  if (event->key() == Qt::Key_Escape) {
    hide();
    event->accept();
    return;
  }
  QWidget::keyPressEvent(event);
}

void Flyout::paintEvent(QPaintEvent*) {
  const auto& colors = Theme::palette();
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  painter.setPen(QPen(colors.border, 1.0));
  painter.setBrush(colors.window);
  painter.drawRoundedRect(rect().adjusted(0, 0, -1, -1), 8, 8);
}

void Flyout::hideEvent(QHideEvent* event) {
  if (eventFilterInstalled_ && qApp != nullptr) {
    qApp->removeEventFilter(this);
    eventFilterInstalled_ = false;
  }
  if (activeFlyout_ == this) {
    activeFlyout_.clear();
  }
  emit closed();
  QWidget::hideEvent(event);
}

QPoint Flyout::alignedPoint(const QRect& rect, const QString& spec) {
  const QString normalized = spec.toLower();
  const int x = normalized.contains(QStringLiteral("left"))
                    ? rect.left()
                    : normalized.contains(QStringLiteral("right"))
                          ? rect.right() + 1
                          : rect.center().x();
  const int y = normalized.contains(QStringLiteral("top"))
                    ? rect.top()
                    : normalized.contains(QStringLiteral("bottom"))
                          ? rect.bottom() + 1
                          : rect.center().y();
  return {x, y};
}

bool Flyout::containsGlobal(const QPoint& point) const {
  return QRect(mapToGlobal(QPoint(0, 0)), size()).contains(point);
}

}  // namespace sli::toolkit

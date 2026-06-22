#include "sli/toolkit/atomic/tooltip.h"

#include <QApplication>
#include <QCloseEvent>
#include <QEvent>
#include <QHelpEvent>
#include <QHideEvent>
#include <QMoveEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QResizeEvent>
#include <QStyle>
#include <QWidget>
#include <Qt>

#include <algorithm>

namespace sli::toolkit {

// ===========================================================================
// TooltipBubble
// ===========================================================================

TooltipBubble::TooltipBubble(QWidget* parent)
    : QWidget(parent) {
  if (parent == nullptr) {
    qFatal("TooltipBubble requires an in-window parent widget");
  }

  setWindowFlags(Qt::Widget);
  setAttribute(Qt::WA_TranslucentBackground);

  auto* layout = new QVBoxLayout(this);
  layout->setContentsMargins(kShadowRadius, kShadowRadius,
                              kShadowRadius, kShadowRadius);
  layout->setSpacing(0);

  label_ = new QLabel(this);
  label_->setObjectName(QStringLiteral("TooltipContentWidget"));
  label_->setAttribute(Qt::WA_TransparentForMouseEvents, true);
  layout->addWidget(label_);

  hide();
}

void TooltipBubble::setText(const QString& text) {
  label_->setText(text);
  label_->adjustSize();
  adjustSize();
}

void TooltipBubble::paintEvent(QPaintEvent* /*event*/) {
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  drawRoundedShadow(painter,
                    QRectF(label_->geometry()),
                    kShadowRadius,
                    kContentRadius);
  painter.end();
}

// ===========================================================================
// shouldHandleTooltipWidget (free helper, mirrors _should_handle_tooltip_widget)
// ===========================================================================

bool shouldHandleTooltipWidget(QObject* watched) {
  auto* widget = qobject_cast<QWidget*>(watched);
  if (widget == nullptr)
    return false;
  // Check for the dynamic property `_disable_custom_tooltip`
  if (widget->property("_disable_custom_tooltip").toBool())
    return false;
  if (widget->toolTip().isEmpty())
    return false;
  return true;
}

// ===========================================================================
// TooltipInterceptor  (mirrors _TooltipInterceptor)
// ===========================================================================

bool TooltipInterceptor::eventFilter(QObject* watched, QEvent* event) {
  if (!shouldHandleTooltipWidget(watched))
    return QObject::eventFilter(watched, event);

  const auto tooltipText = static_cast<QWidget*>(watched)->toolTip();

  if (event->type() == QEvent::ToolTip) {
    auto* he = static_cast<QHelpEvent*>(event);
    const QPoint globalPos = he->globalPos();
    PathTooltip::instance().showTooltip(globalPos, tooltipText);
    return true;  // consume the event
  }

  if (event->type() == QEvent::Leave ||
      event->type() == QEvent::Hide ||
      event->type() == QEvent::Close ||
      event->type() == QEvent::MouseButtonPress ||
      event->type() == QEvent::Wheel) {
    PathTooltip::instance().hideTooltip();
  }

  return QObject::eventFilter(watched, event);
}

// ===========================================================================
// ApplicationTooltipInterceptor  (mirrors _ApplicationTooltipInterceptor)
// ===========================================================================

bool ApplicationTooltipInterceptor::eventFilter(QObject* watched,
                                                QEvent* event) {
  if (!shouldHandleTooltipWidget(watched))
    return QObject::eventFilter(watched, event);

  const auto tooltipText = static_cast<QWidget*>(watched)->toolTip();

  if (event->type() == QEvent::ToolTip) {
    auto* he = static_cast<QHelpEvent*>(event);
    const QPoint globalPos = he->globalPos();
    PathTooltip::instance().showTooltip(globalPos, tooltipText);
    return true;
  }

  if (event->type() == QEvent::Leave ||
      event->type() == QEvent::Hide ||
      event->type() == QEvent::Close ||
      event->type() == QEvent::MouseButtonPress ||
      event->type() == QEvent::Wheel ||
      event->type() == QEvent::FocusOut ||
      event->type() == QEvent::WindowDeactivate) {
    PathTooltip::instance().hideTooltip();
  }

  return QObject::eventFilter(watched, event);
}

// ===========================================================================
// Free helper functions  (mirror install_custom_tooltip,
//                         install_application_tooltips,
//                         set_application_tooltips_enabled,
//                         application_tooltips_enabled)
// ===========================================================================

void installCustomTooltip(QWidget* widget) {
  if (widget == nullptr)
    return;
  if (widget->property("_custom_tooltip_installed").toBool())
    return;

  auto* interceptor = new TooltipInterceptor(widget);
  widget->installEventFilter(interceptor);
  widget->setProperty("_custom_tooltip_installed", true);
  widget->setProperty("_custom_tooltip_interceptor",
                      QVariant::fromValue(reinterpret_cast<quintptr>(interceptor)));
}

void installApplicationTooltips(QApplication* app) {
  if (app == nullptr)
    return;
  if (app->property("_custom_tooltip_installed").toBool())
    return;

  auto* interceptor = new ApplicationTooltipInterceptor(app);
  app->installEventFilter(interceptor);
  app->setProperty("_custom_tooltip_installed", true);
  app->setProperty("_custom_tooltip_interceptor",
                   QVariant::fromValue(reinterpret_cast<quintptr>(interceptor)));
}

void setApplicationTooltipsEnabled(bool enabled) {
  PathTooltip::instance().setEnabled(enabled);
}

bool applicationTooltipsEnabled() {
  return PathTooltip::instance().isEnabled();
}

// ===========================================================================
// PathTooltip  (singleton, mirrors Python PathTooltip)
// ===========================================================================

PathTooltip::PathTooltip()
    : QObject(nullptr) {
  showTimer_.setSingleShot(true);
  connect(&showTimer_, &QTimer::timeout,
          this, &PathTooltip::showPendingTooltip);

  // Theme integration: mirror Python's
  //   self.theme_manager.theme_changed.connect(self._apply_style)
  Theme::onThemeChanged(this, [this]() { applyStyle(); });
}

PathTooltip& PathTooltip::instance() {
  static PathTooltip s_instance;
  return s_instance;
}

// ---- helpers ---------------------------------------------------------------

bool PathTooltip::isAlive(QWidget* widget) {
  if (widget == nullptr)
    return false;
  // In Python the code catches RuntimeError; with QPointer the pointer is
  // automatically nulled on deletion, so a null-check suffices.
  // This is equivalent – the object has not been destroyed.
  return true;  // non-null QPointer means alive
}

QWidget* PathTooltip::resolveHost(const QPoint& globalPos) {
  auto* coreApp = QApplication::instance();
  if (coreApp == nullptr)
    return nullptr;

  // QApplication::instance() returns QCoreApplication*; we need QApplication*
  auto* app = qobject_cast<QApplication*>(coreApp);

  auto* widget = QApplication::widgetAt(globalPos);
  if (widget == nullptr && app)
    widget = app->activeWindow();
  if (widget == nullptr && app) {
    const auto widgets = app->topLevelWidgets();
    if (!widgets.isEmpty())
      widget = widgets.last();
  }
  if (widget == nullptr)
    return nullptr;

  return widget->window();
}

TooltipBubble* PathTooltip::ensureLabel(QWidget* host) {
  // Recreate label if it was destroyed
  if (label_.isNull())
    label_.clear();
  if (host_.isNull())
    host_.clear();

  // If we already have a valid label for this host, reuse it
  if (!label_.isNull() && host_.data() == host)
    return label_.data();

  // Remove event filter from previous host
  if (!host_.isNull()) {
    host_.data()->removeEventFilter(this);
  }

  if (label_.isNull()) {
    label_ = new TooltipBubble(host);
    // Mirror Python: label.destroyed.connect(lambda *_: self._clear_label_ref())
    connect(label_.data(), &QObject::destroyed,
            this, &PathTooltip::clearLabelRef);
    label_->hide();
  } else {
    label_->setParent(host);
  }

  host_ = host;
  host_->installEventFilter(this);
  applyStyle();
  return label_.data();
}

void PathTooltip::applyStyle() {
  if (label_.isNull())
    return;
  // Mirror Python: unpolish + polish + update
  label_->label()->style()->unpolish(label_->label());
  label_->label()->style()->polish(label_->label());
  label_->label()->update();
  label_->update();
}

void PathTooltip::clearLabelRef() {
  label_.clear();
  host_.clear();
}

// ---- core tooltip display --------------------------------------------------

void PathTooltip::showNow(const QPoint& pos, const QString& text) {
  if (!enabled_)
    return;
  if (text.isEmpty())
    return;

  auto* host = resolveHost(pos);
  if (host == nullptr)
    return;

  auto* bubble = ensureLabel(host);
  bubble->setText(text);

  QPoint localPos = host->mapFromGlobal(pos) + QPoint(0, 20);
  QRect rect(localPos, bubble->size());
  QRect bounds = host->rect().adjusted(8, 8, -8, -8);

  if (bounds.width() > 0 && bounds.height() > 0) {
    int x = std::max(bounds.left(),
                     std::min(rect.x(), bounds.right() - rect.width() + 1));
    int y = std::max(bounds.top(),
                     std::min(rect.y(), bounds.bottom() - rect.height() + 1));
    rect.moveTo(x, y);
  }

  bubble->setGeometry(rect);
  bubble->show();
  bubble->raise();
}

void PathTooltip::showPendingTooltip() {
  const QPoint pos = pendingPos_;
  const QString text = pendingText_;
  pendingPos_ = QPoint();
  pendingText_.clear();
  pendingDelayMs_ = 0;

  // C++ note: QPoint() is "null" – we use isNull() to detect "no pending".
  if (pos.isNull() || text.isEmpty())
    return;
  showNow(pos, text);
}

void PathTooltip::showTooltip(QPoint pos, const QString& text,
                              std::optional<int> delayMs) {
  if (!enabled_)
    return;
  if (text.isEmpty())
    return;

  const int delay = delayMs.has_value() ? std::max(0, delayMs.value())
                                        : showDelayMs_;

  pendingPos_ = pos;
  pendingText_ = text;
  pendingDelayMs_ = delay;

  if (delay <= 0) {
    showTimer_.stop();
    showPendingTooltip();
    return;
  }

  showTimer_.start(delay);
}

void PathTooltip::hideTooltip() {
  showTimer_.stop();
  pendingPos_ = QPoint();
  pendingText_.clear();
  pendingDelayMs_ = 0;

  if (!label_.isNull()) {
    label_->hide();
  } else {
    label_.clear();
  }
}

void PathTooltip::setEnabled(bool enabled) {
  enabled_ = enabled;
  if (!enabled_)
    hideTooltip();
}

void PathTooltip::setShowDelayMs(int delayMs) {
  showDelayMs_ = std::max(0, delayMs);
}

// ---- event filter (host resize / move / hide / close / leave) --------------

bool PathTooltip::eventFilter(QObject* watched, QEvent* event) {
  if (watched == host_.data()) {
    if (event->type() == QEvent::Resize ||
        event->type() == QEvent::Move ||
        event->type() == QEvent::Hide ||
        event->type() == QEvent::Close ||
        event->type() == QEvent::WindowStateChange ||
        event->type() == QEvent::Leave) {
      hideTooltip();
    }
  }
  return QObject::eventFilter(watched, event);
}

}  // namespace sli::toolkit

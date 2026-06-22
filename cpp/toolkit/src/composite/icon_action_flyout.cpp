#include "sli/toolkit/composite/icon_action_flyout.h"

#include <QEvent>
#include <QGraphicsDropShadowEffect>
#include <QHBoxLayout>
#include <QMouseEvent>
#include <QPainter>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// ===========================================================================
// IconActionFlyout
// ===========================================================================

IconActionFlyout::IconActionFlyout(QWidget* parent,
                                   const QList<IconActionItem>& actions,
                                   int buttonSize, int iconSize)
    : QWidget(parent),
      buttonSize_(buttonSize),
      iconSize_(iconSize) {
  if (parent == nullptr) {
    qFatal("IconActionFlyout requires a parent widget");
  }

  setObjectName(QStringLiteral("sliIconActionFlyout"));
  setWindowFlags(Qt::Widget);
  setAttribute(Qt::WA_TranslucentBackground);
  setFocusPolicy(Qt::StrongFocus);
  setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Preferred);

  // Container surface (mirrors Python BaseFlyout's container/content_layout)
  auto* shadow = new QGraphicsDropShadowEffect(this);
  shadow->setBlurRadius(16);
  shadow->setOffset(0, 4);
  shadow->setColor(QColor(0, 0, 0, 100));
  setGraphicsEffect(shadow);

  // Main vertical layout for this widget
  auto* outerLayout = new QVBoxLayout(this);
  outerLayout->setContentsMargins(0, 0, 0, 0);
  outerLayout->setSpacing(0);

  container_ = new QWidget(this);
  container_->setObjectName(QStringLiteral("FlyoutContainer"));
  container_->setAttribute(Qt::WA_TranslucentBackground);
  outerLayout->addWidget(container_);

  contentLayout_ = new QVBoxLayout(container_);
  contentLayout_->setContentsMargins(12, 12, 12, 12);
  contentLayout_->setSpacing(8);

  hLayout_ = new QHBoxLayout();
  hLayout_->setContentsMargins(0, 0, 0, 0);
  hLayout_->setSpacing(6);
  contentLayout_->addLayout(hLayout_);

  // Auto-hide timer
  autoHideTimer_ = new QTimer(this);
  autoHideTimer_->setSingleShot(true);
  connect(autoHideTimer_, &QTimer::timeout, this, &IconActionFlyout::hide);

  setActions(actions);
  hide();
}

void IconActionFlyout::setActions(const QList<IconActionItem>& actions) {
  // Remove existing buttons
  for (auto it = buttons_.begin(); it != buttons_.end(); ++it) {
    if (!it.value().isNull()) {
      Button* btn = it.value().data();
      btn->removeEventFilter(this);
      hLayout_->removeWidget(btn);
      btn->deleteLater();
    }
  }
  buttons_.clear();
  actions_.clear();

  for (const IconActionItem& spec : actions) {
    Button::Config btnCfg;
    btnCfg.icon = spec.icon;
    btnCfg.variant = Button::Variant::Ghost;
    auto* button = new Button(btnCfg, container_);
    button->setFixedSize(buttonSize_, buttonSize_);
    button->setIconSize(QSize(iconSize_, iconSize_));
    button->setToolTip(spec.tooltip);
    button->setVisible(spec.visible);
    button->setEnabled(spec.enabled);

    connect(button, &Button::clicked, this,
            [this, actionId = spec.actionId]() { triggerAction(actionId); });

    button->installEventFilter(this);
    button->setProperty("element_name", spec.actionId);
    hLayout_->addWidget(button);
    actions_[spec.actionId] = spec;
    buttons_[spec.actionId] = button;
  }

  updateState();
}

Button* IconActionFlyout::actionButton(const QString& actionId) const {
  auto it = buttons_.find(actionId);
  if (it == buttons_.end() || it.value().isNull()) return nullptr;
  return it.value().data();
}

void IconActionFlyout::setActionState(const QString& actionId,
                                      std::optional<QIcon> icon,
                                      std::optional<QString> tooltip,
                                      std::optional<bool> visible,
                                      std::optional<bool> enabled) {
  auto btnIt = buttons_.find(actionId);
  auto specIt = actions_.find(actionId);
  if (btnIt == buttons_.end() || specIt == actions_.end() ||
      btnIt.value().isNull())
    return;

  Button* button = btnIt.value().data();
  IconActionItem& spec = specIt.value();

  if (icon.has_value()) {
    spec.icon = icon.value();
    button->setIcon(icon.value());
  }
  if (tooltip.has_value()) {
    spec.tooltip = tooltip.value();
    button->setToolTip(tooltip.value());
  }
  if (visible.has_value()) {
    spec.visible = visible.value();
    button->setVisible(spec.visible);
  }
  if (enabled.has_value()) {
    spec.enabled = enabled.value();
    button->setEnabled(spec.enabled);
  }
}

bool IconActionFlyout::eventFilter(QObject* obj, QEvent* event) {
  if (event->type() == QEvent::Enter) {
    QString elementName = obj->property("element_name").toString();
    if (!elementName.isEmpty() && elementName != hoveredElement_) {
      hoveredElement_ = elementName;
      emit elementHovered(elementName);
    }
  } else if (event->type() == QEvent::Leave) {
    if (!hoveredElement_.isEmpty()) {
      hoveredElement_.clear();
      emit elementHoverEnded();
    }
  }
  return QWidget::eventFilter(obj, event);
}

void IconActionFlyout::updateState() {
  hLayout_->invalidate();
  hLayout_->activate();
  container_->updateGeometry();
  updateGeometry();
  adjustSize();
}

void IconActionFlyout::triggerAction(const QString& actionId) {
  emit actionTriggered(actionId);
  hide();
}

void IconActionFlyout::showAbove(QWidget* anchor) {
  updateState();
  if (isVisible() && anchorButton_.data() == anchor) {
    hide();
    return;
  }
  anchorButton_ = anchor;
  showAligned(anchor, QStringLiteral("top-center"),
              QStringLiteral("bottom-center"));
}

void IconActionFlyout::showAligned(QWidget* anchorWidget,
                                   const QString& anchorPoint,
                                   const QString& flyoutPoint, int offset) {
  if (anchorWidget == nullptr) return;

  if (isVisible() && anchorButton_.data() == anchorWidget) {
    hide();
    return;
  }

  anchorButton_ = anchorWidget;
  QWidget* host = anchorWidget->window();

  if (parentWidget() != host) {
    setParent(host);
  }

  adjustSize();
  const QRect anchorRect(anchorWidget->mapTo(host, QPoint(0, 0)),
                         anchorWidget->size());
  const QRect flyoutRect(QPoint(0, 0),
                          sizeHint().expandedTo(minimumSizeHint()));

  // Parse alignment points (simplified version of Flyout's alignedPoint)
  auto alignedPoint = [](const QRect& r, const QString& spec) -> QPoint {
    QString s = spec.toLower();
    int x = s.contains(QLatin1String("left"))
                ? r.left()
                : s.contains(QLatin1String("right")) ? r.right() + 1
                                                     : r.center().x();
    int y = s.contains(QLatin1String("top"))
                ? r.top()
                : s.contains(QLatin1String("bottom")) ? r.bottom() + 1
                                                      : r.center().y();
    return {x, y};
  };

  QPoint position = alignedPoint(anchorRect, anchorPoint) -
                    alignedPoint(flyoutRect, flyoutPoint);

  if (anchorPoint.startsWith(QLatin1String("bottom"))) {
    position.ry() += offset;
  } else if (anchorPoint.startsWith(QLatin1String("top"))) {
    position.ry() -= offset;
  } else if (anchorPoint.endsWith(QLatin1String("right"))) {
    position.rx() += offset;
  } else if (anchorPoint.endsWith(QLatin1String("left"))) {
    position.rx() -= offset;
  }

  const QRect available = host->rect().adjusted(4, 4, -4, -4);
  position.setX(qBound(available.left(), position.x(),
                       available.right() - width() + 1));
  position.setY(qBound(available.top(), position.y(),
                       available.bottom() - height() + 1));

  move(position);
  show();
  raise();
  setFocus(Qt::PopupFocusReason);
}

void IconActionFlyout::scheduleAutoHide(int ms) {
  autoHideTimer_->start(ms);
}

void IconActionFlyout::cancelAutoHide() {
  if (autoHideTimer_ != nullptr) {
    autoHideTimer_->stop();
  }
}

void IconActionFlyout::hide() {
  cancelAutoHide();
  QWidget::hide();
}

}  // namespace sli::toolkit
#include "sli/toolkit/composite/toast.h"

#include <QEvent>
#include <QFontMetrics>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QPainter>
#include <QProgressBar>
#include <QStyle>
#include <QVBoxLayout>

#include <algorithm>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// ===========================================================================
// ToastWidget
// ===========================================================================

ToastWidget::ToastWidget(QWidget* parent)
    : QWidget(parent) {
  Q_ASSERT(parent != nullptr);

  setObjectName(QStringLiteral("ToastNotification"));
  setWindowFlags(Qt::Widget);
  setAttribute(Qt::WA_StyledBackground, false);

  hideTimer_ = new QTimer(this);
  hideTimer_->setSingleShot(true);
  connect(hideTimer_, &QTimer::timeout, this, &ToastWidget::hideAndClose);

  rootLayout_ = new QVBoxLayout(this);
  rootLayout_->setContentsMargins(0, 0, 0, 0);
  rootLayout_->setSpacing(0);

  contentWidget_ = new QWidget(this);
  contentWidget_->setObjectName(QStringLiteral("ToastContentWidget"));
  contentWidget_->setAttribute(Qt::WA_StyledBackground, false);
  contentWidget_->setAttribute(Qt::WA_TranslucentBackground, true);

  mainLayout_ = new QVBoxLayout(contentWidget_);
  mainLayout_->setContentsMargins(12, 10, 12, 10);
  mainLayout_->setSpacing(8);

  messageLabel_ = new QLabel();
  messageLabel_->setWordWrap(true);
  messageLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
  mainLayout_->addWidget(messageLabel_);

  actionRow_ = new QWidget(contentWidget_);
  actionRowLayout_ = new QHBoxLayout(actionRow_);
  actionRowLayout_->setContentsMargins(0, 0, 0, 0);
  actionRowLayout_->setSpacing(6);
  actionRowLayout_->addStretch(1);
  actionRow_->hide();
  mainLayout_->addWidget(actionRow_);

  rootLayout_->addWidget(contentWidget_);

  progressContainer_ = new QWidget(this);
  progressContainer_->setObjectName(QStringLiteral("ToastProgressContainer"));
  progressContainer_->setAttribute(Qt::WA_StyledBackground, false);
  progressContainer_->setAttribute(Qt::WA_TranslucentBackground, true);

  progressLayout_ = new QVBoxLayout(progressContainer_);
  progressLayout_->setContentsMargins(12, 0, 12, 10);
  progressLayout_->setSpacing(0);

  progressBar_ = new QProgressBar(progressContainer_);
  progressBar_->setObjectName(QStringLiteral("ToastProgressBar"));
  progressBar_->setTextVisible(false);
  progressBar_->setFixedHeight(6);
  progressBar_->setRange(0, 100);
  progressLayout_->addWidget(progressBar_);
  progressContainer_->hide();
  rootLayout_->addWidget(progressContainer_);

  Theme::onThemeChanged(this, [this]() { onThemeChanged(); });
  applySurfaceState();
}

void ToastWidget::onThemeChanged() {
  repolishSurfaceWidgets();
  adjustSize();
}

void ToastWidget::repolishSurfaceWidgets() {
  QList<QWidget*> widgets = {this, contentWidget_, progressContainer_,
                             progressBar_};
  for (QWidget* w : widgets) {
    if (w == nullptr) continue;
    QStyle* s = w->style();
    s->unpolish(w);
    s->polish(w);
    w->update();
  }
}

void ToastWidget::applySurfaceState() {
  bool hasProgress = !progressContainer_->isHidden();
  contentWidget_->setProperty("hasProgress", hasProgress);
  progressContainer_->setProperty("hasProgress", hasProgress);
  repolishSurfaceWidgets();
}

void ToastWidget::applyContentLayoutState() {
  if (actionRow_->isVisible()) {
    mainLayout_->setContentsMargins(kMarginsWithAction[0],
                                    kMarginsWithAction[1],
                                    kMarginsWithAction[2],
                                    kMarginsWithAction[3]);
    mainLayout_->setSpacing(8);
  } else {
    mainLayout_->setContentsMargins(kMarginsNoAction[0],
                                    kMarginsNoAction[1],
                                    kMarginsNoAction[2],
                                    kMarginsNoAction[3]);
    mainLayout_->setSpacing(0);
  }
}

void ToastWidget::showMessage(const QString& content, int maxWidth,
                              int duration,
                              const QList<ToastConfig>& actions,
                              std::optional<int> progress) {
  setActions(actions);
  applyContentLayoutState();
  setContent(content, maxWidth);
  setProgress(progress);
  adjustSize();
  show();
  applyDuration(duration);
}

void ToastWidget::updateMessage(const QString& content, int maxWidth,
                                bool success, int duration,
                                const QList<ToastConfig>& actions,
                                std::optional<int> progress) {
  if (!actions.isEmpty()) {
    setActions(actions);
  }
  applyContentLayoutState();
  if (!content.isEmpty()) {
    setContent(content, maxWidth);
  } else {
    fitToContent(maxWidth);
  }
  setProgress(progress);
  adjustSize();
  applyDuration(duration);
}

void ToastWidget::setActions(const QList<ToastConfig>& actions) {
  // Remove existing action widgets (keep the stretch at index count()-1)
  while (actionRowLayout_->count() > 1) {
    QLayoutItem* item = actionRowLayout_->takeAt(0);
    if (QWidget* w = item->widget()) {
      w->setParent(nullptr);
      w->deleteLater();
    }
    delete item;
  }
  actionWidgets_.clear();

  for (const ToastConfig& action : actions) {
    if (action.text.isEmpty()) continue;

    Button::Config cfg;
    cfg.text = action.text;
    cfg.icon = action.icon;
    cfg.variant = Button::Variant::Surface;
    cfg.size = QSize(0, 28);
    cfg.density = QStringLiteral("compact");

    auto* button = new Button(cfg, actionRow_);
    connect(button, &Button::clicked, this,
            [this, cb = action.callback, dismiss = action.dismiss]() {
              handleActionClicked(cb, dismiss);
            });

    actionRowLayout_->insertWidget(actionRowLayout_->count() - 1, button, 0,
                                   Qt::AlignLeft);
    actionWidgets_.append(button);
  }

  actionRow_->setVisible(!actionWidgets_.isEmpty());
}

void ToastWidget::setContent(const QString& content, int maxWidth) {
  // The Python version handles QWidget content separately; here content is
  // always a string since C++ doesn't have Python's dynamic typing on this
  // parameter. The string path is the primary use case.
  setMessageText(content, maxWidth);
}

void ToastWidget::setMessageText(const QString& message, int maxWidth) {
  if (customContent_ != nullptr) {
    mainLayout_->removeWidget(customContent_);
    customContent_->setParent(nullptr);
    customContent_->deleteLater();
    customContent_ = nullptr;
  }
  messageLabel_->show();

  int safeMaxWidth = qMax(180, maxWidth);
  QMargins contentMargins = mainLayout_->contentsMargins();
  QMargins progressMargins = progressLayout_->contentsMargins();
  int actionsWidth =
      actionRow_->isVisible() ? actionRow_->sizeHint().width() : 0;

  int textWidth = qMax(80, safeMaxWidth - contentMargins.left() -
                                contentMargins.right());

  QFontMetrics fm(messageLabel_->font());
  QStringList lines = message.contains(QLatin1Char('\n'))
                          ? message.split(QLatin1Char('\n'))
                          : QStringList{message};
  int longestLineWidth = 0;
  for (const QString& line : lines) {
    longestLineWidth = qMax(longestLineWidth, fm.horizontalAdvance(line));
  }
  int desiredTextWidth =
      qMax(80, qMin(textWidth, longestLineWidth + 4));
  int desiredToastWidth = qMin(
      safeMaxWidth,
      std::max({180,
                desiredTextWidth + contentMargins.left() +
                    contentMargins.right() + 4,
                actionsWidth + contentMargins.left() + contentMargins.right(),
                desiredTextWidth + progressMargins.left() +
                    progressMargins.right()}));
  int finalTextWidth = qMax(
      80, desiredToastWidth - contentMargins.left() - contentMargins.right());

  setFixedWidth(desiredToastWidth);
  contentWidget_->setFixedWidth(desiredToastWidth);
  progressContainer_->setFixedWidth(desiredToastWidth);
  messageLabel_->setFixedWidth(finalTextWidth);
  messageLabel_->setText(message);
  actionRow_->setFixedWidth(finalTextWidth);
  messageLabel_->updateGeometry();
  contentWidget_->adjustSize();
  adjustSize();
  updateGeometry();
}

void ToastWidget::fitToContent(int maxWidth) {
  int safeMaxWidth = qMax(180, maxWidth);
  QMargins contentMargins = mainLayout_->contentsMargins();
  QMargins progressMargins = progressLayout_->contentsMargins();

  int contentWidth =
      customContent_ != nullptr
          ? customContent_->sizeHint().width()
          : messageLabel_->sizeHint().width();
  int actionsWidth =
      actionRow_->isVisible() ? actionRow_->sizeHint().width() : 0;

  int desiredToastWidth = qMin(
      safeMaxWidth,
      std::max({180,
                contentWidth + contentMargins.left() + contentMargins.right(),
                actionsWidth + contentMargins.left() + contentMargins.right(),
                contentWidth + progressMargins.left() +
                    progressMargins.right()}));

  setFixedWidth(desiredToastWidth);
  contentWidget_->setFixedWidth(desiredToastWidth);
  progressContainer_->setFixedWidth(desiredToastWidth);
  actionRow_->setFixedWidth(
      qMax(80, desiredToastWidth - contentMargins.left() -
                   contentMargins.right()));
  contentWidget_->adjustSize();
  adjustSize();
  updateGeometry();
}

void ToastWidget::setProgress(std::optional<int> progress) {
  if (!progress.has_value()) {
    progressContainer_->hide();
    applySurfaceState();
    return;
  }
  int safeProgress = qBound(0, progress.value(), 100);
  progressBar_->setValue(safeProgress);
  progressContainer_->show();
  applySurfaceState();
}

void ToastWidget::applyDuration(int duration) {
  hideTimer_->stop();
  if (duration > 0) {
    hideTimer_->start(duration);
  }
}

void ToastWidget::hideAndClose() {
  hideTimer_->stop();
  hide();
  close();
}

void ToastWidget::handleActionClicked(std::function<void()> callback,
                                      bool dismiss) {
  if (callback) {
    callback();
  }
  if (dismiss) {
    hideAndClose();
  }
}

void ToastWidget::paintEvent(QPaintEvent* event) {
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  QRect rect = this->rect().adjusted(0, 0, -1, -1);
  painter.setBrush(QBrush(Theme::getColor(QStringLiteral("toast.background"))));
  painter.setPen(QPen(Theme::getColor(QStringLiteral("toast.border")), 1));
  painter.drawRoundedRect(rect, 8, 8);
  painter.end();
  QWidget::paintEvent(event);
}

void ToastWidget::mousePressEvent(QMouseEvent* event) {
  if (actionRow_->isVisible() &&
      actionRow_->rect().contains(actionRow_->mapFrom(this, event->pos()))) {
    QWidget::mousePressEvent(event);
    return;
  }
  hideAndClose();
  event->accept();
}

// ===========================================================================
// ToastManager
// ===========================================================================

ToastManager::ToastManager(QWidget* parentWindow, QWidget* imageLabel)
    : QObject(parentWindow) {
  QWidget* hostParent = parentWindow;
  if (hostParent == nullptr && imageLabel != nullptr) {
    hostParent = imageLabel->window();
  }
  Q_ASSERT(hostParent != nullptr);

  parentWindow_ = hostParent;
  imageLabel_ = imageLabel;

  if (parentWindow_ != nullptr) {
    parentWindow_->installEventFilter(this);
  }
  if (imageLabel_ != nullptr) {
    imageLabel_->installEventFilter(this);
  }
}

int ToastManager::showToast(const QString& content, int duration,
                            const QList<ToastConfig>& actions,
                            std::optional<int> progress, bool success) {
  int toastId = nextId_++;
  auto* toast = new ToastWidget(parentWindow_);
  toast->setProperty("toastSuccess", success);
  toasts_[toastId] = toast;

  connect(toast, &QObject::destroyed, this,
          [this, toastId]() { toasts_.remove(toastId); });

  toast->showMessage(content, toastMaxWidth(), duration, actions, progress);
  positionToasts();
  toast->show();
  toast->raise();
  QTimer::singleShot(0, this, &ToastManager::positionToasts);
  return toastId;
}

void ToastManager::updateToast(int toastId, const QString& content,
                               bool success, int duration,
                               const QList<ToastConfig>& actions,
                               std::optional<int> progress) {
  auto it = toasts_.find(toastId);
  if (it == toasts_.end() || it.value().isNull()) return;

  ToastWidget* toast = it.value().data();
  toast->setProperty("toastSuccess", success);
  toast->updateMessage(content, toastMaxWidth(), success, duration, actions,
                       progress);
  positionToasts();
  toast->show();
  toast->raise();
  QTimer::singleShot(0, this, &ToastManager::positionToasts);
}

void ToastManager::closeToast(int toastId) {
  auto it = toasts_.find(toastId);
  if (it == toasts_.end()) return;
  if (!it.value().isNull()) {
    it.value()->hideAndClose();
  }
  toasts_.remove(toastId);
}

int ToastManager::toastMaxWidth() const {
  if (imageLabel_ != nullptr) {
    return qMax(260, static_cast<int>(imageLabel_->width() * 0.42));
  }
  if (parentWindow_ != nullptr) {
    return qMax(260, static_cast<int>(parentWindow_->width() * 0.35));
  }
  return 360;
}

void ToastManager::positionToasts() {
  if (parentWindow_.isNull()) return;

  QPoint anchorPoint(0, 0);
  if (imageLabel_ != nullptr) {
    anchorPoint = imageLabel_->mapTo(parentWindow_, QPoint(0, 0));
  }

  int atX = anchorPoint.x() + spacing_;
  int atY = anchorPoint.y() + spacing_;

  for (auto it = toasts_.begin(); it != toasts_.end(); ++it) {
    if (it.value().isNull()) continue;
    ToastWidget* toast = it.value().data();
    if (!toast->isVisible()) continue;
    toast->setGeometry(QRect(atX, atY, toast->width(), toast->height()));
    toast->raise();
    atY += toast->height() + spacing_;
  }
}

bool ToastManager::eventFilter(QObject* watched, QEvent* event) {
  if ((watched == parentWindow_.data() ||
       watched == imageLabel_.data()) &&
      (event->type() == QEvent::Resize ||
       event->type() == QEvent::Move ||
       event->type() == QEvent::Show ||
       event->type() == QEvent::WindowStateChange ||
       event->type() == QEvent::LayoutRequest)) {
    QTimer::singleShot(0, this, &ToastManager::positionToasts);
  }
  return false;
}

}  // namespace sli::toolkit
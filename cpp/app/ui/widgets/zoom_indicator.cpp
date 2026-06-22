#include "ui/widgets/zoom_indicator.h"

#include "ui/icon_manager.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QSize>

#include <cmath>

namespace imgsli::app::ui::widgets {

ZoomIndicator::ZoomIndicator(QWidget* parent, PrefixProvider prefixProvider,
                             QWidget* target)
    : RoundedOverlayWidget(parent, QColor(0, 0, 0, 140), 6.0),
      prefixProvider_(std::move(prefixProvider)),
      target_(target) {
  setObjectName(QStringLiteral("ZoomIndicator"));
  auto* layout = new QHBoxLayout(this);
  layout->setContentsMargins(6, 2, 4, 2);
  layout->setSpacing(4);

  label_ = new QLabel(QStringLiteral("100%"), this);
  layout->addWidget(label_);

  resetButton_ = new QPushButton(this);
  resetButton_->setIcon(getAppIcon(AppIcon::Sync));
  resetButton_->setFixedSize(QSize(22, 22));
  resetButton_->setToolTip(QStringLiteral("Reset zoom"));
  resetButton_->setFlat(true);
  layout->addWidget(resetButton_);

  adjustSize();
  hide();
  updateZoom(1.0);
}

void ZoomIndicator::setTarget(QWidget* target) {
  target_ = target;
  syncPosition();
}

void ZoomIndicator::updateZoom(double zoom, double panX, double panY) {
  const int percent = static_cast<int>(std::round(zoom * 100.0));
  const QString prefix = prefixProvider_ ? prefixProvider_() : QStringLiteral("Zoom");
  label_->setText(QStringLiteral("%1: %2%").arg(prefix).arg(percent));
  adjustSize();

  const bool visible =
      std::abs(zoom - 1.0) > 1e-3 || std::abs(panX) > 1e-4 || std::abs(panY) > 1e-4;
  setVisible(visible);
  if (visible) {
    syncPosition();
    raise();
  }
}

void ZoomIndicator::syncPosition() {
  if (!isVisible() || !target_) {
    return;
  }
  const QRect targetGeo = target_->geometry();
  constexpr int margin = 8;
  const int x = targetGeo.right() - width() - margin;
  const int y = targetGeo.top() + margin;
  move(x, y);
  raise();
}

}  // namespace imgsli::app::ui::widgets

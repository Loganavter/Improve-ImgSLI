#include "sli/toolkit/composite/toolbar.h"

#include <QHBoxLayout>
#include <QPainter>

#include "sli/toolkit/atomic/divider.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

Toolbar::Toolbar(QWidget* parent)
    : QWidget(parent), layout_(new QHBoxLayout(this)) {
  setObjectName(QStringLiteral("sliToolbar"));
  setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  layout_->setContentsMargins(8, 6, 8, 6);
  layout_->setSpacing(6);
}

void Toolbar::addWidget(QWidget* widget, int stretch) {
  layout_->addWidget(widget, stretch);
}

void Toolbar::addSeparator() {
  layout_->addWidget(new Divider(Qt::Vertical, this));
}

void Toolbar::addStretch(int stretch) {
  layout_->addStretch(stretch);
}

void Toolbar::paintEvent(QPaintEvent*) {
  const auto& colors = Theme::palette();
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  painter.setPen(QPen(colors.border, 1.0));
  painter.setBrush(colors.button);
  painter.drawRoundedRect(rect().adjusted(0, 0, -1, -1), 8, 8);
}

}  // namespace sli::toolkit

#include "ui/widgets/startup_placeholder.h"

#include <QLabel>
#include <QPalette>
#include <QVBoxLayout>

namespace imgsli::app::ui::widgets {

StartupPlaceholder::StartupPlaceholder(QWidget* parent, QWidget* target)
    : QWidget(parent), target_(target) {
  setObjectName(QStringLiteral("ImageStartupPlaceholder"));
  setAttribute(Qt::WA_StyledBackground, true);
  setAttribute(Qt::WA_TransparentForMouseEvents, true);

  auto* layout = new QVBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(0);
  layout->addStretch(1);

  label_ = new QLabel(QString(), this);
  label_->setAlignment(Qt::AlignCenter);
  label_->hide();
  layout->addWidget(label_, 0, Qt::AlignCenter);
  layout->addStretch(1);

  syncGeometry();
  show();
  raise();
}

void StartupPlaceholder::setTarget(QWidget* target) {
  target_ = target;
  syncGeometry();
}

void StartupPlaceholder::setText(const QString& text) {
  label_->setText(text);
  label_->setVisible(!text.isEmpty());
}

void StartupPlaceholder::setBackgroundColor(const QColor& color) {
  QPalette pal = palette();
  pal.setColor(QPalette::Window, color);
  pal.setColor(QPalette::Base, color);
  setPalette(pal);
  setAutoFillBackground(true);
  update();
}

void StartupPlaceholder::syncGeometry() {
  if (!target_) {
    return;
  }
  setGeometry(target_->geometry());
  raise();
}

}  // namespace imgsli::app::ui::widgets

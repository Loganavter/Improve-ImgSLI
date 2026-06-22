#include "sli/toolkit/atomic/section_header.h"

#include <QLabel>
#include <QVBoxLayout>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

SectionHeader::SectionHeader(const QString& title,
                             const QString& description, QWidget* parent)
    : QWidget(parent),
      titleLabel_(new QLabel(title, this)),
      descriptionLabel_(new QLabel(description, this)) {
  setObjectName(QStringLiteral("sliSectionHeader"));
  auto* layout = new QVBoxLayout(this);
  layout->setContentsMargins(0, 4, 0, 4);
  layout->setSpacing(2);

  QFont titleFont = titleLabel_->font();
  titleFont.setBold(true);
  titleFont.setPointSizeF(titleFont.pointSizeF() * 1.08);
  titleLabel_->setFont(titleFont);
  titleLabel_->setObjectName(QStringLiteral("sliSectionHeaderTitle"));
  layout->addWidget(titleLabel_);

  descriptionLabel_->setObjectName(
      QStringLiteral("sliSectionHeaderDescription"));
  descriptionLabel_->setWordWrap(true);
  QPalette descriptionPalette = descriptionLabel_->palette();
  QColor secondary = Theme::palette().windowText;
  secondary.setAlpha(170);
  descriptionPalette.setColor(QPalette::WindowText, secondary);
  descriptionLabel_->setPalette(descriptionPalette);
  descriptionLabel_->setVisible(!description.isEmpty());
  layout->addWidget(descriptionLabel_);
}

QString SectionHeader::title() const {
  return titleLabel_->text();
}

void SectionHeader::setTitle(const QString& title) {
  titleLabel_->setText(title);
}

QString SectionHeader::description() const {
  return descriptionLabel_->text();
}

void SectionHeader::setDescription(const QString& description) {
  descriptionLabel_->setText(description);
  descriptionLabel_->setVisible(!description.isEmpty());
}

}  // namespace sli::toolkit

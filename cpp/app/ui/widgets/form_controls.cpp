#include "ui/widgets/form_controls.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QVBoxLayout>

namespace imgsli::app::ui::widgets {

DialogActionBar::DialogActionBar(const QString& primaryText,
                                 const QString& secondaryText, QWidget* parent,
                                 const QSize& primaryMinSize,
                                 const QSize& secondaryMinSize)
    : QWidget(parent) {
  auto* layout = new QHBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(8);
  layout->addStretch();

  secondary_ = new QPushButton(secondaryText, this);
  secondary_->setMinimumSize(secondaryMinSize);
  primary_ = new QPushButton(primaryText, this);
  primary_->setMinimumSize(primaryMinSize);

  layout->addWidget(secondary_);
  layout->addWidget(primary_);
}

OutputPathSection::OutputPathSection(const Labels& labels, QWidget* parent)
    : QWidget(parent) {
  auto* layout = new QVBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(6);

  dirLabel_ = new QLabel(labels.directoryLabel, this);

  auto* row = new QWidget(this);
  auto* rowLayout = new QHBoxLayout(row);
  rowLayout->setContentsMargins(0, 0, 0, 0);
  rowLayout->setSpacing(6);

  dirEdit_ = new QLineEdit(this);
  browseButton_ = new QPushButton(labels.browseText, this);
  rowLayout->addWidget(dirEdit_, 1);
  rowLayout->addWidget(browseButton_);

  auto* favRow = new QWidget(this);
  auto* favLayout = new QHBoxLayout(favRow);
  favLayout->setContentsMargins(0, 0, 0, 0);
  favLayout->setSpacing(6);
  setFavoriteButton_ = new QPushButton(labels.setFavoriteText, this);
  useFavoriteButton_ = new QPushButton(labels.useFavoriteText, this);
  favLayout->addWidget(setFavoriteButton_);
  favLayout->addWidget(useFavoriteButton_);

  filenameLabel_ = new QLabel(labels.filenameLabel, this);
  filenameEdit_ = new QLineEdit(this);

  layout->addWidget(dirLabel_);
  layout->addWidget(row);
  layout->addWidget(favRow);
  layout->addWidget(filenameLabel_);
  layout->addWidget(filenameEdit_);
}

}  // namespace imgsli::app::ui::widgets

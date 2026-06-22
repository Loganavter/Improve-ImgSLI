#include "sli/toolkit/buttons/chip_group.h"

#include <QButtonGroup>
#include <QKeyEvent>
#include <QHBoxLayout>

#include "sli/toolkit/buttons/button.h"

namespace sli::toolkit {

ChipGroup::ChipGroup(QWidget* parent)
    : QWidget(parent),
      layout_(new QHBoxLayout(this)),
      group_(new QButtonGroup(this)) {
  setObjectName(QStringLiteral("sliChipGroup"));
  layout_->setContentsMargins(0, 0, 0, 0);
  layout_->setSpacing(4);
  group_->setExclusive(true);
  connect(group_, &QButtonGroup::buttonClicked, this,
          [this](QAbstractButton* button) {
            emit currentChanged(button->property("chipId").toString());
          });
}

Button* ChipGroup::addChip(const QString& id, const QString& text) {
  if (id.isEmpty() || chips_.contains(id)) {
    return chips_.value(id);
  }
  auto* chip = new Button(text, Button::Variant::Default, this);
  chip->setCheckable(true);
  chip->setProperty("chipId", id);
  chip->setObjectName(QStringLiteral("sliChip_%1").arg(id));
  chip->installEventFilter(this);
  group_->addButton(chip);
  layout_->addWidget(chip);
  chips_.insert(id, chip);
  if (chips_.size() == 1) {
    chip->setChecked(true);
  }
  return chip;
}

bool ChipGroup::removeChip(const QString& id) {
  Button* chip = chips_.take(id);
  if (chip == nullptr) {
    return false;
  }
  const bool wasChecked = chip->isChecked();
  group_->removeButton(chip);
  layout_->removeWidget(chip);
  chip->deleteLater();
  if (wasChecked && !chips_.isEmpty()) {
    setCurrentId(ids().constFirst());
  }
  return true;
}

QString ChipGroup::currentId() const {
  QAbstractButton* checked = group_->checkedButton();
  return checked == nullptr ? QString()
                            : checked->property("chipId").toString();
}

bool ChipGroup::setCurrentId(const QString& id) {
  Button* chip = chips_.value(id);
  if (chip == nullptr) {
    return false;
  }
  if (!chip->isChecked()) {
    chip->setChecked(true);
    emit currentChanged(id);
  }
  return true;
}

QStringList ChipGroup::ids() const {
  QStringList result;
  result.reserve(layout_->count());
  for (int i = 0; i < layout_->count(); ++i) {
    if (auto* chip = qobject_cast<Button*>(layout_->itemAt(i)->widget())) {
      result.append(chip->property("chipId").toString());
    }
  }
  return result;
}

bool ChipGroup::eventFilter(QObject* watched, QEvent* event) {
  if (event->type() == QEvent::KeyPress &&
      qobject_cast<Button*>(watched) != nullptr) {
    auto* key = static_cast<QKeyEvent*>(event);
    if (key->key() == Qt::Key_Left || key->key() == Qt::Key_Up) {
      moveCurrent(-1);
      return true;
    }
    if (key->key() == Qt::Key_Right || key->key() == Qt::Key_Down) {
      moveCurrent(1);
      return true;
    }
  }
  return QWidget::eventFilter(watched, event);
}

void ChipGroup::moveCurrent(int delta) {
  const QStringList orderedIds = ids();
  if (orderedIds.isEmpty()) {
    return;
  }
  int index = orderedIds.indexOf(currentId());
  if (index < 0) {
    index = 0;
  }
  index = (index + delta + orderedIds.size()) % orderedIds.size();
  if (setCurrentId(orderedIds[index])) {
    chips_.value(orderedIds[index])->setFocus();
  }
}

}  // namespace sli::toolkit

#include "sli/toolkit/list_items/editable_list_item.h"

#include <QHBoxLayout>
#include <QVariant>

#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/buttons/button.h"

namespace sli::toolkit {

EditableListItem::EditableListItem(
    const QString& text,
    bool enabled,
    const QString& placeholder,
    const QString& checkboxTooltip,
    const QIcon& deleteIcon,
    const QString& deleteTooltip,
    QWidget* parent
)
    : QWidget(parent)
{
    layout_ = new QHBoxLayout(this);
    layout_->setContentsMargins(0, 2, 0, 2);
    layout_->setSpacing(8);

    inputField_ = new CustomLineEdit(this);
    inputField_->setText(text);
    if (!placeholder.isEmpty()) {
        inputField_->setPlaceholderText(placeholder);
    }
    layout_->addWidget(inputField_, 1);

    checkBox_ = new CheckBox(QString(), this);
    checkBox_->setChecked(enabled);
    checkBox_->setMinimumSize(28, 28);
    if (!checkboxTooltip.isEmpty()) {
        checkBox_->setToolTip(checkboxTooltip);
    }
    layout_->addWidget(checkBox_);

    Button::Config cfg;
    cfg.icon = deleteIcon;
    cfg.size = QSize(28, 28);
    cfg.iconSize = 16;
    cfg.variant = Button::Variant::Surface;
    deleteBtn_ = new Button(cfg, this);
    if (!deleteTooltip.isEmpty()) {
        deleteBtn_->setToolTip(deleteTooltip);
    }
    connect(deleteBtn_, &Button::clicked, this, &EditableListItem::deleteClicked);
    layout_->addWidget(deleteBtn_);
}

QString EditableListItem::getText() const {
    return inputField_->text().trimmed();
}

bool EditableListItem::isEnabledChecked() const {
    return checkBox_->isChecked();
}

QMap<QString, QVariant> EditableListItem::getValueData() const {
    QMap<QString, QVariant> data;
    data[QStringLiteral("value")] = getText();
    data[QStringLiteral("enabled")] = isEnabledChecked();
    return data;
}

}  // namespace sli::toolkit
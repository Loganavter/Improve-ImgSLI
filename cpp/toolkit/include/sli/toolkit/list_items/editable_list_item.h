#pragma once

#include <QHBoxLayout>
#include <QString>
#include <QWidget>

#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/buttons/button.h"

namespace sli::toolkit {

class EditableListItem final : public QWidget {
    Q_OBJECT

public:
    explicit EditableListItem(
        const QString& text = {},
        bool enabled = true,
        const QString& placeholder = {},
        const QString& checkboxTooltip = {},
        const QIcon& deleteIcon = QIcon::fromTheme(QStringLiteral("edit-delete")),
        const QString& deleteTooltip = {},
        QWidget* parent = nullptr
    );

    QString getText() const;
    bool isEnabledChecked() const;

    /// Returns a dict-like map matching Python's get_value_data().
    /// Keys: "value" -> text, "enabled" -> checkbox state.
    QMap<QString, QVariant> getValueData() const;

    // Public child access (mirrors Python exposing self.input_field etc.)
    CustomLineEdit* inputField() const { return inputField_; }
    CheckBox* checkBox() const { return checkBox_; }
    Button* deleteButton() const { return deleteBtn_; }

signals:
    void deleteClicked();

private:
    QHBoxLayout* layout_ = nullptr;
    CustomLineEdit* inputField_ = nullptr;
    CheckBox* checkBox_ = nullptr;
    Button* deleteBtn_ = nullptr;
};

}  // namespace sli::toolkit
#pragma once

#include <QString>
#include <QTextEdit>
#include <QWidget>

#include "sli/toolkit/atomic/custom_group_widget.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"

class QHBoxLayout;
class QVBoxLayout;
class QWheelEvent;

namespace sli::toolkit {

// -----------------------------------------------------------------------
// NonPropagatingTextEdit — QTextEdit that does not propagate wheel events
// when scrolled to an edge.  Mirrors Python NonPropagatingTextEdit 1:1.
// -----------------------------------------------------------------------
class NonPropagatingTextEdit : public QTextEdit {
    Q_OBJECT

public:
    using QTextEdit::QTextEdit;

protected:
    void wheelEvent(QWheelEvent* event) override;
};

// -----------------------------------------------------------------------
// PreviewPanel — collapsible preview panel with title, text view, and
// optional action buttons.  Mirrors Python PreviewPanel 1:1.
// -----------------------------------------------------------------------
class PreviewPanel : public QWidget {
    Q_OBJECT

public:
    explicit PreviewPanel(const QString& title,
                          bool showActions = false,
                          const QString& editText = QStringLiteral("Edit"),
                          const QString& saveText = QStringLiteral("Save"),
                          const QString& revertText = QStringLiteral("Revert"),
                          QWidget* parent = nullptr);

    void setTitle(const QString& text);
    void setActionTexts(const QString& edit, const QString& save,
                        const QString& revert);
    void setActionsVisible(bool visible);
    void setEditMode(bool enabled);

    NonPropagatingTextEdit* textView() const { return textView_; }
    TitleWidgetProxy* titleProxy() const { return titleProxy_; }
    Button* editButton() const { return editButton_; }
    Button* saveButton() const { return saveButton_; }
    Button* revertButton() const { return revertButton_; }

    // Direct access to the document for programmatic content setting
    void setPlainText(const QString& text) { textView_->setPlainText(text); }
    QString toPlainText() const { return textView_->toPlainText(); }

private:
    void applyStyles();

    CustomGroupWidget* group_ = nullptr;
    TitleWidgetProxy* titleProxy_ = nullptr;
    NonPropagatingTextEdit* textView_ = nullptr;
    Button* editButton_ = nullptr;
    Button* saveButton_ = nullptr;
    Button* revertButton_ = nullptr;
    QHBoxLayout* actionsLayout_ = nullptr;
};

}  // namespace sli::toolkit

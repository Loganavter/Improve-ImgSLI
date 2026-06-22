#include <QHBoxLayout>
#include <QScrollBar>
#include <QStyle>
#include <QVBoxLayout>
#include <QWheelEvent>

#include "sli/toolkit/composite/preview_panel.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// =======================================================================
// NonPropagatingTextEdit
// =======================================================================
void NonPropagatingTextEdit::wheelEvent(QWheelEvent* event) {
    auto* sbar = verticalScrollBar();
    bool atTop = sbar->value() == sbar->minimum();
    bool atBottom = sbar->value() == sbar->maximum();

    bool scrollingDown = event->angleDelta().y() < 0;
    bool scrollingUp = event->angleDelta().y() > 0;

    if ((scrollingUp && atTop) || (scrollingDown && atBottom)) {
        event->accept();
        return;
    }

    QTextEdit::wheelEvent(event);
}

// =======================================================================
// PreviewPanel
// =======================================================================
PreviewPanel::PreviewPanel(const QString& title,
                           bool showActions,
                           const QString& editText,
                           const QString& saveText,
                           const QString& revertText,
                           QWidget* parent)
    : QWidget(parent) {

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);

    // Create styled group — mirrors Python CustomGroupBuilder.create_styled_group(title)
    auto [group, groupLayout, titleProxy] =
        CustomGroupBuilder::createStyledGroup(title);
    group_ = group;
    // TitleWidgetProxy from structured binding is a stack temporary — heap-allocate
    // a copy so it outlives the constructor.
    titleProxy_ = new TitleWidgetProxy(titleProxy);
    group_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    layout->addWidget(group_, 1);

    // Text view
    textView_ = new NonPropagatingTextEdit();
    textView_->setObjectName(QStringLiteral("previewTextEdit"));
    textView_->setFrameShape(QFrame::NoFrame);
    textView_->setReadOnly(true);
    textView_->setTextInteractionFlags(Qt::NoTextInteraction);
    textView_->viewport()->setCursor(Qt::ArrowCursor);
    textView_->setVerticalScrollBar(
        new unified_flyout::MinimalistScrollBar(textView_));
    textView_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

    groupLayout->addWidget(textView_, 1);

    // Action buttons
    editButton_ = new Button(Button::Config{
        .text = editText,
        .variant = Button::Variant::Surface,
    });
    saveButton_ = new Button(Button::Config{
        .text = saveText,
        .variant = Button::Variant::Surface,
    });
    revertButton_ = new Button(Button::Config{
        .text = revertText,
        .variant = Button::Variant::Surface,
    });

    actionsLayout_ = new QHBoxLayout();
    actionsLayout_->addWidget(editButton_);
    actionsLayout_->addWidget(saveButton_);
    actionsLayout_->addWidget(revertButton_);
    groupLayout->addLayout(actionsLayout_);

    setActionsVisible(showActions);

    Theme::onThemeChanged(this, [this]() { applyStyles(); });
    applyStyles();
}

void PreviewPanel::setTitle(const QString& text) {
    if (titleProxy_)
        titleProxy_->setText(text);
}

void PreviewPanel::setActionTexts(const QString& edit, const QString& save,
                                   const QString& revert) {
    editButton_->setText(edit);
    saveButton_->setText(save);
    revertButton_->setText(revert);
}

void PreviewPanel::setActionsVisible(bool visible) {
    editButton_->setVisible(visible);
    saveButton_->setVisible(visible);
    revertButton_->setVisible(visible);
}

void PreviewPanel::setEditMode(bool enabled) {
    textView_->setReadOnly(!enabled);
    if (enabled) {
        textView_->setTextInteractionFlags(Qt::TextEditorInteraction);
        textView_->viewport()->setCursor(Qt::IBeamCursor);
    } else {
        textView_->setTextInteractionFlags(Qt::NoTextInteraction);
        textView_->viewport()->setCursor(Qt::ArrowCursor);
    }

    editButton_->setEnabled(!enabled);
    saveButton_->setEnabled(enabled);
    revertButton_->setEnabled(enabled);
}

void PreviewPanel::applyStyles() {
    QColor text = Theme::getColor(QStringLiteral("dialog.text"));
    QColor bg = Theme::getColor(QStringLiteral("dialog.input.background"));
    QColor border = Theme::getColor(QStringLiteral("input.border.thin"));

    textView_->setStyleSheet(
        QStringLiteral(
            "QTextEdit#previewTextEdit {"
            "  background: %1;"
            "  border: 1px solid %2;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "  color: %3;"
            "}"
            "QTextEdit#previewTextEdit QAbstractScrollArea::viewport {"
            "  background: transparent;"
            "  border-radius: 6px;"
            "}")
            .arg(bg.name(QColor::HexArgb),
                 border.name(QColor::HexArgb),
                 text.name()));
}

}  // namespace sli::toolkit

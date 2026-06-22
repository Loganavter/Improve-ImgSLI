#include "sli/toolkit/overlays/choice_overlay.h"

#include <QIcon>

#include "sli/toolkit/buttons/button.h"

namespace sli::toolkit {

ChoiceOverlay::ChoiceOverlay(
    QWidget* parent,
    QWidget* anchor,
    int buttonSize,
    int cancelSize,
    int spacing,
    int cornerRadius
)
    : TopLevelInWindowOverlay(
          parent,
          anchor,
          true,   // closeOnBackground
          true,   // closeOnEscape
          true,   // closeOnDeactivate
          buttonSize / 2 + spacing + cancelSize / 2  // defaultDistance
      )
    , buttonSize_(buttonSize)
    , cancelSize_(cancelSize)
    , cornerRadius_(cornerRadius)
{
    connect(this, &TopLevelInWindowOverlay::dismissed,
            this, &ChoiceOverlay::onCancel);
}

Button* ChoiceOverlay::addChoice(
    const QString& key,
    OverlaySlot slot,
    const QString& label,
    const QIcon& icon
) {
    Button::Config cfg;
    cfg.text = label;
    cfg.icon = icon;
    cfg.size = QSize(buttonSize_, buttonSize_);
    cfg.cornerRadius = cornerRadius_;
    cfg.variant = Button::Variant::Surface;

    auto* btn = new Button(cfg, this);
    connect(btn, &Button::clicked, this, [this, key]() { onChosen(key); });

    choiceButtons_.insert(key, btn);
    addWidget(btn, key, slot);
    return btn;
}

Button* ChoiceOverlay::setCancel(bool enabled, const QIcon& icon) {
    if (cancelButton_) {
        removeWidget(cancelButton_);
        cancelButton_->deleteLater();
        cancelButton_ = nullptr;
    }
    if (!enabled)
        return nullptr;

    Button::Config cfg;
    cfg.icon = icon;
    cfg.text = icon.isNull() ? QStringLiteral("x") : QString();
    cfg.size = QSize(cancelSize_, cancelSize_);
    cfg.cornerRadius = cancelSize_ / 2;
    cfg.variant = Button::Variant::Ghost;

    cancelButton_ = new Button(cfg, this);
    connect(cancelButton_, &Button::clicked, this, &ChoiceOverlay::onCancel);
    addWidget(cancelButton_, QStringLiteral("cancel"), OverlaySlot::CENTER, 0);
    return cancelButton_;
}

QMap<QString, Button*> ChoiceOverlay::buttons() const {
    return choiceButtons_;
}

void ChoiceOverlay::showModal() {
    showOverlay();
}

void ChoiceOverlay::onChosen(const QString& key) {
    emit chosen(key);
    dismiss(false);
}

void ChoiceOverlay::onCancel() {
    emit cancelled();
    dismiss(false);
}

}  // namespace sli::toolkit
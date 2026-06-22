#pragma once

/// @deprecated Use TopLevelInWindowOverlay directly for new overlays.
/// ChoiceOverlay is a deprecated directional button choice helper.
/// Replaced by TopLevelInWindowOverlay with Button or other child widgets instead.

#include <QMap>
#include <QString>
#include <QWidget>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/overlays/in_window_overlay.h"

namespace sli::toolkit {

/// Deprecated directional button choice helper.
///
/// @deprecated Use TopLevelInWindowOverlay with Button or other child
/// widgets instead.
class [[deprecated("Use TopLevelInWindowOverlay with Button or other child "
                    "widgets instead")]]
ChoiceOverlay final : public TopLevelInWindowOverlay {
    Q_OBJECT

public:
    explicit ChoiceOverlay(
        QWidget* parent,
        QWidget* anchor = nullptr,
        int buttonSize = 120,
        int cancelSize = 60,
        int spacing = 20,
        int cornerRadius = 10
    );

    /// Add a choice button at the given slot.
    Button* addChoice(
        const QString& key,
        OverlaySlot slot,
        const QString& label = {},
        const QIcon& icon = {}
    );

    /// Set or remove the cancel button.
    Button* setCancel(bool enabled = true, const QIcon& icon = {});

    /// Returns a copy of the internal choice buttons map.
    QMap<QString, Button*> buttons() const;

    /// Convenience: show the overlay.
    void showModal();

signals:
    void chosen(const QString& key);
    void cancelled();

private slots:
    void onChosen(const QString& key);
    void onCancel();

private:
    int buttonSize_ = 120;
    int cancelSize_ = 60;
    int cornerRadius_ = 10;
    QMap<QString, Button*> choiceButtons_;
    Button* cancelButton_ = nullptr;
};

}  // namespace sli::toolkit
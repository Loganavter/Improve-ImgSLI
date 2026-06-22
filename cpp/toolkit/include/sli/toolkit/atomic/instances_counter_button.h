#pragma once

#include <QString>
#include <QWidget>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/helpers/wheel_scroll_policy.h"

namespace sli::toolkit {

/// Segmented add/remove counter built on Button regions.
/// Mirrors Python atomic/instances_counter_button.py.
class InstancesCounterButton final : public Button {
    Q_OBJECT

public:
    explicit InstancesCounterButton(
        QWidget* parent = nullptr,
        bool wheelRequiresFocus = false);

    void setCount(int count);
    void setCanRemove(bool canRemove);
    int count() const;
    QWidgetList popupTargets() const;

signals:
    void addClicked();
    void removeClicked();
    void wheelScrolled(int delta);
    void countChanged(int count);

protected:
    void wheelEvent(QWheelEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;

private:
    void syncRegions();
    buttons::ButtonSpec buttonSpec() const;
    void onRegionClicked(const QString& regionId);

    int count_ = 1;
    bool canRemove_ = false;
    buttons::Divider counterDivider_;
    WheelScrollPolicy wheelPolicy_;

    static constexpr int kOuterSize = 36;
    static constexpr int kCornerRadius = 6;
};

}  // namespace sli::toolkit
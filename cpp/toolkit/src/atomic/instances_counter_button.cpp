#include "sli/toolkit/atomic/instances_counter_button.h"

#include <QKeyEvent>
#include <QWheelEvent>

#include <algorithm>
#include <memory>
#include <optional>

#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/buttons/specs.h"

namespace sli::toolkit {

InstancesCounterButton::InstancesCounterButton(
    QWidget* parent, bool wheelRequiresFocus)
    : Button(QString{}, Button::Variant::Default, parent),
      wheelPolicy_(wheelRequiresFocus),
      counterDivider_{QStringLiteral("separator.color"),
                      QStringLiteral("dialog.border"),
                      1.0,
                      2.0} {
    setFocusPolicy(Qt::StrongFocus);
    setSpec(buttonSpec());
    connect(this, &Button::regionClicked,
            this, &InstancesCounterButton::onRegionClicked);
}

// ---------- public API ----------

void InstancesCounterButton::setCount(int count) {
    count = std::max(1, count);
    if (count_ != count) {
        count_ = count;
        syncRegions();
        emit countChanged(count);
    }
}

void InstancesCounterButton::setCanRemove(bool canRemove) {
    if (canRemove_ != canRemove) {
        canRemove_ = canRemove;
        syncRegions();
    }
}

int InstancesCounterButton::count() const {
    return count_;
}

QWidgetList InstancesCounterButton::popupTargets() const {
    return {const_cast<InstancesCounterButton*>(this)};
}

// ---------- events ----------

void InstancesCounterButton::wheelEvent(QWheelEvent* event) {
    if (!wheelPolicy_.shouldHandleWheelEvent(this, event)) {
        return;
    }
    const int delta = static_cast<int>(event->angleDelta().y());
    if (delta != 0) {
        emit wheelScrolled(delta);
        event->accept();
        return;
    }
    Button::wheelEvent(event);
}

void InstancesCounterButton::keyPressEvent(QKeyEvent* event) {
    if (event->isAutoRepeat()) {
        event->accept();
        return;
    }

    const auto key = event->key();
    if (key == Qt::Key_Space || key == Qt::Key_Return
        || key == Qt::Key_Enter || key == Qt::Key_Up
        || key == Qt::Key_Plus) {
        emit addClicked();
        event->accept();
        return;
    }

    if ((key == Qt::Key_Down || key == Qt::Key_Minus) && canRemove_) {
        emit removeClicked();
        event->accept();
        return;
    }

    Button::keyPressEvent(event);
}

// ---------- internals ----------

void InstancesCounterButton::syncRegions() {
    setSpec(buttonSpec());
}

buttons::ButtonSpec InstancesCounterButton::buttonSpec() const {
    using namespace buttons;

    if (count_ <= 1) {
        // Single region: "whole" with add_circle icon.
        RegionSpec wholeRegion;
        wholeRegion.id = QStringLiteral("whole");
        wholeRegion.content.icon = QVariant(QStringLiteral("add_circle"));
        wholeRegion.style.iconSizePx = 20;
        wholeRegion.enabled = true;

        ShapeSpec shape;
        shape.cornerRadius = kCornerRadius;
        shape.size = QSize(kOuterSize, kOuterSize);
        shape.iconSize = 20;

        ButtonSpec spec;
        spec.regions = {std::move(wholeRegion)};
        spec.split = std::make_shared<VerticalSplit>();
        spec.divider = std::nullopt;
        spec.shape = std::move(shape);
        spec.variant = QStringLiteral("default");
        return spec;
    }

    // Two regions: "top" (add) and "bottom" (remove).
    RegionSpec topRegion;
    topRegion.id = QStringLiteral("top");
    topRegion.content.icon = QVariant(QStringLiteral("add"));
    topRegion.style.iconSizePx = 14;
    topRegion.enabled = true;

    RegionSpec bottomRegion;
    bottomRegion.id = QStringLiteral("bottom");
    bottomRegion.content.icon = QVariant(QStringLiteral("remove"));
    bottomRegion.style.iconSizePx = 14;
    bottomRegion.enabled = canRemove_;

    ShapeSpec shape;
    shape.cornerRadius = kCornerRadius;
    shape.size = QSize(kOuterSize, kOuterSize);
    shape.iconSize = 20;

    ButtonSpec spec;
    spec.regions = {std::move(topRegion), std::move(bottomRegion)};
    spec.split = std::make_shared<VerticalSplit>();
    spec.divider = counterDivider_;
    spec.shape = std::move(shape);
    spec.variant = QStringLiteral("default");
    return spec;
}

void InstancesCounterButton::onRegionClicked(const QString& regionId) {
    if (regionId == QStringLiteral("whole")
        || regionId == QStringLiteral("top")) {
        emit addClicked();
    } else if (regionId == QStringLiteral("bottom") && canRemove_) {
        emit removeClicked();
    }
}

}  // namespace sli::toolkit
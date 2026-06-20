#pragma once

#include <QSpinBox>

namespace sli::toolkit {

/// Themed integer spin box. Subclasses `QSpinBox`, swaps the native arrow
/// buttons for custom-painted +/- steppers, and draws a rounded themed border.
class SpinBox final : public QSpinBox {
    Q_OBJECT

public:
    explicit SpinBox(QWidget* parent = nullptr);

    QSize sizeHint() const override;

protected:
    void paintEvent(QPaintEvent* event) override;
};

}  // namespace sli::toolkit

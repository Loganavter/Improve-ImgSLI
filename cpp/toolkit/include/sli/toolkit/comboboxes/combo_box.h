#pragma once

#include <QComboBox>

namespace sli::toolkit {

class ComboBox final : public QComboBox {
    Q_OBJECT

public:
    explicit ComboBox(QWidget* parent = nullptr);

    QSize sizeHint() const override;

protected:
    void paintEvent(QPaintEvent* event) override;
};

}  // namespace sli::toolkit

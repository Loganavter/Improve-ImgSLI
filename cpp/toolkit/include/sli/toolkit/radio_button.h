#pragma once

#include <QAbstractButton>

namespace sli::toolkit {

class RadioButton final : public QAbstractButton {
    Q_OBJECT

public:
    explicit RadioButton(const QString& text = {}, QWidget* parent = nullptr);

    QSize sizeHint() const override;

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    static constexpr int kDiameter = 16;
    static constexpr int kSpacing = 8;
};

}  // namespace sli::toolkit

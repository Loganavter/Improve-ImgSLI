#pragma once

#include <QAbstractButton>

namespace sli::toolkit {

class CheckBox final : public QAbstractButton {
    Q_OBJECT

public:
    explicit CheckBox(const QString& text = {}, QWidget* parent = nullptr);

    QSize sizeHint() const override;

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    static constexpr int kBoxSize = 16;
    static constexpr int kSpacing = 8;
};

}  // namespace sli::toolkit

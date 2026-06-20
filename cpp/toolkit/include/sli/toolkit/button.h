#pragma once

#include <QAbstractButton>

namespace sli::toolkit {

class Button final : public QAbstractButton {
    Q_OBJECT

public:
    enum class Variant {
        Default,
        Surface,
        Ghost,
        Subtle,
    };

    explicit Button(
        const QString& text = {},
        Variant variant = Variant::Surface,
        QWidget* parent = nullptr);

    QSize sizeHint() const override;
    void setVariant(Variant variant);

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    Variant variant_;
};

}  // namespace sli::toolkit

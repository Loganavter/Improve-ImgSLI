#pragma once

#include <QAbstractButton>
#include <QPropertyAnimation>

namespace sli::toolkit {

class RadioButton final : public QAbstractButton {
    Q_OBJECT
    Q_PROPERTY(qreal hoverProgress READ getHoverProgress WRITE setHoverProgress)

public:
    explicit RadioButton(const QString& text = {}, QWidget* parent = nullptr);

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

    qreal getHoverProgress() const { return m_hoverProgress; }
    void setHoverProgress(qreal value);

protected:
    void paintEvent(QPaintEvent* event) override;
    bool event(QEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;
    void focusInEvent(QFocusEvent* e) override;
    void focusOutEvent(QFocusEvent* e) override;
    void changeEvent(QEvent* e) override;

private:
    void setHoverActive(bool active);
    void animateHover(bool hovered);
    bool hoverHitTest(const QPointF& pos) const;

    QRectF indicatorRect(const QRectF& fullRect) const;
    QRectF textRectAvailable(const QRectF& fullRect, const QRectF& indicatorRect) const;
    QRectF textRectContent(const QRectF& fullRect, const QRectF& indicatorRect) const;

    static constexpr int kIndicatorSize = 20;
    static constexpr int kOutlineWidth = 1;
    static constexpr int kSpacing = 8;
    static constexpr int kPaddingH = 2;
    static constexpr int kPaddingV = 5;

    static constexpr qreal kInnerHoleFactorBase = 0.50;
    static constexpr qreal kInnerHoleFactorHover = 0.60;

    static constexpr int kDisabledAlpha = 110;

    qreal m_hoverProgress = 0.0;
    bool m_hoverActive = false;

    QPropertyAnimation* m_hoverAnim = nullptr;
};

}  // namespace sli::toolkit

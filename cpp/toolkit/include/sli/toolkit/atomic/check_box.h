#pragma once

#include <QAbstractButton>
#include <QPropertyAnimation>

namespace sli::toolkit {

class CheckBox final : public QAbstractButton {
    Q_OBJECT
    Q_PROPERTY(qreal hoverProgress READ getHoverProgress WRITE setHoverProgress)
    Q_PROPERTY(qreal checkedProgress READ getCheckedProgress WRITE setCheckedProgress)

public:
    explicit CheckBox(const QString& text = {}, QWidget* parent = nullptr);

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

    qreal getHoverProgress() const { return m_hoverProgress; }
    void setHoverProgress(qreal value);

    qreal getCheckedProgress() const { return m_checkedProgress; }
    void setCheckedProgress(qreal value);

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
    void onStateChanged(int state);
    bool hoverHitTest(const QPointF& pos) const;

    QRectF indicatorRect(const QRectF& fullRect) const;
    QRectF textRectAvailable(const QRectF& fullRect, const QRectF& indicatorRect) const;
    QRectF textRectContent(const QRectF& fullRect, const QRectF& indicatorRect) const;

    static constexpr int kIndicatorSize = 20;
    static constexpr int kIndicatorRadius = 4;
    static constexpr int kOutlineWidth = 1;
    static constexpr int kSpacing = 8;
    static constexpr int kPaddingH = 2;
    static constexpr int kPaddingV = 5;

    // Check mark constants
    static constexpr qreal kCheckRotationDeg = -21.0;
    static constexpr qreal kCheckStrokeWidth = 1.1;
    static constexpr qreal kCheckX1 = 0.26;
    static constexpr qreal kCheckY1Norm = 0.42;
    static constexpr qreal kCheckX2 = 0.36;
    static constexpr qreal kCheckY2Pre = 0.63;
    static constexpr qreal kCheckX3 = 0.82;
    static constexpr qreal kCheckY3Pre = 0.34;
    static constexpr qreal kCheckBottomFactor = 0.75;
    static constexpr qreal kCheckTopFactor = 0.55;

    static constexpr int kDisabledAlpha = 110;

    qreal m_hoverProgress = 0.0;
    bool m_hoverActive = false;
    qreal m_checkedProgress = 0.0;

    QPropertyAnimation* m_hoverAnim = nullptr;
    QPropertyAnimation* m_checkedAnim = nullptr;
};

}  // namespace sli::toolkit

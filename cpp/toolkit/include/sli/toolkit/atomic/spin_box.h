#pragma once

#include <QLineEdit>

namespace sli::toolkit {

/// Themed integer spin box. Extends QLineEdit with value management,
/// wheel scroll handling, and keyboard Up/Down support.
class SpinBox final : public QLineEdit {
    Q_OBJECT

public:
    explicit SpinBox(QWidget* parent = nullptr,
                     int defaultValue = 0,
                     Qt::Alignment alignment = Qt::AlignCenter,
                     bool wheelRequiresFocus = false);

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

    void setRange(int minVal, int maxVal);
    int minimum() const { return m_minimum; }
    int maximum() const { return m_maximum; }
    int value() const { return m_value; }
    void setValue(int val);
    void setSuffix(const QString& suffix) { m_suffix = suffix; updateStyle(); }
    QString suffix() const { return m_suffix; }

signals:
    void valueChanged(int value);

protected:
    void paintEvent(QPaintEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void focusInEvent(QFocusEvent* event) override;

private:
    void onEditingFinished();
    void updateStyle();
    bool shouldHandleWheelEvent(const QWheelEvent* event) const;
    int contentWidth() const;

    static constexpr int kFixedHeight = 32;
    static constexpr int kMinimumWidth = 44;
    static constexpr int kHorizontalPadding = 8;

    int m_minimum = 0;
    int m_maximum = 100;
    int m_value = 0;
    int m_defaultValue = 0;
    QString m_suffix;
    bool m_wheelRequiresFocus = false;
};

}  // namespace sli::toolkit

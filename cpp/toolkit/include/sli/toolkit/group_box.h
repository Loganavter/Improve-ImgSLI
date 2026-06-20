#pragma once

#include <QString>
#include <QWidget>

class QLayout;
class QVBoxLayout;

namespace sli::toolkit {

/// Custom group container with a title drawn on the top border. Mirrors
/// `sli_ui_toolkit.widgets.CustomGroupWidget`. Use [`addWidget`] /
/// [`addLayout`] to populate the body.
class GroupBox final : public QWidget {
    Q_OBJECT

public:
    explicit GroupBox(const QString& title = {}, QWidget* parent = nullptr);

    void setTitle(const QString& title);
    QString title() const { return title_; }

    void addWidget(QWidget* widget);
    void addLayout(QLayout* layout);

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    void updateContentMargins();

    QString title_;
    QVBoxLayout* content_;
    static constexpr int kRadius = 8;
    static constexpr int kTitleLeftPad = 12;
};

}  // namespace sli::toolkit

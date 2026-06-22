#pragma once

#include <QString>
#include <QWidget>

#include <vector>

class QLayout;
class QVBoxLayout;

namespace sli::toolkit {

class CustomGroupWidget;

// -----------------------------------------------------------------------
// TitleWidgetProxy — lightweight adapter returned by
// CustomGroupBuilder::createStyledGroup.  Mirrors the Python inner class
// so callers can do proxy.setText("…") / proxy.text().
// -----------------------------------------------------------------------
class TitleWidgetProxy final {
public:
    explicit TitleWidgetProxy(CustomGroupWidget* group)
        : group_(group) {}

    void setText(const QString& text);
    QString text() const;

private:
    CustomGroupWidget* group_;
};

// -----------------------------------------------------------------------
// CustomGroupWidget — custom group container with a title drawn on the top
// border.  Mirrors sli_ui_toolkit.widgets.CustomGroupWidget exactly
// (including token-based theme colors).
// -----------------------------------------------------------------------
class CustomGroupWidget final : public QWidget {
    Q_OBJECT

public:
    explicit CustomGroupWidget(const QString& title_text = {},
                               QWidget* parent = nullptr);

    void setTitle(const QString& title);
    QString title() const { return title_; }

    void addWidget(QWidget* widget);
    void addLayout(QLayout* layout);

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

    /// Exposed for the builder / proxy — returns the internal layout.
    QVBoxLayout* contentLayout() const { return content_; }

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    void updateContentMargins();

    QString title_;
    QVBoxLayout* content_;

    static constexpr int kRadius = 8;
    static constexpr int kBorderWidth = 1;
    static constexpr int kTitleLeftPad = 12;
    static constexpr int kTextPadding = 4;
};

// -----------------------------------------------------------------------
// CustomGroupBuilder — convenience builder.  Two equivalent APIs:
//
//   auto [group, layout, proxy] =
//       CustomGroupBuilder::createStyledGroup("title");
//
//   auto group = CustomGroupBuilder{}
//                   .add(widget)
//                   .addLayout(layout)
//                   .build("title");
// -----------------------------------------------------------------------
class CustomGroupBuilder final {
public:
    CustomGroupBuilder() = default;

    CustomGroupBuilder& add(QWidget* widget);
    CustomGroupBuilder& addLayout(QLayout* layout);
    CustomGroupWidget* build(const QString& title = {});

    static std::tuple<CustomGroupWidget*, QVBoxLayout*, TitleWidgetProxy>
    createStyledGroup(const QString& title_text);

private:
    enum class ItemKind { Widget, Layout };
    struct PendingItem {
        ItemKind kind;
        void*    ptr;   // QWidget* or QLayout*
    };
    std::vector<PendingItem> pending_;
};

}  // namespace sli::toolkit
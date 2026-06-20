#include "sli/toolkit/theme.h"

#include <QApplication>

namespace {

const sli::toolkit::Palette kLight{
    .window = QColor("#ffffff"),
    .windowText = QColor("#1f1f1f"),
    .base = QColor("#ffffff"),
    .text = QColor("#1f1f1f"),
    .button = QColor("#f0f0f0"),
    .buttonText = QColor("#000000"),
    .accent = QColor("#0078d4"),
    .border = QColor("#c8c8c8"),
    .hover = QColor("#e5e5e5"),
    .pressed = QColor("#d5d5d5"),
};

const sli::toolkit::Palette kDark{
    .window = QColor("#252525"),
    .windowText = QColor("#e8e8e8"),
    .base = QColor("#252525"),
    .text = QColor("#dfdfdf"),
    .button = QColor("#3a3a3a"),
    .buttonText = QColor("#e8e8e8"),
    .accent = QColor("#0096ff"),
    .border = QColor("#555555"),
    .hover = QColor("#484848"),
    .pressed = QColor("#303030"),
};

}  // namespace

namespace sli::toolkit {

Theme::Mode Theme::mode_ = Theme::Mode::Dark;

const Palette& Theme::palette() {
    return mode_ == Mode::Dark ? kDark : kLight;
}

Theme::Mode Theme::mode() {
    return mode_;
}

void Theme::apply(QApplication& application, Mode mode) {
    mode_ = mode;
    const auto& colors = palette();
    QPalette palette;
    palette.setColor(QPalette::Window, colors.window);
    palette.setColor(QPalette::WindowText, colors.windowText);
    palette.setColor(QPalette::Base, colors.base);
    palette.setColor(QPalette::Text, colors.text);
    palette.setColor(QPalette::Button, colors.button);
    palette.setColor(QPalette::ButtonText, colors.buttonText);
    palette.setColor(QPalette::Highlight, colors.accent);
    palette.setColor(QPalette::HighlightedText, QColor("#ffffff"));
    application.setPalette(palette);
}

bool Theme::applyNamed(QApplication& application, const QString& name) {
    if (name.compare(QStringLiteral("dark"), Qt::CaseInsensitive) == 0) {
        apply(application, Mode::Dark);
        return true;
    }
    if (name.compare(QStringLiteral("light"), Qt::CaseInsensitive) == 0) {
        apply(application, Mode::Light);
        return true;
    }
    return false;
}

}  // namespace sli::toolkit

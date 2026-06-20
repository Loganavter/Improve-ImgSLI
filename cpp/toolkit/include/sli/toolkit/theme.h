#pragma once

#include <QColor>
#include <QPalette>
#include <QString>

class QApplication;

namespace sli::toolkit {

struct Palette {
    QColor window;
    QColor windowText;
    QColor base;
    QColor text;
    QColor button;
    QColor buttonText;
    QColor accent;
    QColor border;
    QColor hover;
    QColor pressed;
};

class Theme final {
public:
    enum class Mode {
        Light,
        Dark,
    };

    static const Palette& palette();
    static Mode mode();
    static void apply(QApplication& application, Mode mode);
    static bool applyNamed(QApplication& application, const QString& name);

private:
    static Mode mode_;
};

}  // namespace sli::toolkit

#pragma once

#include <QColor>
#include <QPalette>
#include <QString>

#include <optional>

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
    static bool isDark() { return mode_ == Mode::Dark; }
    static void apply(QApplication& application, Mode mode);
    static bool applyNamed(QApplication& application, const QString& name);

    // Token-keyed color lookup. `tryGetColor` returns std::nullopt on miss;
    // `getColor` falls back to a derived value from the Palette so callers
    // always get something useful. Tokens mirror Python `sli_ui_toolkit`
    // theme manager:
    //   button.{toggle,dialog.default,ghost}.background.{normal,hover,
    //                                                    pressed,checked,
    //                                                    checked.hover,
    //                                                    disabled}
    //   button.{toggle,dialog.default}.border
    //   accent, dialog.text, dialog.border, separator.color
    static QColor getColor(const QString& token);
    static std::optional<QColor> tryGetColor(const QString& token);

    // Register a callback invoked on theme change.  Mirrors Python's
    // `theme_manager.theme_changed.connect(slot)`.
    using ThemeChangedCallback = std::function<void()>;
    static void onThemeChanged(QObject* owner, ThemeChangedCallback callback);

private:
    static Mode mode_;
    static std::vector<std::pair<QObject*, ThemeChangedCallback>> themeCallbacks_;
};

}  // namespace sli::toolkit

#include "sli/toolkit/theme.h"

#include <QApplication>
#include <QHash>

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

using TokenMap = QHash<QString, QColor>;

TokenMap buildLightTokens() {
    TokenMap m;
    m.insert(QStringLiteral("accent"), kLight.accent);
    m.insert(QStringLiteral("dialog.text"), kLight.text);
    m.insert(QStringLiteral("dialog.border"), kLight.border);
    m.insert(QStringLiteral("separator.color"), kLight.border);
    m.insert(QStringLiteral("dialog.button.hover"), QColor("#d8d8d8"));
    m.insert(QStringLiteral("Window"), kLight.window);
    m.insert(QStringLiteral("WindowText"), kLight.windowText);

    // ComboBox / dropdown tokens (mirrors Python ThemeManager light palette).
    m.insert(QStringLiteral("dialog.input.background"),
             QColor(0xff, 0xff, 0xff));
    m.insert(QStringLiteral("list_item.background.hover"),
             QColor(0xf0, 0xf0, 0xf0));
    m.insert(QStringLiteral("input.border.thin"),
             QColor(0xc8, 0xc8, 0xc8));
    m.insert(QStringLiteral("flyout.background"),
             QColor(0xff, 0xff, 0xff));
    m.insert(QStringLiteral("flyout.border"),
             QColor(0xd0, 0xd0, 0xd0));

    // button.toggle.* — default-variant token tree. Values mirror Python
    // FLUENT_LIGHT exactly; deliberately we do NOT define
    // `button.toggle.border` — Python omits it, which makes
    // default-variant buttons render without a visible border.
    m.insert(QStringLiteral("button.toggle.background.normal"),
             QColor(0xf0, 0xf0, 0xf0));
    m.insert(QStringLiteral("button.toggle.background.hover"),
             QColor(0xe6, 0xe6, 0xe6));
    m.insert(QStringLiteral("button.toggle.background.pressed"),
             QColor(0xdc, 0xdc, 0xdc));
    // Subtle grey checked, NOT accent. Accent for checked was a port
    // divergence flagged by the parity tester.
    m.insert(QStringLiteral("button.toggle.background.checked"),
             QColor(0xc0, 0xc0, 0xc0));
    m.insert(QStringLiteral("button.toggle.background.checked.hover"),
             QColor(0xb0, 0xb0, 0xb0));
    m.insert(QStringLiteral("button.toggle.background.disabled"),
             QColor(kLight.button.red(), kLight.button.green(),
                    kLight.button.blue(), 120));

    // button.dialog.default.* — surface-variant token tree (Python's
    // FLUENT_LIGHT values verbatim).
    m.insert(QStringLiteral("button.dialog.default.background"),
             QColor(0xff, 0xff, 0xff));
    m.insert(QStringLiteral("button.dialog.default.background.hover"),
             QColor(0xf8, 0xf8, 0xf8));
    m.insert(QStringLiteral("button.dialog.default.background.pressed"),
             QColor(0xe9, 0xe9, 0xe9));
    // NOTE: Python's FLUENT_LIGHT palette deliberately does NOT define
    // `button.dialog.default.background.checked`. The resolver
    // (default_resolve_bg) then falls back to `.pressed`, which keeps the
    // surface-variant checked appearance subtle. Defining it here forced
    // the C++ port to paint the accent (bright blue) panel — exactly the
    // divergence the parity tester button_toggle_checked case caught.
    m.insert(QStringLiteral("button.dialog.default.background.disabled"),
             QColor(kLight.button.red(), kLight.button.green(),
                    kLight.button.blue(), 120));
    // Python's `button.dialog.default.border = #1E000000` — low-alpha black
    // overlay. Reads as a very subtle outline against the white surface
    // instead of the chunky `#c8c8c8` the port used to draw.
    m.insert(QStringLiteral("button.dialog.default.border"),
             QColor(0, 0, 0, 0x1E));
    return m;
}

TokenMap buildDarkTokens() {
    TokenMap m;
    m.insert(QStringLiteral("accent"), kDark.accent);
    m.insert(QStringLiteral("dialog.text"), kDark.text);
    m.insert(QStringLiteral("dialog.border"), kDark.border);
    m.insert(QStringLiteral("separator.color"), kDark.border);
    m.insert(QStringLiteral("dialog.button.hover"), QColor("#4f4f4f"));
    m.insert(QStringLiteral("Window"), kDark.window);
    m.insert(QStringLiteral("WindowText"), kDark.windowText);

    // ComboBox / dropdown tokens (mirrors Python ThemeManager dark palette).
    m.insert(QStringLiteral("dialog.input.background"),
             QColor(0x3c, 0x3c, 0x3c));
    m.insert(QStringLiteral("list_item.background.hover"),
             QColor(0x48, 0x48, 0x48));
    m.insert(QStringLiteral("input.border.thin"),
             QColor(0x55, 0x55, 0x55));
    m.insert(QStringLiteral("flyout.background"),
             QColor(0x3c, 0x3c, 0x3c));
    m.insert(QStringLiteral("flyout.border"),
             QColor(0x55, 0x55, 0x55));

    // button.toggle.* — dark FLUENT_DARK values verbatim. No
    // `button.toggle.border` token, no accent checked — both were port
    // divergences.
    m.insert(QStringLiteral("button.toggle.background.normal"),
             QColor(0x3a, 0x3a, 0x3a));
    m.insert(QStringLiteral("button.toggle.background.hover"),
             QColor(0x48, 0x48, 0x48));
    m.insert(QStringLiteral("button.toggle.background.pressed"),
             QColor(0x55, 0x55, 0x55));
    m.insert(QStringLiteral("button.toggle.background.checked"),
             QColor(0x60, 0x60, 0x60));
    m.insert(QStringLiteral("button.toggle.background.checked.hover"),
             QColor(0x70, 0x70, 0x70));
    m.insert(QStringLiteral("button.toggle.background.disabled"),
             QColor(kDark.button.red(), kDark.button.green(),
                    kDark.button.blue(), 120));

    // button.dialog.default.* — dark FLUENT_DARK surface variant.
    m.insert(QStringLiteral("button.dialog.default.background"),
             QColor(0x3c, 0x3c, 0x3c));
    m.insert(QStringLiteral("button.dialog.default.background.hover"),
             QColor(0x4a, 0x4a, 0x4a));
    m.insert(QStringLiteral("button.dialog.default.background.pressed"),
             QColor(0x55, 0x55, 0x55));
    m.insert(QStringLiteral("button.dialog.default.background.disabled"),
             QColor(kDark.button.red(), kDark.button.green(),
                    kDark.button.blue(), 120));
    // Python FLUENT_DARK: `button.dialog.default.border = #26FFFFFF`
    // (~15% white overlay) — subtle outline on the dark surface.
    m.insert(QStringLiteral("button.dialog.default.border"),
             QColor(255, 255, 255, 0x26));
    return m;
}

const TokenMap& lightTokens() {
    static const TokenMap instance = buildLightTokens();
    return instance;
}

const TokenMap& darkTokens() {
    static const TokenMap instance = buildDarkTokens();
    return instance;
}

}  // namespace

namespace sli::toolkit {

Theme::Mode Theme::mode_ = Theme::Mode::Dark;
std::vector<std::pair<QObject*, Theme::ThemeChangedCallback>> Theme::themeCallbacks_;

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

    // Fire registered callbacks — Python's theme_manager.theme_changed.emit().
    // Purge dead owners (destroyed QObjects) while we're at it.
    themeCallbacks_.erase(
        std::remove_if(themeCallbacks_.begin(), themeCallbacks_.end(),
                       [](const auto& pair) { return pair.first == nullptr; }),
        themeCallbacks_.end());
    for (auto& [owner, cb] : themeCallbacks_) {
        if (owner != nullptr) {
            cb();
        }
    }
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

std::optional<QColor> Theme::tryGetColor(const QString& token) {
    const TokenMap& tokens = mode_ == Mode::Dark ? darkTokens() : lightTokens();
    auto it = tokens.find(token);
    if (it == tokens.end()) {
        return std::nullopt;
    }
    return *it;
}

QColor Theme::getColor(const QString& token) {
    if (auto resolved = tryGetColor(token); resolved.has_value()) {
        return *resolved;
    }
    // Token-miss fallback: derive a sensible default from the palette so the
    // pipeline degrades gracefully rather than rendering invalid colors.
    const Palette& p = palette();
    if (token.contains(QStringLiteral("pressed"))) return p.pressed;
    if (token.contains(QStringLiteral("hover"))) return p.hover;
    if (token.contains(QStringLiteral("checked"))) return p.accent;
    if (token.contains(QStringLiteral("disabled"))) {
        QColor c = p.button;
        c.setAlpha(120);
        return c;
    }
    if (token.contains(QStringLiteral("border"))) return p.border;
    if (token.contains(QStringLiteral("background"))) return p.button;
    if (token.contains(QStringLiteral("text"))) return p.text;
    return p.windowText;
}

void Theme::onThemeChanged(QObject* owner, ThemeChangedCallback callback) {
    // Register the callback.  When `owner` is destroyed the pointer is
    // nulled by the purge in apply().
    themeCallbacks_.emplace_back(owner, std::move(callback));
    if (owner != nullptr) {
        QObject::connect(owner, &QObject::destroyed, owner, [owner] {
            for (auto& [o, _cb] : themeCallbacks_) {
                if (o == owner) {
                    o = nullptr;
                }
            }
        });
    }
}

}  // namespace sli::toolkit

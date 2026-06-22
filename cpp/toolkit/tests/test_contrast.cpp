// Ported from sli-ui-toolkit/tests/test_contrast.py.
//
// The Python toolkit ships a string-keyed token palette and verifies WCAG AA
// contrast (4.5:1 text, 3.0:1 UI) for many token pairs. The C++ Palette is a
// flat struct with named members — we map the still-applicable Python pairs
// onto Palette members and verify them under both Light and Dark themes.

#include <QApplication>
#include <QColor>
#include <QTest>

#include "sli/toolkit/theme.h"

using namespace sli::toolkit;

class TestContrast : public QObject {
  Q_OBJECT

 private slots:
  void initTestCase();
  void anchorBlackOnWhiteIs21();
  void anchorSameColorIsOne();
  void lightThemeTextPairsMeetAa();
  void darkThemeTextPairsMeetAa();
  void lightThemeUiPairsMeetUiThreshold();
  void darkThemeUiPairsMeetUiThreshold();

 private:
  int argc_ = 1;
  char arg0_[8] = "tk-test";
  char* argv_[2] = {arg0_, nullptr};
  QApplication* app_ = nullptr;
};

namespace {

double linearize(double c) {
  return c <= 0.03928 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4);
}

double relativeLuminance(const QColor& c) {
  const double r = linearize(c.red() / 255.0);
  const double g = linearize(c.green() / 255.0);
  const double b = linearize(c.blue() / 255.0);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

double contrastRatio(const QColor& a, const QColor& b) {
  const double la = relativeLuminance(a);
  const double lb = relativeLuminance(b);
  const double light = std::max(la, lb);
  const double dark = std::min(la, lb);
  return (light + 0.05) / (dark + 0.05);
}

void verifyOpaque(const QColor& c, const char* name) {
  QVERIFY2(c.alpha() == 255,
           qPrintable(QStringLiteral("token %1 must be opaque for direct "
                                     "contrast measurement").arg(name)));
}

}  // namespace

void TestContrast::initTestCase() {
  if (QApplication::instance() == nullptr) {
    app_ = new QApplication(argc_, argv_);
  }
}

void TestContrast::anchorBlackOnWhiteIs21() {
  QCOMPARE(static_cast<int>(std::round(
               contrastRatio(QColor("#000000"), QColor("#ffffff")) * 100)),
           2100);
}

void TestContrast::anchorSameColorIsOne() {
  QCOMPARE(static_cast<int>(std::round(
               contrastRatio(QColor("#ffffff"), QColor("#ffffff")) * 100)),
           100);
}

void TestContrast::lightThemeTextPairsMeetAa() {
  Theme::apply(*qApp, Theme::Mode::Light);
  const Palette& p = Theme::palette();
  verifyOpaque(p.windowText, "windowText");
  verifyOpaque(p.window, "window");
  verifyOpaque(p.text, "text");
  verifyOpaque(p.base, "base");
  verifyOpaque(p.buttonText, "buttonText");
  verifyOpaque(p.button, "button");

  QVERIFY2(contrastRatio(p.windowText, p.window) >= 4.5,
           "Light: windowText on window must meet WCAG AA text 4.5:1");
  QVERIFY2(contrastRatio(p.text, p.base) >= 4.5,
           "Light: text on base must meet WCAG AA text 4.5:1");
  QVERIFY2(contrastRatio(p.buttonText, p.button) >= 4.5,
           "Light: buttonText on button must meet WCAG AA text 4.5:1");
}

void TestContrast::darkThemeTextPairsMeetAa() {
  Theme::apply(*qApp, Theme::Mode::Dark);
  const Palette& p = Theme::palette();
  verifyOpaque(p.windowText, "windowText");
  verifyOpaque(p.window, "window");
  verifyOpaque(p.text, "text");
  verifyOpaque(p.base, "base");
  verifyOpaque(p.buttonText, "buttonText");
  verifyOpaque(p.button, "button");

  QVERIFY2(contrastRatio(p.windowText, p.window) >= 4.5,
           "Dark: windowText on window must meet WCAG AA text 4.5:1");
  QVERIFY2(contrastRatio(p.text, p.base) >= 4.5,
           "Dark: text on base must meet WCAG AA text 4.5:1");
  QVERIFY2(contrastRatio(p.buttonText, p.button) >= 4.5,
           "Dark: buttonText on button must meet WCAG AA text 4.5:1");
}

void TestContrast::lightThemeUiPairsMeetUiThreshold() {
  Theme::apply(*qApp, Theme::Mode::Light);
  const Palette& p = Theme::palette();
  QVERIFY2(contrastRatio(p.accent, p.window) >= 3.0,
           "Light: accent vs window must meet WCAG AA UI 3.0:1");
}

void TestContrast::darkThemeUiPairsMeetUiThreshold() {
  Theme::apply(*qApp, Theme::Mode::Dark);
  const Palette& p = Theme::palette();
  QVERIFY2(contrastRatio(p.accent, p.window) >= 3.0,
           "Dark: accent vs window must meet WCAG AA UI 3.0:1");
}

QTEST_APPLESS_MAIN(TestContrast)
#include "test_contrast.moc"

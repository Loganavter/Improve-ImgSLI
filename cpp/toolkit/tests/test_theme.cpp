// Ported from sli-ui-toolkit/tests/test_theme.py.
//
// Theme switching parity. The C++ Theme uses an enum (Light/Dark) instead
// of named string keys like the Python ThemeManager — we exercise both
// `apply(...)` paths and `applyNamed("light"/"dark")` so the named API stays
// behaviorally equivalent.

#include <QApplication>
#include <QTest>

#include "sli/toolkit/theme.h"

using namespace sli::toolkit;

class TestTheme : public QObject {
  Q_OBJECT

 private slots:
  void initTestCase();
  void paletteHasUsableColors();
  void themeSwitchingChangesMode();
  void applyNamedAcceptsLightAndDark();
  void applyNamedRejectsUnknown();

 private:
  int argc_ = 1;
  char arg0_[8] = "tk-test";
  char* argv_[2] = {arg0_, nullptr};
  QApplication* app_ = nullptr;
};

void TestTheme::initTestCase() {
  if (QApplication::instance() == nullptr) {
    app_ = new QApplication(argc_, argv_);
  }
}

void TestTheme::paletteHasUsableColors() {
  const Palette& pal = Theme::palette();
  QVERIFY(pal.window.isValid());
  QVERIFY(pal.windowText.isValid());
  QVERIFY(pal.buttonText.isValid());
  QVERIFY(pal.accent.isValid());
}

void TestTheme::themeSwitchingChangesMode() {
  Q_ASSERT(QApplication::instance() != nullptr);
  Theme::apply(*qApp, Theme::Mode::Light);
  QCOMPARE(Theme::mode(), Theme::Mode::Light);
  QVERIFY(!Theme::isDark());

  Theme::apply(*qApp, Theme::Mode::Dark);
  QCOMPARE(Theme::mode(), Theme::Mode::Dark);
  QVERIFY(Theme::isDark());
}

void TestTheme::applyNamedAcceptsLightAndDark() {
  QVERIFY(Theme::applyNamed(*qApp, QStringLiteral("light")));
  QCOMPARE(Theme::mode(), Theme::Mode::Light);
  QVERIFY(Theme::applyNamed(*qApp, QStringLiteral("dark")));
  QCOMPARE(Theme::mode(), Theme::Mode::Dark);
}

void TestTheme::applyNamedRejectsUnknown() {
  // Python's ThemeManager would simply ignore an unknown name; the C++
  // contract is that the boolean return signals success/failure. If this
  // fails it documents the C++ side accepting names it shouldn't.
  QVERIFY(!Theme::applyNamed(*qApp, QStringLiteral("midnight-blue")));
}

QTEST_APPLESS_MAIN(TestTheme)
#include "test_theme.moc"

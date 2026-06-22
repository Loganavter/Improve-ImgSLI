// Ported from sli-ui-toolkit/tests/test_button_custom_bg.py.
//
// Verifies the variant-dependent derivation of CustomPalette from a base
// color: tint (default/surface), ghost (transparent → opaque on hover),
// and fallback semantics.

#include <QColor>
#include <QTest>

#include "sli/toolkit/buttons/variants.h"

using namespace sli::toolkit::buttons;

namespace {
const QColor kRed(QStringLiteral("#D93025"));
}

class TestButtonCustomBg : public QObject {
  Q_OBJECT

 private slots:
  void defaultVariantIsTintedWithoutBorder();
  void surfaceMatchesDefaultFillButKeepsBorder();
  void ghostVariantStartsTransparent();
  void unknownVariantFallsBackToTint();
  void emptyVariantTreatedAsDefault();
};

void TestButtonCustomBg::defaultVariantIsTintedWithoutBorder() {
  CustomPalette pal = deriveCustomPalette(kRed, QStringLiteral("default"));
  QVERIFY(pal.normal.alpha() < 80);
  QVERIFY(pal.hover.alpha() > pal.normal.alpha());
  QCOMPARE(pal.normal.red(), kRed.red());
  QCOMPARE(pal.normal.green(), kRed.green());
  QCOMPARE(pal.normal.blue(), kRed.blue());
  QVERIFY(!pal.border.has_value());
}

void TestButtonCustomBg::surfaceMatchesDefaultFillButKeepsBorder() {
  const CustomPalette d = deriveCustomPalette(kRed, QStringLiteral("default"));
  const CustomPalette s = deriveCustomPalette(kRed, QStringLiteral("surface"));
  QCOMPARE(d.normal.rgba(), s.normal.rgba());
  QCOMPARE(d.hover.rgba(), s.hover.rgba());
  QCOMPARE(d.pressed.rgba(), s.pressed.rgba());
  QCOMPARE(d.disabled.rgba(), s.disabled.rgba());
  QVERIFY(!d.border.has_value());
  QVERIFY(s.border.has_value());
  QCOMPARE(s.border->red(), kRed.red());
  QCOMPARE(s.border->green(), kRed.green());
  QCOMPARE(s.border->blue(), kRed.blue());
}

void TestButtonCustomBg::ghostVariantStartsTransparent() {
  CustomPalette pal = deriveCustomPalette(kRed, QStringLiteral("ghost"));
  QCOMPARE(pal.normal.alpha(), 0);
  QVERIFY(pal.hover.alpha() > 0);
  QVERIFY(pal.pressed.alpha() > pal.hover.alpha());
  QVERIFY(!pal.border.has_value());
}

void TestButtonCustomBg::unknownVariantFallsBackToTint() {
  const CustomPalette pal = deriveCustomPalette(kRed, QStringLiteral("warning"));
  const CustomPalette fallback =
      deriveCustomPalette(kRed, QStringLiteral("default"));
  QCOMPARE(pal.normal.rgba(), fallback.normal.rgba());
}

void TestButtonCustomBg::emptyVariantTreatedAsDefault() {
  const CustomPalette pal = deriveCustomPalette(kRed, QString());
  const CustomPalette dflt =
      deriveCustomPalette(kRed, QStringLiteral("default"));
  QCOMPARE(pal.normal.rgba(), dflt.normal.rgba());
}

QTEST_GUILESS_MAIN(TestButtonCustomBg)
#include "test_button_custom_bg.moc"

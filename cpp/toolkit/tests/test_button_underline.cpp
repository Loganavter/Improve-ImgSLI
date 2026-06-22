// Ported from sli-ui-toolkit/tests/test_button_underline.py.
//
// The Python test monkey-patches the helper to capture the thickness value
// reaching the painter. In C++ there's no monkey-patch, so we paint into a
// QImage and inspect the rendered rect for a non-empty bottom band, plus
// verify the underline path runs without crashing.

#include <QColor>
#include <QImage>
#include <QPainter>
#include <QTest>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/layers/underline_layer.h"
#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/buttons/specs.h"
#include "sli/toolkit/buttons/variants.h"
#include "sli/toolkit/theme.h"

using namespace sli::toolkit;
using namespace sli::toolkit::buttons;

class TestButtonUnderline : public QObject {
  Q_OBJECT

 private slots:
  void underlineRendersWhenRequested();
  void underlineSkippedWhenFlagOff();
};

namespace {

QImage paintWithLayer(double thickness, bool showUnderline) {
  QImage img(80, 32, QImage::Format_ARGB32_Premultiplied);
  img.fill(Qt::white);
  QPainter painter(&img);

  DrawContext ctx;
  ctx.painter = &painter;
  ctx.rect = QRectF(0, 0, 80, 32);
  ctx.cornerRadius = 6;
  ctx.variant = getVariant(QStringLiteral("default"));
  ctx.showUnderline = showUnderline;
  ctx.underlineColor = QVariant::fromValue(QColor(255, 0, 0));
  ctx.underlineThickness = thickness;

  Theme theme;
  UnderlineLayer layer;
  if (layer.applies(ctx)) {
    layer.draw(ctx, theme);
  }
  painter.end();
  return img;
}

bool hasNonWhitePixelInBottomBand(const QImage& img, int band) {
  for (int y = img.height() - band; y < img.height(); ++y) {
    for (int x = 0; x < img.width(); ++x) {
      QColor c = img.pixelColor(x, y);
      // Any non-white pixel means the underline painted something.
      if (c.red() < 250 || c.green() < 250 || c.blue() < 250) {
        return true;
      }
    }
  }
  return false;
}

}  // namespace

void TestButtonUnderline::underlineRendersWhenRequested() {
  QImage img = paintWithLayer(3.0, true);
  QVERIFY(hasNonWhitePixelInBottomBand(img, 8));
}

void TestButtonUnderline::underlineSkippedWhenFlagOff() {
  QImage img = paintWithLayer(3.0, false);
  QVERIFY(!hasNonWhitePixelInBottomBand(img, 8));
}

QTEST_MAIN(TestButtonUnderline)
#include "test_button_underline.moc"

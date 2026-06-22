// Ported from sli-ui-toolkit/tests/test_button_regions.py.
//
// These tests are deliberately faithful — they assert what the Python tests
// assert. Anything that fails here is a real divergence between the Python
// reference and the C++ port and should be tracked in
// docs/dev/TOOLKIT_PORT_AUDIT.md.

#include <QGuiApplication>
#include <QIcon>
#include <QMouseEvent>
#include <QPainterPath>
#include <QPixmap>
#include <QPointF>
#include <QSignalSpy>
#include <QTest>
#include <QWheelEvent>

#include <memory>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/capabilities/scroll_capability.h"
#include "sli/toolkit/buttons/controller.h"
#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/buttons/specs.h"
#include "sli/toolkit/buttons/state.h"

using namespace sli::toolkit;
using namespace sli::toolkit::buttons;

namespace {

QIcon dummyIcon() {
  QPixmap pix(16, 16);
  pix.fill(Qt::red);
  return QIcon(pix);
}

void clickAt(QWidget* widget, const QPoint& pos) {
  QTest::mouseClick(widget, Qt::LeftButton, Qt::NoModifier, pos);
}

// Expose the dynamic-property `buttonController` the toolkit stashes for the
// painter so tests can reach the runtime state of the button under test.
ButtonController* controllerOf(QWidget* w) {
  return w->property("buttonController").value<ButtonController*>();
}

}  // namespace

class TestButtonRegions : public QObject {
  Q_OBJECT

 private slots:
  void verticalRegionsEmitRegionClicked();
  void disabledRegionDoesNotEmit();
  void specBasedButtonEmitsRegionClicked();
  void scrollWheelClampsToMaxValue();
  void pathRegionHitTestUsesShape();
  void pathRegionZIndexBeatsLower();
  void setCheckedUpdatesMainRegionState();
};

void TestButtonRegions::verticalRegionsEmitRegionClicked() {
  ButtonRegion top;
  top.id = QStringLiteral("top");
  top.icon = QVariant::fromValue(dummyIcon());
  ButtonRegion bottom;
  bottom.id = QStringLiteral("bottom");
  bottom.icon = QVariant::fromValue(dummyIcon());

  ButtonSpecArgs args;
  args.split = std::make_shared<VerticalSplit>();
  args.shape = ShapeSpec{};
  args.shape->size = QSize(36, 36);

  Button btn;
  btn.setSpec(ButtonSpec::fromRegions({top, bottom}, args));
  btn.resize(36, 36);
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));

  QSignalSpy spy(&btn, &Button::regionClicked);
  clickAt(&btn, QPoint(18, 8));
  clickAt(&btn, QPoint(18, 28));

  QCOMPARE(spy.size(), 2);
  QCOMPARE(spy.at(0).at(0).toString(), QStringLiteral("top"));
  QCOMPARE(spy.at(1).at(0).toString(), QStringLiteral("bottom"));
}

void TestButtonRegions::disabledRegionDoesNotEmit() {
  ButtonRegion top;
  top.id = QStringLiteral("top");
  top.icon = QVariant::fromValue(dummyIcon());
  ButtonRegion bottom;
  bottom.id = QStringLiteral("bottom");
  bottom.icon = QVariant::fromValue(dummyIcon());
  bottom.enabled = false;

  ButtonSpecArgs args;
  args.split = std::make_shared<VerticalSplit>();
  args.shape = ShapeSpec{};
  args.shape->size = QSize(36, 36);

  Button btn;
  btn.setSpec(ButtonSpec::fromRegions({top, bottom}, args));
  btn.resize(36, 36);
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));

  QSignalSpy spy(&btn, &Button::regionClicked);
  // Python: clicking the disabled bottom region must NOT emit anything.
  clickAt(&btn, QPoint(18, 28));
  QCOMPARE(spy.size(), 0);
}

void TestButtonRegions::specBasedButtonEmitsRegionClicked() {
  RegionSpec top;
  top.id = QStringLiteral("top");
  top.content.icon = QVariant::fromValue(dummyIcon());
  RegionSpec bottom;
  bottom.id = QStringLiteral("bottom");
  bottom.content.icon = QVariant::fromValue(dummyIcon());

  ButtonSpec spec;
  spec.regions = {top, bottom};
  spec.split = std::make_shared<VerticalSplit>();
  spec.shape.size = QSize(36, 36);

  Button btn;
  btn.setSpec(spec);
  btn.resize(36, 36);
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));

  QSignalSpy spy(&btn, &Button::regionClicked);
  clickAt(&btn, QPoint(18, 8));
  clickAt(&btn, QPoint(18, 28));

  QCOMPARE(spy.size(), 2);
  QCOMPARE(spy.at(0).at(0).toString(), QStringLiteral("top"));
  QCOMPARE(spy.at(1).at(0).toString(), QStringLiteral("bottom"));
}

void TestButtonRegions::scrollWheelClampsToMaxValue() {
  // Python: a positive wheel step on a region with scroll(min=0, max=2)
  // emits regionValueChanged("scroll", 2). We listen on the underlying
  // ScrollCapability since C++ Button does not currently re-emit a
  // regionValueChanged signal.
  Button::Config cfg;
  cfg.icon = dummyIcon();
  cfg.size = QSize(36, 36);
  cfg.scrollable = std::make_pair(0, 2);
  Button btn(cfg);
  btn.resize(36, 36);
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));

  ScrollCapability* cap = btn.findChild<ScrollCapability*>();
  QVERIFY2(cap != nullptr, "Config.scrollable must attach a ScrollCapability");

  QSignalSpy spy(cap, &ScrollCapability::scrollValueChanged);

  QWheelEvent event(QPointF(18, 18),
                    btn.mapToGlobal(QPoint(18, 18)),
                    QPoint(0, 0), QPoint(0, 120), Qt::NoButton, Qt::NoModifier,
                    Qt::NoScrollPhase, false);
  QApplication::sendEvent(&btn, &event);

  QCOMPARE(spy.size(), 1);
  QCOMPARE(spy.at(0).at(1).toInt(), 2);
}

static QPainterPath diamondPath(const QRectF& rect) {
  QPainterPath path;
  const QPointF center = rect.center();
  const qreal radius =
      static_cast<qreal>(std::min(rect.width(), rect.height())) * 0.25;
  path.moveTo(center.x(), center.y() - radius);
  path.lineTo(center.x() + radius, center.y());
  path.lineTo(center.x(), center.y() + radius);
  path.lineTo(center.x() - radius, center.y());
  path.closeSubpath();
  return path;
}

void TestButtonRegions::pathRegionHitTestUsesShape() {
  ButtonRegion diamond;
  diamond.id = QStringLiteral("diamond");
  diamond.icon = QVariant::fromValue(dummyIcon());
  diamond.rectFn = [](const QRectF& r) { return r; };
  diamond.pathFn = diamondPath;

  ButtonSpecArgs args;
  args.shape = ShapeSpec{};
  args.shape->size = QSize(40, 40);

  Button btn;
  btn.setSpec(ButtonSpec::fromRegions({diamond}, args));
  btn.resize(40, 40);
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));

  QSignalSpy spy(&btn, &Button::regionClicked);
  clickAt(&btn, QPoint(20, 20));  // inside diamond
  clickAt(&btn, QPoint(2, 2));    // outside diamond
  QCOMPARE(spy.size(), 1);
  QCOMPARE(spy.at(0).at(0).toString(), QStringLiteral("diamond"));
}

void TestButtonRegions::pathRegionZIndexBeatsLower() {
  ButtonRegion base;
  base.id = QStringLiteral("base");
  base.icon = QVariant::fromValue(dummyIcon());
  base.rectFn = [](const QRectF& r) { return r; };
  base.zIndex = 0;

  ButtonRegion diamond;
  diamond.id = QStringLiteral("diamond");
  diamond.icon = QVariant::fromValue(dummyIcon());
  diamond.rectFn = [](const QRectF& r) { return r; };
  diamond.pathFn = diamondPath;
  diamond.zIndex = 10;

  ButtonSpecArgs args;
  args.shape = ShapeSpec{};
  args.shape->size = QSize(40, 40);

  Button btn;
  btn.setSpec(ButtonSpec::fromRegions({base, diamond}, args));
  btn.resize(40, 40);
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));

  QSignalSpy spy(&btn, &Button::regionClicked);
  clickAt(&btn, QPoint(20, 20));  // diamond wins on overlap
  clickAt(&btn, QPoint(2, 2));    // falls through to base
  QCOMPARE(spy.size(), 2);
  QCOMPARE(spy.at(0).at(0).toString(), QStringLiteral("diamond"));
  QCOMPARE(spy.at(1).at(0).toString(), QStringLiteral("base"));
}

void TestButtonRegions::setCheckedUpdatesMainRegionState() {
  // Python: `button.setChecked(True)` adds ButtonState.CHECKED to the _main
  // region's state set. The toolkit port must keep the controller's runtime
  // state in sync with the Qt-level checked flag — otherwise paint layers
  // gated on `regionStates` will render the wrong variant.
  Button::Config cfg;
  cfg.text = QStringLiteral("Toggle");
  cfg.toggle = true;
  Button btn(cfg);
  QVERIFY(btn.isCheckable());

  btn.setChecked(true);
  QVERIFY(btn.isChecked());
  ButtonController* controller = controllerOf(&btn);
  QVERIFY(controller != nullptr);
  QVERIFY2(controller->states(QStringLiteral("_main"))
               .testFlag(ButtonState::Checked),
           "controller._main state must include Checked after setChecked(true)");

  btn.setChecked(false);
  QVERIFY(!btn.isChecked());
  QVERIFY2(!controller->states(QStringLiteral("_main"))
                .testFlag(ButtonState::Checked),
           "controller._main state must drop Checked after setChecked(false)");
}

QTEST_MAIN(TestButtonRegions)
#include "test_button_regions.moc"

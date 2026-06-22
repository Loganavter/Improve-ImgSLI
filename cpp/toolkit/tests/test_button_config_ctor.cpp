// Pin down the ergonomic Button(Config) ctor we added — Python's
// `Button(icon=…, toggle=…, scrollable=…, long_press=…, menu=…)` has no
// 1-line C++ equivalent before this work. Each test asserts a single
// keyword surface so a regression in one field is easy to spot.

#include <QIcon>
#include <QPixmap>
#include <QTest>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/capabilities/long_press_capability.h"
#include "sli/toolkit/buttons/capabilities/menu_capability.h"
#include "sli/toolkit/buttons/capabilities/scroll_capability.h"
#include "sli/toolkit/buttons/controller.h"

using namespace sli::toolkit;
using namespace sli::toolkit::buttons;

namespace {
QIcon dummyIcon() {
  QPixmap pix(8, 8);
  pix.fill(Qt::blue);
  return QIcon(pix);
}
ButtonController* controllerOf(QWidget* w) {
  return w->property("buttonController").value<ButtonController*>();
}
}  // namespace

class TestButtonConfigCtor : public QObject {
  Q_OBJECT

 private slots:
  void textConfigBuildsTextRegion();
  void iconConfigPropagatesIcon();
  void toggleConfigMakesCheckable();
  void scrollableAutoAttachesCapability();
  void longPressAutoAttachesCapability();
  void menuAutoAttachesCapability();
  void variantPropagates();
  void sizePropagatesToShape();
};

void TestButtonConfigCtor::textConfigBuildsTextRegion() {
  Button::Config cfg;
  cfg.text = QStringLiteral("Apply");
  Button btn(cfg);
  QCOMPARE(btn.text(), QStringLiteral("Apply"));
  ButtonController* c = controllerOf(&btn);
  QVERIFY(c != nullptr);
  QCOMPARE(c->regions().size(), std::size_t{1});
  QCOMPARE(c->regions().front().text, QStringLiteral("Apply"));
}

void TestButtonConfigCtor::iconConfigPropagatesIcon() {
  Button::Config cfg;
  cfg.icon = dummyIcon();
  Button btn(cfg);
  ButtonController* c = controllerOf(&btn);
  QVERIFY(c != nullptr);
  const auto& region = c->regions().front();
  QVERIFY2(region.icon.isValid(),
           "Config.icon must flow into ButtonRegion.icon");
  QVERIFY(region.icon.canConvert<QIcon>());
}

void TestButtonConfigCtor::toggleConfigMakesCheckable() {
  Button::Config cfg;
  cfg.text = QStringLiteral("T");
  cfg.toggle = true;
  Button btn(cfg);
  QVERIFY(btn.isCheckable());
}

void TestButtonConfigCtor::scrollableAutoAttachesCapability() {
  Button::Config cfg;
  cfg.icon = dummyIcon();
  cfg.scrollable = std::make_pair(0, 10);
  Button btn(cfg);
  QVERIFY2(btn.findChild<ScrollCapability*>() != nullptr,
           "Config.scrollable must auto-attach ScrollCapability");
}

void TestButtonConfigCtor::longPressAutoAttachesCapability() {
  Button::Config cfg;
  cfg.icon = dummyIcon();
  cfg.longPressMs = 500;
  Button btn(cfg);
  QVERIFY2(btn.findChild<LongPressCapability*>() != nullptr,
           "Config.longPressMs must auto-attach LongPressCapability");
}

void TestButtonConfigCtor::menuAutoAttachesCapability() {
  Button::Config cfg;
  cfg.icon = dummyIcon();
  cfg.menu = std::vector<std::pair<QString, QVariant>>{
      {QStringLiteral("One"), QVariant(1)},
      {QStringLiteral("Two"), QVariant(2)}};
  Button btn(cfg);
  QVERIFY2(btn.findChild<MenuCapability*>() != nullptr,
           "Config.menu must auto-attach MenuCapability");
}

void TestButtonConfigCtor::variantPropagates() {
  Button::Config cfg;
  cfg.text = QStringLiteral("Ghost");
  cfg.variant = Button::Variant::Ghost;
  Button btn(cfg);
  QCOMPARE(btn.variant(), Button::Variant::Ghost);
}

void TestButtonConfigCtor::sizePropagatesToShape() {
  Button::Config cfg;
  cfg.icon = dummyIcon();
  cfg.size = QSize(28, 28);
  Button btn(cfg);
  ButtonController* c = controllerOf(&btn);
  QCOMPARE(c->spec().shape.size, QSize(28, 28));
}

QTEST_MAIN(TestButtonConfigCtor)
#include "test_button_config_ctor.moc"

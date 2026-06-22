// Verifies the toggle propagation we added in Button::setSpec — a spec
// declaring region.toggle (or BehaviorKind::Toggle) flips the Qt-level
// checkable flag so isChecked() and ButtonState::Checked are kept in sync.

#include <QTest>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/buttons/specs.h"

using namespace sli::toolkit;
using namespace sli::toolkit::buttons;

class TestButtonToggle : public QObject {
  Q_OBJECT

 private slots:
  void specWithToggleMakesButtonCheckable();
  void specWithoutToggleIsNotCheckable();
  void configCtorTogglePropagates();
};

void TestButtonToggle::specWithToggleMakesButtonCheckable() {
  ButtonRegion region;
  region.id = QStringLiteral("_main");
  region.text = QStringLiteral("Toggle");
  region.toggle = true;
  Button btn;
  btn.setSpec(ButtonSpec::fromRegions({region}, {}));
  QVERIFY(btn.isCheckable());

  btn.setChecked(true);
  QVERIFY(btn.isChecked());
  btn.setChecked(false);
  QVERIFY(!btn.isChecked());
}

void TestButtonToggle::specWithoutToggleIsNotCheckable() {
  ButtonRegion region;
  region.id = QStringLiteral("_main");
  region.text = QStringLiteral("Click");
  Button btn;
  btn.setSpec(ButtonSpec::fromRegions({region}, {}));
  QVERIFY(!btn.isCheckable());
}

void TestButtonToggle::configCtorTogglePropagates() {
  Button::Config cfg;
  cfg.text = QStringLiteral("T");
  cfg.toggle = true;
  Button btn(cfg);
  QVERIFY(btn.isCheckable());
}

QTEST_MAIN(TestButtonToggle)
#include "test_button_toggle.moc"

// Ported from sli-ui-toolkit/tests/test_widgets_smoke.py.
//
// Verifies that the public widget classes can be instantiated without
// crashing. Mirrors the Python smoke list for the subset that lives in the
// C++ toolkit.

#include <QTest>

#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/atomic/radio_button.h"
#include "sli/toolkit/atomic/slider.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "sli/toolkit/atomic/switch.h"
#include "sli/toolkit/atomic/text_labels.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/combo_box.h"

using namespace sli::toolkit;

class TestWidgetsSmoke : public QObject {
  Q_OBJECT

 private slots:
  void buttonInstantiates();
  void checkBoxInstantiates();
  void comboBoxInstantiates();
  void lineEditInstantiates();
  void labelInstantiates();
  void radioButtonInstantiates();
  void sliderInstantiates();
  void spinBoxInstantiates();
  void switchInstantiates();
};

void TestWidgetsSmoke::buttonInstantiates() {
  Button btn(QStringLiteral("Click"));
  QVERIFY(btn.text() == QStringLiteral("Click"));
}

void TestWidgetsSmoke::checkBoxInstantiates() {
  CheckBox box(QStringLiteral("Check"));
  QVERIFY(box.text() == QStringLiteral("Check"));
}

void TestWidgetsSmoke::comboBoxInstantiates() {
  ComboBox box;
  QVERIFY(box.count() >= 0);
}

void TestWidgetsSmoke::lineEditInstantiates() {
  CustomLineEdit edit;
  QVERIFY(edit.text().isEmpty());
}

void TestWidgetsSmoke::labelInstantiates() {
  Label label(QStringLiteral("Hello"));
  QVERIFY(label.text() == QStringLiteral("Hello"));
}

void TestWidgetsSmoke::radioButtonInstantiates() {
  RadioButton btn(QStringLiteral("Radio"));
  QVERIFY(btn.text() == QStringLiteral("Radio"));
}

void TestWidgetsSmoke::sliderInstantiates() {
  Slider slider;
  QVERIFY(slider.minimum() <= slider.maximum());
}

void TestWidgetsSmoke::spinBoxInstantiates() {
  SpinBox box;
  QVERIFY(box.minimum() <= box.maximum());
}

void TestWidgetsSmoke::switchInstantiates() {
  Switch sw;
  QVERIFY(!sw.isChecked());
}

QTEST_MAIN(TestWidgetsSmoke)
#include "test_widgets_smoke.moc"

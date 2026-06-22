// Ported from sli-ui-toolkit/tests/test_keyboard.py.
//
// Verifies the keyboard contract for the toolkit widgets — Button activation
// on Space / Return, focus policies. Tests for widgets not yet ported (
// InstancesCounterButton, TimelineWidget) are omitted; tests are kept
// faithful so any regression in focus or activation shows up.

#include <QSignalSpy>
#include <QTest>

#include "sli/toolkit/atomic/switch.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/scrollable_combo_box.h"

using namespace sli::toolkit;

class TestKeyboard : public QObject {
  Q_OBJECT

 private slots:
  void buttonSpaceActivates();
  void buttonEnterActivates();
  void buttonFocusPolicyIsStrong();
  void switchSpaceToggles();
  void switchFocusPolicyIsStrong();
  void scrollableComboBoxFocusPolicyIsStrong();
};

void TestKeyboard::buttonSpaceActivates() {
  Button btn(QStringLiteral("Go"));
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));
  btn.setFocus();
  QSignalSpy spy(&btn, &QAbstractButton::clicked);
  QTest::keyClick(&btn, Qt::Key_Space);
  QCOMPARE(spy.size(), 1);
}

void TestKeyboard::buttonEnterActivates() {
  Button btn(QStringLiteral("Go"));
  btn.show();
  QVERIFY(QTest::qWaitForWindowExposed(&btn));
  btn.setFocus();
  QSignalSpy spy(&btn, &QAbstractButton::clicked);
  QTest::keyClick(&btn, Qt::Key_Return);
  // Python asserts clicked fires on Return. Qt's QAbstractButton only fires
  // on Space by default — if this test fails it documents that the C++
  // Button needs the same key-binding override Python's Button installs.
  QCOMPARE(spy.size(), 1);
}

void TestKeyboard::buttonFocusPolicyIsStrong() {
  Button btn(QStringLiteral("Go"));
  QCOMPARE(btn.focusPolicy(), Qt::StrongFocus);
}

void TestKeyboard::switchSpaceToggles() {
  Switch sw;
  sw.show();
  QVERIFY(QTest::qWaitForWindowExposed(&sw));
  sw.setFocus();
  QVERIFY(!sw.isChecked());
  QTest::keyClick(&sw, Qt::Key_Space);
  QVERIFY(sw.isChecked());
  QTest::keyClick(&sw, Qt::Key_Space);
  QVERIFY(!sw.isChecked());
}

void TestKeyboard::switchFocusPolicyIsStrong() {
  Switch sw;
  QCOMPARE(sw.focusPolicy(), Qt::StrongFocus);
}

void TestKeyboard::scrollableComboBoxFocusPolicyIsStrong() {
  sli::toolkit::comboboxes::ScrollableComboBox box;
  QCOMPARE(box.focusPolicy(), Qt::StrongFocus);
}

QTEST_MAIN(TestKeyboard)
#include "test_keyboard.moc"

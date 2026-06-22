#include "tabs/video_editor/sections/sections.h"

#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/atomic/spin_box.h"

namespace imgsli::app::video_editor_sections {

sli::toolkit::SpinBox* makeSpin(QWidget* parent, const QString& objectName,
                                 int minimum, int maximum, int value) {
  auto* field = new sli::toolkit::SpinBox(parent);
  field->setObjectName(objectName);
  field->setRange(minimum, maximum);
  field->setValue(value);
  return field;
}

sli::toolkit::ComboBox* makeCombo(QWidget* parent, const QString& objectName,
                                   const QStringList& values) {
  auto* field = new sli::toolkit::ComboBox(parent);
  field->setObjectName(objectName);
  field->addItems(values);
  return field;
}

sli::toolkit::Button* makeButton(QWidget* parent,
                                  const QString& translationKey,
                                  const QString& objectName) {
  auto* result = new sli::toolkit::Button(
      imgsli::app::tr(translationKey),
      sli::toolkit::Button::Variant::Surface, parent);
  result->setObjectName(objectName);
  return result;
}

}  // namespace imgsli::app::video_editor_sections

#include "tabs/multi_compare/sections/sections.h"

#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"

namespace imgsli::app::multi_compare_sections {

sli::toolkit::Button* makeToggleButton(QWidget* parent,
                                        const QString& translationKey,
                                        const QString& objectName,
                                        bool checked) {
  auto* button = new sli::toolkit::Button(
      imgsli::app::tr(translationKey),
      sli::toolkit::Button::Variant::Default, parent);
  button->setObjectName(objectName);
  button->setCheckable(true);
  button->setChecked(checked);
  return button;
}

}  // namespace imgsli::app::multi_compare_sections

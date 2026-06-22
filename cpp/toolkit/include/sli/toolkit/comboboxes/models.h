#pragma once

#include <QString>
#include <QVariant>

namespace sli::toolkit::comboboxes {

struct ComboItem {
  QString text;
  QVariant data;
  QString normalizedText;

  ComboItem() = default;
  ComboItem(QString t, QVariant d = {});
};

}  // namespace sli::toolkit::comboboxes

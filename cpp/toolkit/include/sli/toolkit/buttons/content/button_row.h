#pragma once

#include <QColor>
#include <QString>
#include <Qt>

#include <optional>

namespace sli::toolkit::buttons {

enum class RowWeight {
  Normal,
  Bold,
};

struct ButtonRow {
  QString text;
  int size = 12;
  RowWeight weight = RowWeight::Normal;
  std::optional<QColor> color;
  double ratio = 0.5;
  Qt::Alignment hAlign = Qt::AlignHCenter;
  bool strikethrough = false;
  bool italic = false;
};

}  // namespace sli::toolkit::buttons

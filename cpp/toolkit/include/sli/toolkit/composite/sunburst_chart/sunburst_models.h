#pragma once

#include <QString>

namespace sli::toolkit {

/// Data for a single sunburst chart segment.
/// Angles are in radians. Radii are normalized (0.0–1.0).
struct SunburstSegmentData {
  double start_angle = 0.0;
  double end_angle = 0.0;
  double inner_radius = 0.0;
  double outer_radius = 0.0;
  QString color;
  QString label;
  int font_size = 0;
  QString node_id;
  QString value_text;
  QString tooltip;
  bool is_clickable = true;
  bool is_disabled = false;
};

}  // namespace sli::toolkit

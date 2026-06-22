#pragma once

#include "ui/canvas/canvas_widget.h"

#include <QColor>
#include <QString>
#include <optional>

namespace imgsli::app::shared::rendering {

struct DividerSpec {
  bool enabled = true;
  float thickness = 2.0F;
};

struct MagnifierSpec {
  float captureX = 0.35F;
  float captureY = 0.5F;
  float magnifierX = 0.7F;
  float magnifierY = 0.5F;
  float radius = 0.16F;
  float zoom = 2.0F;
};

struct FeatureToggles {
  bool magnifier = false;
  bool guides = false;
  bool capture = false;
  bool filename = true;
  bool pasteOverlay = false;
};

// Optional rich-overlay knobs. When set, the builder also produces an
// `OverlayLayout` (slots, capture circles, guide sets, channel/diff/interp
// modes). Live UI today doesn't consume it yet — the legacy flat fields
// drive rendering. The rich payload is reachable via `buildPlanJson` for the
// future PB-C cutover.
struct OverlaySpec {
  std::optional<QColor> borderColor;
  float borderWidth = 2.0F;
  int channelMode = 0;
  int diffMode = 0;
  int interpMode = 1;
};

struct PlanInputs {
  QString leftKey;
  QString rightKey;
  int canvasWidth = 1;
  int canvasHeight = 1;
  float split = 0.5F;
  bool horizontal = false;
  DividerSpec divider;
  MagnifierSpec magnifier;
  FeatureToggles features;
  QString leftLabel;
  QString rightLabel;
  QColor fill = QColor(37, 37, 37, 255);
  std::optional<OverlaySpec> overlay;
};

// Build the flat `CanvasRenderPlan` POD the QRhi canvas widget consumes.
// Single canonical entry point — both `ComparisonController` and
// `MultiCompareGrid` route through here.
CanvasRenderPlan buildCanvasRenderPlan(const PlanInputs& inputs);

// Same builder, but returns the rich `OverlayLayout` payload as JSON. Reserved
// for the canvas widget cutover (PB-C) that will consume slots/captures/guides
// directly. Empty `QString` on failure.
QString buildCanvasRenderPlanJson(const PlanInputs& inputs);

}  // namespace imgsli::app::shared::rendering

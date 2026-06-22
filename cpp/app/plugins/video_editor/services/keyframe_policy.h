#pragma once

#include <QJsonObject>

#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

/// Interpolate two recorded plans and freeze feature groups disabled by
/// `policy` to their first-snapshot (`baseline`) values.
CanvasRenderPlan interpolateVideoPlan(const CanvasRenderPlan& before,
                                      const CanvasRenderPlan& after,
                                      const CanvasRenderPlan& baseline,
                                      const QJsonObject& policy,
                                      double factor);

}  // namespace imgsli::app

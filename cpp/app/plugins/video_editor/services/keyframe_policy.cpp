#include "plugins/video_editor/services/keyframe_policy.h"

#include <QString>

#include <algorithm>

namespace imgsli::app {

CanvasRenderPlan interpolateVideoPlan(const CanvasRenderPlan& before,
                                      const CanvasRenderPlan& after,
                                      const CanvasRenderPlan& baseline,
                                      const QJsonObject& policy,
                                      double factor) {
  const double clamped = std::clamp(factor, 0.0, 1.0);
  const float t = static_cast<float>(clamped);
  const float inverse = 1.0F - t;
  CanvasRenderPlan plan = clamped >= 1.0 ? after : before;
  plan.split = before.split * inverse + after.split * t;
  plan.dividerThickness =
      before.dividerThickness * inverse + after.dividerThickness * t;
  plan.captureX = before.captureX * inverse + after.captureX * t;
  plan.captureY = before.captureY * inverse + after.captureY * t;
  plan.magnifierX = before.magnifierX * inverse + after.magnifierX * t;
  plan.magnifierY = before.magnifierY * inverse + after.magnifierY * t;
  plan.magnifierRadius =
      before.magnifierRadius * inverse + after.magnifierRadius * t;
  plan.magnifierZoom =
      before.magnifierZoom * inverse + after.magnifierZoom * t;
  plan.canvasWidth = static_cast<int>(
      static_cast<double>(before.canvasWidth) * (1.0 - clamped) +
      static_cast<double>(after.canvasWidth) * clamped);
  plan.canvasHeight = static_cast<int>(
      static_cast<double>(before.canvasHeight) * (1.0 - clamped) +
      static_cast<double>(after.canvasHeight) * clamped);

  const auto enabled = [&policy](const char* id) {
    return policy.value(QString::fromLatin1(id)).toBool(true);
  };
  if (!enabled("split")) {
    plan.split = baseline.split;
    plan.horizontal = baseline.horizontal;
  }
  if (!enabled("divider")) {
    plan.dividerEnabled = baseline.dividerEnabled;
    plan.dividerThickness = baseline.dividerThickness;
  }
  if (!enabled("magnifier")) {
    plan.magnifierEnabled = baseline.magnifierEnabled;
    plan.magnifierX = baseline.magnifierX;
    plan.magnifierY = baseline.magnifierY;
    plan.magnifierRadius = baseline.magnifierRadius;
    plan.magnifierZoom = baseline.magnifierZoom;
  }
  if (!enabled("capture")) {
    plan.captureEnabled = baseline.captureEnabled;
    plan.captureX = baseline.captureX;
    plan.captureY = baseline.captureY;
  }
  if (!enabled("guides")) {
    plan.guidesEnabled = baseline.guidesEnabled;
  }
  if (!enabled("filename_overlay")) {
    plan.filenameEnabled = baseline.filenameEnabled;
    plan.leftLabel = baseline.leftLabel;
    plan.rightLabel = baseline.rightLabel;
  }
  if (!enabled("paste_overlay")) {
    plan.pasteOverlayEnabled = baseline.pasteOverlayEnabled;
  }
  return plan;
}

}  // namespace imgsli::app

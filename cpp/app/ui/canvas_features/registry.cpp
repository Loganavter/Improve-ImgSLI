#include "ui/canvas_features/registry.h"

#include <memory>

#include "ui/canvas/passes/background_pass.h"
#include "ui/canvas/passes/filename_overlay_pass.h"
#include "ui/canvas/passes/shape_pass.h"

namespace imgsli::app {

void registerDefaultRenderPasses(RenderPassRegistry &registry) {
  registry.add(std::make_unique<BackgroundPass>());
  registry.add(std::make_unique<ShapePass>(
      QStringLiteral("divider"), CanvasStackRole::UnderlaySplit, 1,
      QColor(255, 255, 255, 230), [](const CanvasRenderPlan &plan) {
        return plan.dividerEnabled && plan.texture2Id != 0;
      }));
  registry.add(std::make_unique<ShapePass>(
      QStringLiteral("guides"), CanvasStackRole::AnnotationGuide, 3,
      QColor(255, 105, 180, 210), [](const CanvasRenderPlan &plan) {
        return plan.guidesEnabled && plan.magnifierEnabled;
      }));
  registry.add(std::make_unique<ShapePass>(
      QStringLiteral("capture"), CanvasStackRole::AnnotationRing, 4,
      QColor(255, 105, 180, 240), [](const CanvasRenderPlan &plan) {
        return plan.captureEnabled && plan.magnifierEnabled;
      }));
  registry.add(std::make_unique<ShapePass>(
      QStringLiteral("magnifier_frame"), CanvasStackRole::ImageOverlayFrame, 7,
      QColor(235, 235, 235, 255),
      [](const CanvasRenderPlan &plan) { return plan.magnifierEnabled; }));
  registry.add(std::make_unique<ShapePass>(
      QStringLiteral("magnifier"), CanvasStackRole::ImageOverlayContent, 2,
      QColor(255, 255, 255, 255),
      [](const CanvasRenderPlan &plan) { return plan.magnifierEnabled; }));
  registry.add(std::make_unique<FilenameOverlayPass>());
  registry.add(std::make_unique<ShapePass>(
      QStringLiteral("paste_overlay"), CanvasStackRole::TransientPreview, 6,
      QColor(0, 120, 215, 100),
      [](const CanvasRenderPlan &plan) { return plan.pasteOverlayEnabled; }));
  registry.sortByStackingPolicy();
}

}  // namespace imgsli::app

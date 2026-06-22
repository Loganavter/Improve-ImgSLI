#pragma once

#include "core/render_pass.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class BackgroundPass final : public CanvasRenderPass {
 public:
  QString name() const override { return QStringLiteral("background"); }
  CanvasStackRole stackRole() const override {
    return CanvasStackRole::UnderlaySplit;
  }
  void initialize(QRhi*, QRhiRenderTarget*) override {}
  bool shouldRender(const RenderPassContext&) const override { return false; }
  void prepare(const RenderPassContext&, QRhiResourceUpdateBatch*) override {}
  void record(QRhiCommandBuffer*, const RenderPassContext&) override {}
  void release() override {}
};

}  // namespace imgsli::app

#pragma once

#include <QString>

#include "core/render_pass.h"
#include "ui/canvas/canvas_widget.h"

class QRhi;
class QRhiBuffer;
class QRhiGraphicsPipeline;
class QRhiSampler;
class QRhiShaderResourceBindings;
class QRhiTexture;

namespace imgsli::app {

class FilenameOverlayPass final : public CanvasRenderPass {
 public:
  QString name() const override { return QStringLiteral("filename_overlay"); }
  CanvasStackRole stackRole() const override {
    return CanvasStackRole::HudLabel;
  }

  void initialize(QRhi *rhi, QRhiRenderTarget *target) override;
  bool shouldRender(const RenderPassContext &context) const override;
  void prepare(const RenderPassContext &context,
               QRhiResourceUpdateBatch *updates) override;
  void record(QRhiCommandBuffer *commandBuffer,
              const RenderPassContext &context) override;
  void release() override;

 private:
  QRhi *rhi_ = nullptr;
  QRhiBuffer *vertexBuffer_ = nullptr;
  QRhiBuffer *uniformBuffer_ = nullptr;
  QRhiTexture *texture_ = nullptr;
  QRhiSampler *sampler_ = nullptr;
  QRhiShaderResourceBindings *bindings_ = nullptr;
  QRhiGraphicsPipeline *pipeline_ = nullptr;
  QString uploadKey_;
};

}  // namespace imgsli::app

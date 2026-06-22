#pragma once

#include <QColor>
#include <QString>

#include <functional>

#include "core/render_pass.h"
#include "ui/canvas/canvas_widget.h"

class QRhi;
class QRhiBuffer;
class QRhiGraphicsPipeline;
class QRhiSampler;
class QRhiShaderResourceBindings;
class QRhiTexture;

namespace imgsli::app {

class ShapePass final : public CanvasRenderPass {
 public:
  using Predicate = std::function<bool(const CanvasRenderPlan &)>;

  ShapePass(QString name, CanvasStackRole role, int mode, QColor color,
            Predicate predicate);

  QString name() const override { return name_; }
  CanvasStackRole stackRole() const override { return role_; }

  void initialize(QRhi *rhi, QRhiRenderTarget *target) override;
  void setSharedTextures(QRhiTexture *texture1, QRhiTexture *texture2,
                         QRhiSampler *sampler) override;
  bool shouldRender(const RenderPassContext &context) const override;
  void prepare(const RenderPassContext &context,
               QRhiResourceUpdateBatch *updates) override;
  void record(QRhiCommandBuffer *commandBuffer,
              const RenderPassContext &context) override;
  void release() override;

 private:
  QString name_;
  CanvasStackRole role_;
  int mode_;
  QColor color_;
  Predicate predicate_;
  QRhi *rhi_ = nullptr;
  QRhiTexture *texture1_ = nullptr;
  QRhiTexture *texture2_ = nullptr;
  QRhiSampler *sampler_ = nullptr;
  QRhiBuffer *vertexBuffer_ = nullptr;
  QRhiBuffer *uniformBuffer_ = nullptr;
  QRhiShaderResourceBindings *bindings_ = nullptr;
  QRhiGraphicsPipeline *pipeline_ = nullptr;
  bool initialized_ = false;
};

}  // namespace imgsli::app

#pragma once

#include <QRectF>
#include <QString>

#include <cstdint>

class QRhi;
class QRhiCommandBuffer;
class QRhiRenderTarget;
class QRhiResourceUpdateBatch;
class QRhiSampler;
class QRhiTexture;

namespace imgsli::app {

struct CanvasRenderPlan;

enum class CanvasStackRole : int {
  UnderlaySplit = 10,
  ImageOverlayFrame = 15,
  ImageOverlayContent = 20,
  AnnotationRing = 30,
  AnnotationBorder = 35,
  AnnotationGuide = 40,
  HudLabel = 50,
  TransientPreview = 55,
  InteractionHandle = 60,
  DebugVis = 70,
};

struct RenderPassContext {
  const CanvasRenderPlan &plan;
  QRectF contentViewport;
  QRhiTexture *texture1 = nullptr;
  QRhiTexture *texture2 = nullptr;
  QRhiSampler *sampler = nullptr;
  int targetWidth = 0;
  int targetHeight = 0;
};

class CanvasRenderPass {
public:
  virtual ~CanvasRenderPass() = default;
  [[nodiscard]] virtual QString name() const = 0;
  [[nodiscard]] virtual CanvasStackRole stackRole() const = 0;
  virtual void setSharedTextures(QRhiTexture *texture1, QRhiTexture *texture2,
                                 QRhiSampler *sampler) {
    Q_UNUSED(texture1);
    Q_UNUSED(texture2);
    Q_UNUSED(sampler);
  }
  virtual void initialize(QRhi *rhi, QRhiRenderTarget *target) = 0;
  [[nodiscard]] virtual bool
  shouldRender(const RenderPassContext &context) const = 0;
  virtual void prepare(const RenderPassContext &context,
                       QRhiResourceUpdateBatch *updates) = 0;
  virtual void record(QRhiCommandBuffer *commandBuffer,
                      const RenderPassContext &context) = 0;
  virtual void release() = 0;
};

} // namespace imgsli::app

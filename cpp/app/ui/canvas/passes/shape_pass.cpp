#include "ui/canvas/passes/shape_pass.h"

#include <QFile>
#include <QMatrix4x4>
#include <rhi/qrhi.h>
#include <rhi/qshader.h>

#include <algorithm>
#include <array>

namespace imgsli::app {

namespace {

QShader loadShader(const QString &path) {
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly)) {
    qFatal("Unable to open feature shader resource");
  }
  const QShader shader = QShader::fromSerialized(file.readAll());
  if (!shader.isValid()) {
    qFatal("Invalid feature shader");
  }
  return shader;
}

constexpr std::array<float, 16> kVertices{
    -1.0F, 1.0F, 0.0F, 0.0F, -1.0F, -1.0F, 0.0F, 1.0F,
    1.0F,  1.0F, 1.0F, 0.0F, 1.0F,  -1.0F, 1.0F, 1.0F,
};

using FeatureUniforms = std::array<float, 36>;

}  // namespace

ShapePass::ShapePass(QString name, CanvasStackRole role, int mode, QColor color,
                     Predicate predicate)
    : name_(std::move(name)),
      role_(role),
      mode_(mode),
      color_(std::move(color)),
      predicate_(std::move(predicate)) {}

void ShapePass::initialize(QRhi *rhi, QRhiRenderTarget *target) {
  release();
  rhi_ = rhi;
  vertexBuffer_ = rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer,
                                 static_cast<quint32>(sizeof(kVertices)));
  vertexBuffer_->create();
  uniformBuffer_ = rhi->newBuffer(QRhiBuffer::Dynamic, QRhiBuffer::UniformBuffer,
                                  sizeof(FeatureUniforms));
  uniformBuffer_->create();

  bindings_ = rhi->newShaderResourceBindings();
  bindings_->setBindings({
      QRhiShaderResourceBinding::uniformBuffer(
          0,
          QRhiShaderResourceBinding::VertexStage |
              QRhiShaderResourceBinding::FragmentStage,
          uniformBuffer_),
      QRhiShaderResourceBinding::sampledTexture(
          1, QRhiShaderResourceBinding::FragmentStage, texture1_, sampler_),
      QRhiShaderResourceBinding::sampledTexture(
          2, QRhiShaderResourceBinding::FragmentStage, texture2_, sampler_),
  });
  bindings_->create();

  pipeline_ = rhi->newGraphicsPipeline();
  pipeline_->setShaderStages({
      {QRhiShaderStage::Vertex,
       loadShader(QStringLiteral(":/imgsli/shaders/feature.vert.qsb"))},
      {QRhiShaderStage::Fragment,
       loadShader(QStringLiteral(":/imgsli/shaders/feature.frag.qsb"))},
  });
  pipeline_->setTopology(QRhiGraphicsPipeline::TriangleStrip);
  pipeline_->setSampleCount(target->sampleCount());
  pipeline_->setShaderResourceBindings(bindings_);
  pipeline_->setRenderPassDescriptor(target->renderPassDescriptor());
  pipeline_->setFlags(QRhiGraphicsPipeline::UsesScissor);

  QRhiGraphicsPipeline::TargetBlend blend;
  blend.enable = true;
  blend.srcColor = QRhiGraphicsPipeline::SrcAlpha;
  blend.dstColor = QRhiGraphicsPipeline::OneMinusSrcAlpha;
  blend.srcAlpha = QRhiGraphicsPipeline::One;
  blend.dstAlpha = QRhiGraphicsPipeline::OneMinusSrcAlpha;
  pipeline_->setTargetBlends({blend});

  QRhiVertexInputLayout layout;
  layout.setBindings({{4 * sizeof(float)}});
  layout.setAttributes({
      {0, 0, QRhiVertexInputAttribute::Float2, 0},
      {0, 1, QRhiVertexInputAttribute::Float2, 2 * sizeof(float)},
  });
  pipeline_->setVertexInputLayout(layout);
  pipeline_->create();
  initialized_ = true;
}

void ShapePass::setSharedTextures(QRhiTexture *texture1, QRhiTexture *texture2,
                                  QRhiSampler *sampler) {
  texture1_ = texture1;
  texture2_ = texture2;
  sampler_ = sampler;
}

bool ShapePass::shouldRender(const RenderPassContext &context) const {
  return initialized_ && predicate_(context.plan);
}

void ShapePass::prepare(const RenderPassContext &context,
                        QRhiResourceUpdateBatch *updates) {
  const auto &plan = context.plan;
  FeatureUniforms uniforms{};
  const QMatrix4x4 matrix = rhi_->clipSpaceCorrMatrix();
  std::copy(matrix.constData(), matrix.constData() + 16, uniforms.begin());
  uniforms[16] = static_cast<float>(context.contentViewport.width());
  uniforms[17] = static_cast<float>(context.contentViewport.height());
  uniforms[18] = static_cast<float>(context.targetWidth);
  uniforms[19] = static_cast<float>(context.targetHeight);
  uniforms[20] = plan.split;
  uniforms[21] = plan.horizontal ? 1.0F : 0.0F;
  uniforms[22] = plan.dividerThickness;
  uniforms[23] = static_cast<float>(mode_);
  uniforms[24] = plan.captureX;
  uniforms[25] = plan.captureY;
  uniforms[26] = plan.magnifierX;
  uniforms[27] = plan.magnifierY;
  uniforms[28] = plan.magnifierRadius;
  uniforms[29] = plan.magnifierZoom;
  uniforms[30] = 2.0F;
  uniforms[32] = color_.redF();
  uniforms[33] = color_.greenF();
  uniforms[34] = color_.blueF();
  uniforms[35] = color_.alphaF();
  updates->uploadStaticBuffer(vertexBuffer_, kVertices.data());
  updates->updateDynamicBuffer(uniformBuffer_, 0, sizeof(uniforms), &uniforms);
}

void ShapePass::record(QRhiCommandBuffer *commandBuffer,
                       const RenderPassContext &context) {
  const QRectF viewport = context.contentViewport;
  commandBuffer->setGraphicsPipeline(pipeline_);
  commandBuffer->setViewport({
      static_cast<float>(viewport.x()),
      static_cast<float>(viewport.y()),
      static_cast<float>(viewport.width()),
      static_cast<float>(viewport.height()),
  });
  commandBuffer->setScissor({
      static_cast<int>(viewport.x()),
      static_cast<int>(viewport.y()),
      static_cast<int>(viewport.width()),
      static_cast<int>(viewport.height()),
  });
  commandBuffer->setShaderResources(bindings_);
  const QRhiCommandBuffer::VertexInput input(vertexBuffer_, 0);
  commandBuffer->setVertexInput(0, 1, &input);
  commandBuffer->draw(4);
}

void ShapePass::release() {
  delete pipeline_;
  pipeline_ = nullptr;
  delete bindings_;
  bindings_ = nullptr;
  delete uniformBuffer_;
  uniformBuffer_ = nullptr;
  delete vertexBuffer_;
  vertexBuffer_ = nullptr;
  initialized_ = false;
  rhi_ = nullptr;
}

}  // namespace imgsli::app

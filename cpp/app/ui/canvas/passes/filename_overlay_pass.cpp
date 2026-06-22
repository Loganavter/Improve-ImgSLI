#include "ui/canvas/passes/filename_overlay_pass.h"

#include <QFile>
#include <QFont>
#include <QFontMetrics>
#include <QImage>
#include <QMatrix4x4>
#include <QPainter>
#include <QRectF>
#include <rhi/qrhi.h>
#include <rhi/qshader.h>

#include <array>

namespace imgsli::app {

namespace {

QShader loadShader(const QString &path) {
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly)) {
    qFatal("Unable to open overlay shader resource");
  }
  const QShader shader = QShader::fromSerialized(file.readAll());
  if (!shader.isValid()) {
    qFatal("Invalid overlay shader");
  }
  return shader;
}

constexpr std::array<float, 16> kVertices{
    -1.0F, 1.0F, 0.0F, 0.0F, -1.0F, -1.0F, 0.0F, 1.0F,
    1.0F,  1.0F, 1.0F, 0.0F, 1.0F,  -1.0F, 1.0F, 1.0F,
};

}  // namespace

void FilenameOverlayPass::initialize(QRhi *rhi, QRhiRenderTarget *target) {
  release();
  rhi_ = rhi;
  vertexBuffer_ = rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer,
                                 static_cast<quint32>(sizeof(kVertices)));
  vertexBuffer_->create();
  uniformBuffer_ =
      rhi->newBuffer(QRhiBuffer::Dynamic, QRhiBuffer::UniformBuffer, 64);
  uniformBuffer_->create();
  sampler_ = rhi->newSampler(QRhiSampler::Linear, QRhiSampler::Linear,
                             QRhiSampler::None, QRhiSampler::ClampToEdge,
                             QRhiSampler::ClampToEdge);
  sampler_->create();
  texture_ = rhi->newTexture(QRhiTexture::RGBA8, QSize(256, 52));
  texture_->create();
  bindings_ = rhi->newShaderResourceBindings();
  bindings_->setBindings({
      QRhiShaderResourceBinding::uniformBuffer(
          0, QRhiShaderResourceBinding::VertexStage, uniformBuffer_),
      QRhiShaderResourceBinding::sampledTexture(
          1, QRhiShaderResourceBinding::FragmentStage, texture_, sampler_),
  });
  bindings_->create();
  pipeline_ = rhi->newGraphicsPipeline();
  pipeline_->setShaderStages({
      {QRhiShaderStage::Vertex,
       loadShader(QStringLiteral(":/imgsli/shaders/overlay.vert.qsb"))},
      {QRhiShaderStage::Fragment,
       loadShader(QStringLiteral(":/imgsli/shaders/overlay.frag.qsb"))},
  });
  pipeline_->setTopology(QRhiGraphicsPipeline::TriangleStrip);
  pipeline_->setSampleCount(target->sampleCount());
  pipeline_->setShaderResourceBindings(bindings_);
  pipeline_->setRenderPassDescriptor(target->renderPassDescriptor());
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
  uploadKey_.clear();
}

bool FilenameOverlayPass::shouldRender(const RenderPassContext &context) const {
  return context.plan.filenameEnabled;
}

void FilenameOverlayPass::prepare(const RenderPassContext &context,
                                  QRhiResourceUpdateBatch *updates) {
  updates->uploadStaticBuffer(vertexBuffer_, kVertices.data());
  const QMatrix4x4 matrix = rhi_->clipSpaceCorrMatrix();
  updates->updateDynamicBuffer(uniformBuffer_, 0, 64, matrix.constData());
  const QString key =
      context.plan.leftLabel + QStringLiteral("\n") + context.plan.rightLabel;
  if (key == uploadKey_) {
    return;
  }
  uploadKey_ = key;
  QImage image(256, 52, QImage::Format_RGBA8888);
  image.fill(Qt::transparent);
  QPainter painter(&image);
  painter.setRenderHint(QPainter::Antialiasing);
  painter.setBrush(QColor(0, 0, 0, 185));
  painter.setPen(Qt::NoPen);
  painter.drawRoundedRect(QRectF(2, 2, 122, 48), 5, 5);
  painter.drawRoundedRect(QRectF(132, 2, 122, 48), 5, 5);
  QFont font = painter.font();
  font.setPixelSize(16);
  font.setBold(true);
  painter.setFont(font);
  painter.setPen(Qt::white);
  const QFontMetrics metrics(font);
  const QString leftText =
      metrics.elidedText(context.plan.leftLabel, Qt::ElideMiddle, 108);
  const QString rightText =
      metrics.elidedText(context.plan.rightLabel, Qt::ElideMiddle, 108);
  painter.drawText(QRect(8, 2, 108, 48), Qt::AlignVCenter | Qt::AlignLeft,
                   leftText);
  painter.drawText(QRect(140, 2, 108, 48), Qt::AlignVCenter | Qt::AlignRight,
                   rightText);
  painter.end();
  updates->uploadTexture(texture_, image);
}

void FilenameOverlayPass::record(QRhiCommandBuffer *commandBuffer,
                                 const RenderPassContext &context) {
  const QRectF viewport = context.contentViewport;
  const float overlayHeight =
      static_cast<float>(qMin(52.0, viewport.height()));
  commandBuffer->setGraphicsPipeline(pipeline_);
  commandBuffer->setViewport({
      static_cast<float>(viewport.x()),
      static_cast<float>(viewport.y() + viewport.height() - overlayHeight),
      static_cast<float>(viewport.width()),
      overlayHeight,
  });
  commandBuffer->setShaderResources(bindings_);
  const QRhiCommandBuffer::VertexInput input(vertexBuffer_, 0);
  commandBuffer->setVertexInput(0, 1, &input);
  commandBuffer->draw(4);
}

void FilenameOverlayPass::release() {
  delete pipeline_;
  pipeline_ = nullptr;
  delete bindings_;
  bindings_ = nullptr;
  delete texture_;
  texture_ = nullptr;
  delete sampler_;
  sampler_ = nullptr;
  delete uniformBuffer_;
  uniformBuffer_ = nullptr;
  delete vertexBuffer_;
  vertexBuffer_ = nullptr;
  rhi_ = nullptr;
}

}  // namespace imgsli::app

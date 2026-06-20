#include "feature_passes.h"

#include <QFile>
#include <QFont>
#include <QFontMetrics>
#include <QImage>
#include <QMatrix4x4>
#include <QPainter>
#include <QVector4D>
#include <rhi/qrhi.h>
#include <rhi/qshader.h>

#include <algorithm>
#include <array>
#include <functional>

#include "canvas_widget.h"

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

} // namespace

namespace imgsli::app {

class BackgroundPass final : public CanvasRenderPass {
public:
  QString name() const override { return QStringLiteral("background"); }
  CanvasStackRole stackRole() const override {
    return CanvasStackRole::UnderlaySplit;
  }
  void initialize(QRhi *, QRhiRenderTarget *) override {}
  bool shouldRender(const RenderPassContext &) const override { return false; }
  void prepare(const RenderPassContext &, QRhiResourceUpdateBatch *) override {}
  void record(QRhiCommandBuffer *, const RenderPassContext &) override {}
  void release() override {}
};

class ShapePass final : public CanvasRenderPass {
public:
  using Predicate = std::function<bool(const CanvasRenderPlan &)>;

  ShapePass(QString name, CanvasStackRole role, int mode, QColor color,
            Predicate predicate)
      : name_(std::move(name)), role_(role), mode_(mode),
        color_(std::move(color)), predicate_(std::move(predicate)) {}

  QString name() const override { return name_; }
  CanvasStackRole stackRole() const override { return role_; }

  void initialize(QRhi *rhi, QRhiRenderTarget *target) override {
    release();
    rhi_ = rhi;
    vertexBuffer_ =
        rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer,
                       static_cast<quint32>(sizeof(kVertices)));
    vertexBuffer_->create();
    uniformBuffer_ =
        rhi->newBuffer(QRhiBuffer::Dynamic, QRhiBuffer::UniformBuffer,
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

  void setSharedTextures(QRhiTexture *texture1, QRhiTexture *texture2,
                         QRhiSampler *sampler) override {
    texture1_ = texture1;
    texture2_ = texture2;
    sampler_ = sampler;
  }

  bool shouldRender(const RenderPassContext &context) const override {
    return initialized_ && predicate_(context.plan);
  }

  void prepare(const RenderPassContext &context,
               QRhiResourceUpdateBatch *updates) override {
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
    updates->updateDynamicBuffer(uniformBuffer_, 0, sizeof(uniforms),
                                 &uniforms);
  }

  void record(QRhiCommandBuffer *commandBuffer,
              const RenderPassContext &context) override {
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

  void release() override {
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

class FilenameOverlayPass final : public CanvasRenderPass {
public:
  QString name() const override { return QStringLiteral("filename_overlay"); }
  CanvasStackRole stackRole() const override {
    return CanvasStackRole::HudLabel;
  }

  void initialize(QRhi *rhi, QRhiRenderTarget *target) override {
    release();
    rhi_ = rhi;
    vertexBuffer_ =
        rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer,
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

  bool shouldRender(const RenderPassContext &context) const override {
    return context.plan.filenameEnabled;
  }

  void prepare(const RenderPassContext &context,
               QRhiResourceUpdateBatch *updates) override {
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

  void record(QRhiCommandBuffer *commandBuffer,
              const RenderPassContext &context) override {
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

  void release() override {
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

} // namespace imgsli::app

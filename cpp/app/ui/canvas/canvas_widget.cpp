#include "ui/canvas/canvas_widget.h"

#include <QDateTime>
#include <QFile>
#include <QMatrix4x4>
#include <QMouseEvent>
#include <QVector4D>
#include <rhi/qrhi.h>
#include <rhi/qshader.h>

#include <algorithm>
#include <array>
#include <cmath>

#include "ui/canvas_features/registry.h"
#include "core/feature_registry.h"
#include "core/render_pass_registry.h"

namespace {

QShader loadShader(const QString &path) {
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly)) {
    qFatal("Unable to open shader resource");
  }
  const QShader shader = QShader::fromSerialized(file.readAll());
  if (!shader.isValid()) {
    qFatal("Invalid compiled shader");
  }
  return shader;
}

constexpr std::array<float, 16> kVertices{
    -1.0F, 1.0F, 0.0F, 0.0F, -1.0F, -1.0F, 0.0F, 1.0F,
    1.0F,  1.0F, 1.0F, 0.0F, 1.0F,  -1.0F, 1.0F, 1.0F,
};

using CanvasUniforms = std::array<float, 20>;

} // namespace

namespace imgsli::app {

CanvasWidget::CanvasWidget(QWidget *parent)
    : QRhiWidget(parent),
      passRegistry_(std::make_unique<RenderPassRegistry>()) {
  // GNOME Wayland CSD fix: by default QRhiWidget's native surface
  // promotion reparents every ancestor into a native widget through a
  // shortcut path that skips the xdg-decoration handshake — so the
  // top-level window never gets decorated by the Adwaita CSD plugin
  // (child dialogs render fine because they go through the normal
  // QPA show() path). This attribute keeps the promotion local to
  // QRhiWidget so the top-level keeps its standard surface lifecycle.
  // See docs/dev/CPP_RUST_MIGRATION.md "QRhiWidget + GNOME = no
  // window decorations".
  setAttribute(Qt::WA_DontCreateNativeAncestors, true);
  const QString backend = qEnvironmentVariable("IMGSLI_RHI_BACKEND");
  if (backend.compare(QStringLiteral("null"), Qt::CaseInsensitive) == 0) {
    setApi(QRhiWidget::Api::Null);
  } else if (backend.compare(QStringLiteral("opengl"), Qt::CaseInsensitive) ==
             0) {
    setApi(QRhiWidget::Api::OpenGL);
  } else {
    setApi(QRhiWidget::Api::Vulkan);
  }
  registerDefaultRenderPasses(*passRegistry_);
  setMinimumSize(320, 180);
}

CanvasWidget::~CanvasWidget() { releaseRhiResources(); }

void CanvasWidget::registerImage(std::uint64_t textureId, const QImage &image) {
  if (textureId == 0 || image.isNull()) {
    return;
  }
  images_.insert(textureId, image.convertToFormat(QImage::Format_RGBA8888));
  if (plan_.texture1Id == textureId) {
    pendingImages_[0] = images_.value(textureId);
  }
  if (plan_.texture2Id == textureId) {
    pendingImages_[1] = images_.value(textureId);
  }
  update();
}

void CanvasWidget::setRenderPlan(const CanvasRenderPlan &plan) {
  plan_ = plan;
  for (const auto &feature : FeatureRegistry::instance().features()) {
    feature->applyDefaults(plan_);
  }
  pendingImages_[0] = images_.value(plan_.texture1Id);
  pendingImages_[1] = images_.value(plan_.texture2Id);
  if (pendingImages_[1].isNull()) {
    pendingImages_[1] = pendingImages_[0];
  }
  frameRenderedEmitted_ = false;
  update();
}

CanvasRenderPlan CanvasWidget::renderPlan() const { return plan_; }

QStringList CanvasWidget::renderPassNames() const {
  return passRegistry_->names();
}

QHash<std::uint64_t, QImage> CanvasWidget::registeredImages() const {
  return images_;
}

bool CanvasWidget::executeFeatureCommand(const QString &featureName,
                                         const QString &command,
                                         const QVariant &value) {
  for (const auto &feature : FeatureRegistry::instance().features()) {
    if (feature->name() == featureName &&
        feature->execute(plan_, command, value)) {
      update();
      return true;
    }
  }
  return false;
}

void CanvasWidget::initialize(QRhiCommandBuffer *commandBuffer) {
  releaseRhiResources();
  QRhi *renderer = rhi();
  if (renderer == nullptr) {
    return;
  }

  vertexBuffer_ =
      renderer->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer,
                          static_cast<quint32>(sizeof(kVertices)));
  vertexBuffer_->create();

  uniformBuffer_ = renderer->newBuffer(
      QRhiBuffer::Dynamic, QRhiBuffer::UniformBuffer, sizeof(CanvasUniforms));
  uniformBuffer_->create();

  sampler_ = renderer->newSampler(QRhiSampler::Linear, QRhiSampler::Linear,
                                  QRhiSampler::None, QRhiSampler::ClampToEdge,
                                  QRhiSampler::ClampToEdge);
  sampler_->create();

  QImage placeholder(1, 1, QImage::Format_RGBA8888);
  placeholder.fill(Qt::transparent);
  QRhiResourceUpdateBatch *updates = renderer->nextResourceUpdateBatch();
  updates->uploadStaticBuffer(vertexBuffer_, kVertices.data());
  for (int index = 0; index < 2; ++index) {
    textures_[index] =
        renderer->newTexture(QRhiTexture::RGBA8, placeholder.size());
    textures_[index]->create();
    updates->uploadTexture(textures_[index], placeholder);
  }
  commandBuffer->resourceUpdate(updates);

  rebuildShaderResources();
  createPipeline();
  initializePasses();
  pendingImages_[0] = images_.value(plan_.texture1Id);
  pendingImages_[1] = images_.value(plan_.texture2Id);
  if (pendingImages_[1].isNull()) {
    pendingImages_[1] = pendingImages_[0];
  }
}

void CanvasWidget::render(QRhiCommandBuffer *commandBuffer) {
  QRhi *renderer = rhi();
  QRhiRenderTarget *target = renderTarget();
  if (renderer == nullptr || target == nullptr || pipeline_ == nullptr) {
    return;
  }

  uploadPendingTextures(commandBuffer);

  QRhiResourceUpdateBatch *updates = renderer->nextResourceUpdateBatch();
  CanvasUniforms uniforms{};
  const QMatrix4x4 matrix = renderer->clipSpaceCorrMatrix();
  std::copy(matrix.constData(), matrix.constData() + 16, uniforms.begin());
  uniforms[16] = plan_.split;
  uniforms[17] = plan_.horizontal ? 1.0F : 0.0F;
  updates->updateDynamicBuffer(uniformBuffer_, 0, sizeof(uniforms), &uniforms);

  const QRectF viewport = contentViewport();
  const RenderPassContext context{
      .plan = plan_,
      .contentViewport = viewport,
      .texture1 = textures_[0],
      .texture2 = textures_[1],
      .sampler = sampler_,
      .targetWidth = target->pixelSize().width(),
      .targetHeight = target->pixelSize().height(),
  };
  for (const auto &pass : passRegistry_->passes()) {
    if (pass->shouldRender(context)) {
      pass->prepare(context, updates);
    }
  }

  commandBuffer->beginPass(target, plan_.fill, {1.0F, 0}, updates);

  if (plan_.texture1Id != 0 && textures_[0] != nullptr) {
    commandBuffer->setGraphicsPipeline(pipeline_);
    commandBuffer->setViewport({
        static_cast<float>(viewport.x()),
        static_cast<float>(viewport.y()),
        static_cast<float>(viewport.width()),
        static_cast<float>(viewport.height()),
    });
    commandBuffer->setShaderResources(bindings_);
    const QRhiCommandBuffer::VertexInput input(vertexBuffer_, 0);
    commandBuffer->setVertexInput(0, 1, &input);
    commandBuffer->draw(4);
  }
  for (const auto &pass : passRegistry_->passes()) {
    if (pass->shouldRender(context)) {
      pass->record(commandBuffer, context);
    }
  }
  commandBuffer->endPass();
  emit frameRecorded();

  ++fpsFrameCount_;
  const qint64 now = QDateTime::currentMSecsSinceEpoch();
  if (fpsWindowStartMs_ == 0) {
    fpsWindowStartMs_ = now;
  } else if (now - fpsWindowStartMs_ >= 1000) {
    const double fps =
        fpsFrameCount_ * 1000.0 / static_cast<double>(now - fpsWindowStartMs_);
    emit framesPerSecondMeasured(fps);
    fpsWindowStartMs_ = now;
    fpsFrameCount_ = 0;
  }

  if (!frameRenderedEmitted_ && plan_.texture1Id != 0) {
    frameRenderedEmitted_ = true;
    emit frameRendered();
  }
}

void CanvasWidget::releaseResources() { releaseRhiResources(); }

void CanvasWidget::mousePressEvent(QMouseEvent *event) {
  if (event->button() != Qt::LeftButton) {
    QRhiWidget::mousePressEvent(event);
    return;
  }
  const QRectF viewport = contentViewport();
  if (!viewport.contains(event->position())) {
    return;
  }
  const QPointF normalized(
      (event->position().x() - viewport.x()) / viewport.width(),
      (event->position().y() - viewport.y()) / viewport.height());
  const double dividerDistance =
      plan_.horizontal ? qAbs(normalized.y() - plan_.split) * viewport.height()
                       : qAbs(normalized.x() - plan_.split) * viewport.width();
  const double aspect = viewport.width() / qMax(1.0, viewport.height());
  const QPointF magnifierDelta((normalized.x() - plan_.magnifierX) * aspect,
                               normalized.y() - plan_.magnifierY);
  if (dividerDistance <= qMax(6.0, plan_.dividerThickness * 2.0)) {
    dragTarget_ = DragTarget::Divider;
  } else if (plan_.magnifierEnabled &&
             std::hypot(magnifierDelta.x(), magnifierDelta.y()) <=
                 plan_.magnifierRadius) {
    dragTarget_ = DragTarget::Magnifier;
  }
  if (dragTarget_ != DragTarget::None) {
    setCursor(Qt::ClosedHandCursor);
    event->accept();
  }
}

void CanvasWidget::mouseMoveEvent(QMouseEvent *event) {
  if (dragTarget_ == DragTarget::None) {
    QRhiWidget::mouseMoveEvent(event);
    return;
  }
  const QRectF viewport = contentViewport();
  const float x =
      qBound(0.0F,
             static_cast<float>((event->position().x() - viewport.x()) /
                                viewport.width()),
             1.0F);
  const float y =
      qBound(0.0F,
             static_cast<float>((event->position().y() - viewport.y()) /
                                viewport.height()),
             1.0F);
  if (dragTarget_ == DragTarget::Divider) {
    executeFeatureCommand(QStringLiteral("divider"),
                          QStringLiteral("set_split"),
                          plan_.horizontal ? y : x);
  } else {
    executeFeatureCommand(QStringLiteral("magnifier"), QStringLiteral("set_x"),
                          x);
    executeFeatureCommand(QStringLiteral("magnifier"), QStringLiteral("set_y"),
                          y);
  }
  event->accept();
}

void CanvasWidget::mouseReleaseEvent(QMouseEvent *event) {
  if (dragTarget_ != DragTarget::None && event->button() == Qt::LeftButton) {
    dragTarget_ = DragTarget::None;
    unsetCursor();
    event->accept();
    return;
  }
  QRhiWidget::mouseReleaseEvent(event);
}

void CanvasWidget::createPipeline() {
  QRhi *renderer = rhi();
  QRhiRenderTarget *target = renderTarget();
  if (renderer == nullptr || target == nullptr || bindings_ == nullptr) {
    return;
  }
  pipeline_ = renderer->newGraphicsPipeline();
  pipeline_->setShaderStages({
      {QRhiShaderStage::Vertex,
       loadShader(QStringLiteral(":/imgsli/shaders/canvas.vert.qsb"))},
      {QRhiShaderStage::Fragment,
       loadShader(QStringLiteral(":/imgsli/shaders/canvas.frag.qsb"))},
  });
  pipeline_->setTopology(QRhiGraphicsPipeline::TriangleStrip);
  pipeline_->setSampleCount(target->sampleCount());
  pipeline_->setShaderResourceBindings(bindings_);
  pipeline_->setRenderPassDescriptor(target->renderPassDescriptor());

  QRhiVertexInputLayout layout;
  layout.setBindings({{4 * sizeof(float)}});
  layout.setAttributes({
      {0, 0, QRhiVertexInputAttribute::Float2, 0},
      {0, 1, QRhiVertexInputAttribute::Float2, 2 * sizeof(float)},
  });
  pipeline_->setVertexInputLayout(layout);
  pipeline_->create();
}

void CanvasWidget::initializePasses() {
  QRhi *renderer = rhi();
  QRhiRenderTarget *target = renderTarget();
  if (renderer == nullptr || target == nullptr) {
    return;
  }
  for (const auto &pass : passRegistry_->passes()) {
    pass->setSharedTextures(textures_[0], textures_[1], sampler_);
    pass->initialize(renderer, target);
  }
}

void CanvasWidget::releaseRhiResources() {
  if (passRegistry_) {
    for (const auto &pass : passRegistry_->passes()) {
      pass->release();
    }
  }
  delete pipeline_;
  pipeline_ = nullptr;
  delete bindings_;
  bindings_ = nullptr;
  for (QRhiTexture *&texture : textures_) {
    delete texture;
    texture = nullptr;
  }
  delete sampler_;
  sampler_ = nullptr;
  delete uniformBuffer_;
  uniformBuffer_ = nullptr;
  delete vertexBuffer_;
  vertexBuffer_ = nullptr;
}

void CanvasWidget::uploadPendingTextures(QRhiCommandBuffer *commandBuffer) {
  if (pendingImages_[0].isNull() && pendingImages_[1].isNull()) {
    return;
  }
  QRhi *renderer = rhi();
  if (renderer == nullptr) {
    return;
  }
  for (const auto &pass : passRegistry_->passes()) {
    pass->release();
  }
  delete pipeline_;
  pipeline_ = nullptr;
  delete bindings_;
  bindings_ = nullptr;

  QRhiResourceUpdateBatch *updates = renderer->nextResourceUpdateBatch();
  for (int index = 0; index < 2; ++index) {
    if (!pendingImages_[index].isNull()) {
      replaceTexture(index, pendingImages_[index], updates);
      pendingImages_[index] = {};
    }
  }
  commandBuffer->resourceUpdate(updates);
  rebuildShaderResources();
  createPipeline();
  initializePasses();
}

void CanvasWidget::replaceTexture(int index, const QImage &image,
                                  QRhiResourceUpdateBatch *updates) {
  delete textures_[index];
  textures_[index] = rhi()->newTexture(QRhiTexture::RGBA8, image.size());
  textures_[index]->create();
  updates->uploadTexture(textures_[index], image);
}

void CanvasWidget::rebuildShaderResources() {
  QRhi *renderer = rhi();
  if (renderer == nullptr || textures_[0] == nullptr ||
      textures_[1] == nullptr) {
    return;
  }
  delete bindings_;
  bindings_ = renderer->newShaderResourceBindings();
  bindings_->setBindings({
      QRhiShaderResourceBinding::uniformBuffer(
          0,
          QRhiShaderResourceBinding::VertexStage |
              QRhiShaderResourceBinding::FragmentStage,
          uniformBuffer_),
      QRhiShaderResourceBinding::sampledTexture(
          1, QRhiShaderResourceBinding::FragmentStage, textures_[0], sampler_),
      QRhiShaderResourceBinding::sampledTexture(
          2, QRhiShaderResourceBinding::FragmentStage, textures_[1], sampler_),
  });
  bindings_->create();
}

QRectF CanvasWidget::contentViewport() const {
  const QSize targetSize = renderTarget() != nullptr
                               ? renderTarget()->pixelSize()
                               : QSize(width(), height());
  const double scale = qMin(
      targetSize.width() / static_cast<double>(qMax(1, plan_.canvasWidth)),
      targetSize.height() / static_cast<double>(qMax(1, plan_.canvasHeight)));
  const double contentWidth = plan_.canvasWidth * scale;
  const double contentHeight = plan_.canvasHeight * scale;
  return {
      (targetSize.width() - contentWidth) * 0.5,
      (targetSize.height() - contentHeight) * 0.5,
      contentWidth,
      contentHeight,
  };
}

} // namespace imgsli::app

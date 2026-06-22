#include "plugins/export/services/offscreen_renderer.h"

#include <QApplication>
#include <QCryptographicHash>
#include <QDataStream>
#include <QEventLoop>
#include <QIODevice>
#include <QMetaObject>
#include <QScopedValueRollback>
#include <QTimer>
#include <QVariant>
#include <QVariantList>
#include <QVariantMap>

#include <algorithm>

#include "imgsli/contracts/plugin_contract.h"
#include "core/plugin_registry.h"

namespace imgsli::app {

OffscreenRenderer::OffscreenRenderer(QObject *parent) : QObject(parent) {
  setObjectName(QStringLiteral("offscreenRenderer"));
}

OffscreenRenderer::~OffscreenRenderer() {
  if (canvas_) {
    delete canvas_;
  }
}

QImage OffscreenRenderer::renderCanvas(CanvasWidget *source,
                                       const QSize &target) {
  if (source == nullptr) {
    return {};
  }
  return renderPlan(source, source->renderPlan(), target);
}

QImage OffscreenRenderer::renderPlan(CanvasWidget *source,
                                     const CanvasRenderPlan &plan,
                                     const QSize &target) {
  if (source == nullptr || target.isEmpty() || renderInProgress_) {
    return {};
  }
  const QString key = cacheKey(source, plan, target);
  if (const QImage *cached = cache_.object(key)) {
    return *cached;
  }
  QScopedValueRollback rendering(renderInProgress_, true);
  CanvasWidget *offscreen = ensureCanvas();
  if (offscreen == nullptr) {
    return {};
  }

  const auto images = source->registeredImages();
  for (auto it = images.constBegin(); it != images.constEnd(); ++it) {
    offscreen->registerImage(it.key(), it.value());
  }
  offscreen->setRenderPlan(plan);
  if (offscreen->size() != target) {
    offscreen->resize(target);
    QApplication::processEvents();
  }

  QEventLoop loop;
  QTimer timeout;
  bool frameRecorded = false;
  timeout.setSingleShot(true);
  QObject::connect(&timeout, &QTimer::timeout, &loop, &QEventLoop::quit);
  const QMetaObject::Connection rendered = QObject::connect(
      offscreen, &CanvasWidget::frameRecorded, &loop,
      [&frameRecorded, &loop]() {
        frameRecorded = true;
        loop.quit();
      },
      Qt::QueuedConnection);
  offscreen->update();
  timeout.start(3000);
  loop.exec();
  QObject::disconnect(rendered);
  if (!frameRecorded) {
    return {};
  }
  const QImage image = offscreen->grabFramebuffer();
  if (!image.isNull()) {
    const int costKiB =
        std::max(1, static_cast<int>(image.sizeInBytes() / 1024));
    cache_.insert(key, new QImage(image), costKiB);
  }
  return image;
}

QString OffscreenRenderer::cacheKey(CanvasWidget *source,
                                    const CanvasRenderPlan &plan,
                                    const QSize &target) {
  QByteArray payload;
  QDataStream stream(&payload, QIODevice::WriteOnly);
  stream.setVersion(QDataStream::Qt_6_7);
  stream << target << static_cast<quint64>(plan.texture1Id)
         << static_cast<quint64>(plan.texture2Id) << plan.canvasWidth
         << plan.canvasHeight << plan.split << plan.horizontal
         << plan.dividerEnabled << plan.dividerThickness
         << plan.magnifierEnabled << plan.captureX << plan.captureY
         << plan.magnifierX << plan.magnifierY << plan.magnifierRadius
         << plan.magnifierZoom << plan.guidesEnabled << plan.captureEnabled
         << plan.filenameEnabled << plan.pasteOverlayEnabled << plan.leftLabel
         << plan.rightLabel << plan.fill.rgba();
  const auto images = source->registeredImages();
  for (const std::uint64_t textureId :
       {plan.texture1Id, plan.texture2Id}) {
    const QImage image = images.value(textureId);
    stream << static_cast<quint64>(textureId)
           << static_cast<qint64>(image.cacheKey()) << image.size()
           << static_cast<qint32>(image.format());
  }
  return QString::fromLatin1(
      QCryptographicHash::hash(payload, QCryptographicHash::Sha256).toHex());
}

CanvasWidget *OffscreenRenderer::ensureCanvas() {
  if (canvas_) {
    return canvas_;
  }
  auto *offscreen = new CanvasWidget();
  offscreen->setObjectName(QStringLiteral("sharedOffscreenCanvas"));
  offscreen->setAttribute(Qt::WA_DontShowOnScreen, true);
  offscreen->setAttribute(Qt::WA_TranslucentBackground, true);
  offscreen->setAutoFillBackground(false);
  offscreen->setMinimumSize(1, 1);
  offscreen->show();
  QApplication::processEvents();
  canvas_ = offscreen;
  return offscreen;
}

namespace {

class OffscreenRendererPlugin final
    : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override {
    return QStringLiteral("offscreen_renderer");
  }

  QString displayName() const override {
    return QStringLiteral("Offscreen Renderer");
  }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {
        QStringLiteral("offscreen_renderer.instance"),
        QStringLiteral("offscreen_renderer.render_canvas"),
        QStringLiteral("offscreen_renderer.render_plan"),
        QStringLiteral("offscreen_renderer.render_batch"),
        QStringLiteral("offscreen_renderer.cache_size"),
        QStringLiteral("offscreen_renderer.cache_clear"),
    };
    return def;
  }

  bool providesService(const QString &serviceId) const override {
    return serviceId == QStringLiteral("offscreen_renderer.instance") ||
           serviceId == QStringLiteral("offscreen_renderer.render_canvas") ||
           serviceId == QStringLiteral("offscreen_renderer.render_plan") ||
           serviceId == QStringLiteral("offscreen_renderer.render_batch") ||
           serviceId == QStringLiteral("offscreen_renderer.cache_size") ||
           serviceId == QStringLiteral("offscreen_renderer.cache_clear");
  }

  QVariant callService(const QString &serviceId,
                       const QVariantMap &args) override {
    if (serviceId == QStringLiteral("offscreen_renderer.instance")) {
      return QVariant::fromValue<QObject *>(ensureRenderer());
    }
    if (serviceId == QStringLiteral("offscreen_renderer.cache_size")) {
      return ensureRenderer()->cacheSize();
    }
    if (serviceId == QStringLiteral("offscreen_renderer.cache_clear")) {
      ensureRenderer()->clearCache();
      return true;
    }
    if (serviceId == QStringLiteral("offscreen_renderer.render_batch")) {
      QVariantList images;
      const QVariantList requests =
          args.value(QStringLiteral("requests")).toList();
      images.reserve(requests.size());
      for (const QVariant &requestValue : requests) {
        const QVariantMap request = requestValue.toMap();
        auto *source = qobject_cast<CanvasWidget *>(
            request.value(QStringLiteral("canvas")).value<QObject *>());
        const QSize target(request.value(QStringLiteral("width")).toInt(),
                           request.value(QStringLiteral("height")).toInt());
        QImage image;
        if (request.contains(QStringLiteral("plan"))) {
          image = ensureRenderer()->renderPlan(
              source,
              request.value(QStringLiteral("plan")).value<CanvasRenderPlan>(),
              target);
        } else {
          image = ensureRenderer()->renderCanvas(source, target);
        }
        images.append(QVariant::fromValue(image));
        if (image.isNull()) {
          break;
        }
      }
      return images;
    }
    auto *source = qobject_cast<CanvasWidget *>(
        args.value(QStringLiteral("canvas")).value<QObject *>());
    const QSize target(args.value(QStringLiteral("width")).toInt(),
                       args.value(QStringLiteral("height")).toInt());
    if (serviceId == QStringLiteral("offscreen_renderer.render_canvas")) {
      return QVariant::fromValue(ensureRenderer()->renderCanvas(source, target));
    }
    if (serviceId == QStringLiteral("offscreen_renderer.render_plan")) {
      const CanvasRenderPlan plan =
          args.value(QStringLiteral("plan")).value<CanvasRenderPlan>();
      return QVariant::fromValue(
          ensureRenderer()->renderPlan(source, plan, target));
    }
    return {};
  }

 private:
  OffscreenRenderer *ensureRenderer() {
    if (renderer_ == nullptr) {
      renderer_ = new OffscreenRenderer();
    }
    return renderer_;
  }

  QPointer<OffscreenRenderer> renderer_;
};

IMGSLI_REGISTER_PLUGIN(OffscreenRendererPlugin);

}  // namespace
}  // namespace imgsli::app

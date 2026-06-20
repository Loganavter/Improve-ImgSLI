// Phase 2 shell / Phase 3 canvas smoke:
//   * own the stateful Rust store from a Qt QObject,
//   * decode image bytes in Rust,
//   * build a Rust render-plan POD,
//   * execute the plan in a C++ QRhiWidget.
//
// Everything Qt-touching stays on this side. Rust never sees QObject types.

#include <QApplication>
#include <QElapsedTimer>
#include <QFileDialog>
#include <QImage>
#include <QLabel>
#include <QMainWindow>
#include <QPainter>
#include <QPlainTextEdit>
#include <QSlider>
#include <QString>
#include <QTimer>
#include <QVBoxLayout>
#include <QWidget>

#include <cstdio>
#include <memory>
#include <string>

#include <QSettings>
#include <QTabWidget>

#include "canvas_widget.h"
#include "feature_registry.h"
#include "i18n_helper.h"
#include "imgsli_core_bridge/bridge.h"
#include "settings_application_service.h"
#include "settings_dialog.h"
#include "tab_registry.h"
#include "sli/toolkit/button.h"
#include "sli/toolkit/combo_box.h"
#include "sli/toolkit/theme.h"
#include "store.h"

namespace {

QString rs_to_q(const rust::String &s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

QString roundTripDemo() {
  try {
    const rust::String out = imgsli::settings_roundtrip_json(
        R"({"theme": "dark", "window_width": 1600})");
    return rs_to_q(out);
  } catch (const std::exception &ex) {
    return QStringLiteral("settings_roundtrip_json failed: %1")
        .arg(QString::fromUtf8(ex.what()));
  }
}

QImage decodeImage(const QString &path, QString *error) {
  const QByteArray utf8 = path.toUtf8();
  try {
    const auto decoded = imgsli::decode_image_rgba8(
        std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())));
    if (decoded.width == 0 || decoded.height == 0 || decoded.pixels.empty()) {
      *error = QStringLiteral("decoder returned an empty image");
      return {};
    }
    const auto *bytes = reinterpret_cast<const uchar *>(decoded.pixels.data());
    return QImage(bytes, static_cast<int>(decoded.width),
                  static_cast<int>(decoded.height),
                  static_cast<qsizetype>(decoded.width) * 4,
                  QImage::Format_RGBA8888)
        .copy();
  } catch (const std::exception &ex) {
    *error = QString::fromUtf8(ex.what());
    return {};
  }
}

QImage fitImageToCanvas(const QImage &image, const QSize &canvasSize) {
  QImage result(canvasSize, QImage::Format_RGBA8888);
  result.fill(Qt::transparent);
  const QImage scaled =
      image.scaled(canvasSize, Qt::KeepAspectRatio, Qt::SmoothTransformation);
  QPainter painter(&result);
  painter.drawImage(QPoint((canvasSize.width() - scaled.width()) / 2,
                           (canvasSize.height() - scaled.height()) / 2),
                    scaled);
  return result;
}

struct ComparisonInput {
  QString leftPath;
  QString rightPath;
  QImage left;
  QImage right;
  float split = 0.5F;
  bool horizontal = false;
  bool magnifier = true;
  bool guides = true;
  bool pasteOverlay = false;
};

} // namespace

int main(int argc, char **argv) {
  QApplication app(argc, argv);
  sli::toolkit::Theme::apply(app, sli::toolkit::Theme::Mode::Dark);

  // Wire the Rust-backed translation store to the Python project's existing
  // JSON dictionaries. C++ widgets call imgsli::app::tr("…").
  imgsli::app::initI18n(
      QStringLiteral(IMGSLI_I18N_ROOT));
  imgsli::app::setLanguage(QStringLiteral("en"));

  QMainWindow window;
  window.setWindowTitle(QStringLiteral("ImgSLI — C++/Rust Phase 3"));

  auto *central = new QWidget(&window);
  auto *layout = new QVBoxLayout(central);

  layout->addWidget(new QLabel(rs_to_q(imgsli::core_greeting("Qt"))));
  auto *canvas = new imgsli::app::CanvasWidget(central);
  layout->addWidget(canvas, 3);
  const QStringList startupArguments = app.arguments();
  const bool smokeExit =
      startupArguments.contains(QStringLiteral("--smoke-exit"));
  const qsizetype snapshotIndex =
      startupArguments.indexOf(QStringLiteral("--snapshot"));
  const QString snapshotPath =
      snapshotIndex >= 0 && snapshotIndex + 1 < startupArguments.size()
          ? startupArguments.at(snapshotIndex + 1)
          : QString();
  if (smokeExit || !snapshotPath.isEmpty()) {
    QObject::connect(
        canvas, &imgsli::app::CanvasWidget::frameRendered, &app,
        [canvas, snapshotPath, &app]() {
          if (!snapshotPath.isEmpty()) {
            canvas->grabFramebuffer().save(snapshotPath);
          }
          app.quit();
        },
        Qt::QueuedConnection);
  }
  if (startupArguments.contains(QStringLiteral("--contract-check"))) {
    const QStringList requiredPasses{
        QStringLiteral("background"),       QStringLiteral("divider"),
        QStringLiteral("magnifier"),        QStringLiteral("guides"),
        QStringLiteral("filename_overlay"), QStringLiteral("capture"),
        QStringLiteral("paste_overlay"),
    };
    const QStringList requiredFeatures{
        QStringLiteral("divider"), QStringLiteral("magnifier"),
        QStringLiteral("guides"),  QStringLiteral("filename_overlay"),
        QStringLiteral("capture"), QStringLiteral("paste_overlay"),
    };
    const QStringList passNames = canvas->renderPassNames();
    const QStringList featureNames =
        imgsli::app::FeatureRegistry::instance().names();
    for (const QString &name : requiredPasses) {
      if (!passNames.contains(name)) {
        qCritical("Missing render pass: %s", qPrintable(name));
        return 2;
      }
    }
    for (const QString &name : requiredFeatures) {
      if (!featureNames.contains(name)) {
        qCritical("Missing canvas feature: %s", qPrintable(name));
        return 3;
      }
    }
    const auto &features = imgsli::app::FeatureRegistry::instance().features();
    const auto hasCommand = [&features](const QString &featureName,
                                        const QString &command) {
      for (const auto &feature : features) {
        if (feature->name() == featureName) {
          return feature->commandIds().contains(command);
        }
      }
      return false;
    };
    if (!hasCommand(QStringLiteral("divider"), QStringLiteral("set_split")) ||
        !hasCommand(QStringLiteral("magnifier"), QStringLiteral("set_x")) ||
        !hasCommand(QStringLiteral("guides"), QStringLiteral("set_enabled"))) {
      qCritical("Required feature commands are not registered");
      return 4;
    }
    // Phase 4 acceptance: workspace tab registry populated.
    const QStringList requiredTabs{QStringLiteral("multi_compare"),
                                   QStringLiteral("video_editor"),
                                   QStringLiteral("export")};
    for (const QString &sessionType : requiredTabs) {
      if (imgsli::app::TabRegistry::instance().find(sessionType) == nullptr) {
        qCritical("Missing tab: %s", qPrintable(sessionType));
        return 6;
      }
    }
    canvas->setRenderPlan({
        .texture1Id = 1,
        .texture2Id = 2,
        .dividerEnabled = true,
        .magnifierEnabled = true,
        .guidesEnabled = true,
    });
    if (!canvas->executeFeatureCommand(QStringLiteral("divider"),
                                       QStringLiteral("set_split"), 0.25F) ||
        qAbs(canvas->renderPlan().split - 0.25F) > 0.0001F) {
      qCritical("Divider feature command roundtrip failed");
      return 5;
    }
    qInfo("Phase 3 contracts registered: %lld passes, %lld features",
          static_cast<long long>(passNames.size()),
          static_cast<long long>(featureNames.size()));
    return 0;
  }
  const qsizetype benchmarkIndex =
      startupArguments.indexOf(QStringLiteral("--benchmark-frames"));
  const int benchmarkFrames =
      benchmarkIndex >= 0 && benchmarkIndex + 1 < startupArguments.size()
          ? startupArguments.at(benchmarkIndex + 1).toInt()
          : 0;
  if (benchmarkFrames > 0) {
    auto *timer = new QElapsedTimer();
    auto *count = new int(0);
    QObject::connect(
        canvas, &imgsli::app::CanvasWidget::frameRecorded, canvas,
        [canvas, timer, count, benchmarkFrames, &app]() {
          if (!timer->isValid()) {
            timer->start();
          }
          ++(*count);
          if (*count >= benchmarkFrames) {
            const double seconds = timer->elapsed() / 1000.0;
            const double fps = seconds > 0.0 ? *count / seconds : 0.0;
            std::fprintf(stdout, "IMGSLI_BENCHMARK_FPS=%.2f\n", fps);
            std::fflush(stdout);
            app.quit();
            return;
          }
          canvas->update();
        },
        Qt::QueuedConnection);
  }

  auto *store = new imgsli::app::Store(central);
  auto *openButton =
      new sli::toolkit::Button(QStringLiteral("Open image pair…"),
                               sli::toolkit::Button::Variant::Surface, central);
  layout->addWidget(openButton);

  auto *splitSlider = new QSlider(Qt::Horizontal, central);
  splitSlider->setRange(0, 1000);
  splitSlider->setValue(500);
  layout->addWidget(new QLabel(QStringLiteral("Split position:"), central));
  layout->addWidget(splitSlider);

  auto *orientationButton =
      new sli::toolkit::Button(QStringLiteral("Horizontal split"),
                               sli::toolkit::Button::Variant::Default, central);
  orientationButton->setCheckable(true);
  auto *magnifierButton =
      new sli::toolkit::Button(QStringLiteral("Magnifier"),
                               sli::toolkit::Button::Variant::Default, central);
  magnifierButton->setCheckable(true);
  magnifierButton->setChecked(true);
  auto *guidesButton =
      new sli::toolkit::Button(QStringLiteral("Guides"),
                               sli::toolkit::Button::Variant::Default, central);
  guidesButton->setCheckable(true);
  guidesButton->setChecked(true);
  auto *pasteButton =
      new sli::toolkit::Button(QStringLiteral("Paste preview"),
                               sli::toolkit::Button::Variant::Default, central);
  pasteButton->setCheckable(true);
  layout->addWidget(orientationButton);
  layout->addWidget(magnifierButton);
  layout->addWidget(guidesButton);
  layout->addWidget(pasteButton);

  auto *state = new QPlainTextEdit(central);
  state->setReadOnly(true);
  state->setPlainText(store->stateJson());
  layout->addWidget(new QLabel(QStringLiteral("Live Rust store state:")));
  layout->addWidget(state, 1);

  auto *theme = new sli::toolkit::ComboBox(central);
  theme->addItems({
      QStringLiteral("system"),
      QStringLiteral("light"),
      QStringLiteral("dark"),
  });
  layout->addWidget(
      new QLabel(QStringLiteral("Dispatch SetTheme through Rust reducer:")));
  layout->addWidget(theme);

  const auto comparison = std::make_shared<ComparisonInput>();
  const auto applyComparison = [store, canvas, comparison]() {
    if (comparison->left.isNull()) {
      return;
    }
    try {
      const QImage right =
          comparison->right.isNull() ? comparison->left : comparison->right;
      const QString rightPath = comparison->rightPath.isEmpty()
                                    ? comparison->leftPath
                                    : comparison->rightPath;
      const QSize canvasSize(qMax(comparison->left.width(), right.width()),
                             qMax(comparison->left.height(), right.height()));
      const QByteArray leftUtf8 = comparison->leftPath.toUtf8();
      const QByteArray rightUtf8 = rightPath.toUtf8();
      const auto plan = imgsli::build_compare_render_plan(
          std::string(leftUtf8.constData(), leftUtf8.size()),
          std::string(rightUtf8.constData(), rightUtf8.size()),
          static_cast<std::uint32_t>(canvasSize.width()),
          static_cast<std::uint32_t>(canvasSize.height()), comparison->split,
          comparison->horizontal, comparison->magnifier, comparison->guides,
          comparison->pasteOverlay);
      canvas->registerImage(plan.texture1_id,
                            fitImageToCanvas(comparison->left, canvasSize));
      canvas->registerImage(plan.texture2_id,
                            fitImageToCanvas(right, canvasSize));
      canvas->setRenderPlan({
          .texture1Id = plan.texture1_id,
          .texture2Id = plan.texture2_id,
          .canvasWidth = plan.canvas_w,
          .canvasHeight = plan.canvas_h,
          .split = plan.split,
          .horizontal = plan.horizontal,
          .dividerEnabled = plan.divider_enabled,
          .dividerThickness = plan.divider_thickness,
          .magnifierEnabled = plan.magnifier_enabled,
          .captureX = plan.capture_x,
          .captureY = plan.capture_y,
          .magnifierX = plan.magnifier_x,
          .magnifierY = plan.magnifier_y,
          .magnifierRadius = plan.magnifier_radius,
          .magnifierZoom = plan.magnifier_zoom,
          .guidesEnabled = plan.guides_enabled,
          .captureEnabled = plan.capture_enabled,
          .filenameEnabled = plan.filename_enabled,
          .pasteOverlayEnabled = plan.paste_overlay_enabled,
          .leftLabel = rs_to_q(plan.left_label),
          .rightLabel = rs_to_q(plan.right_label),
          .fill = QColor(plan.fill_r, plan.fill_g, plan.fill_b, plan.fill_a),
      });
      QString escapedPath = comparison->leftPath;
      escapedPath.replace(u'\\', QStringLiteral("\\\\"));
      escapedPath.replace(u'"', QStringLiteral("\\\""));
      store->dispatch(
          QStringLiteral(
              R"({"SetActiveImagePath":{"slot":"Left","path":"%1"}})")
              .arg(escapedPath));
    } catch (const std::exception &ex) {
      store->dispatchFailed(QString::fromUtf8(ex.what()));
    }
  };
  const auto openPair = [comparison, applyComparison, store](
                            const QString &leftPath, const QString &rightPath) {
    if (leftPath.isEmpty()) {
      return;
    }
    QString error;
    const QImage left = decodeImage(leftPath, &error);
    if (left.isNull()) {
      store->dispatchFailed(QStringLiteral("Decode failed: %1").arg(error));
      return;
    }
    QImage right;
    if (!rightPath.isEmpty()) {
      right = decodeImage(rightPath, &error);
      if (right.isNull()) {
        store->dispatchFailed(QStringLiteral("Decode failed: %1").arg(error));
        return;
      }
    }
    comparison->leftPath = leftPath;
    comparison->rightPath = rightPath;
    comparison->left = left;
    comparison->right = right;
    applyComparison();
  };
  QObject::connect(
      openButton, &sli::toolkit::Button::clicked, store, [openPair, &window]() {
        const QStringList paths = QFileDialog::getOpenFileNames(
            &window, QStringLiteral("Open one or two images"), {},
            QStringLiteral(
                "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff);;"
                "All files (*)"));
        if (!paths.isEmpty()) {
          openPair(paths[0], paths.size() > 1 ? paths[1] : QString());
        }
      });
  QObject::connect(splitSlider, &QSlider::valueChanged, canvas,
                   [comparison, applyComparison](int value) {
                     comparison->split = value / 1000.0F;
                     applyComparison();
                   });
  QObject::connect(orientationButton, &sli::toolkit::Button::toggled, canvas,
                   [comparison, applyComparison](bool enabled) {
                     comparison->horizontal = enabled;
                     applyComparison();
                   });
  QObject::connect(magnifierButton, &sli::toolkit::Button::toggled, canvas,
                   [comparison, applyComparison](bool enabled) {
                     comparison->magnifier = enabled;
                     applyComparison();
                   });
  QObject::connect(guidesButton, &sli::toolkit::Button::toggled, canvas,
                   [comparison, applyComparison](bool enabled) {
                     comparison->guides = enabled;
                     applyComparison();
                   });
  QObject::connect(pasteButton, &sli::toolkit::Button::toggled, canvas,
                   [comparison, applyComparison](bool enabled) {
                     comparison->pasteOverlay = enabled;
                     applyComparison();
                   });
  QObject::connect(theme, &sli::toolkit::ComboBox::currentTextChanged, store,
                   [store, &app](const QString &value) {
                     sli::toolkit::Theme::applyNamed(app, value);
                     store->dispatch(
                         QStringLiteral(R"({"SetTheme":"%1"})").arg(value));
                   });
  QObject::connect(store, &imgsli::app::Store::stateChanged, state,
                   [state](const QString &json, const QString &scope) {
                     state->setPlainText(
                         QStringLiteral("scope: %1\n\n%2").arg(scope, json));
                   });
  QObject::connect(store, &imgsli::app::Store::dispatchFailed, state,
                   [state](const QString &message) {
                     state->setPlainText(
                         QStringLiteral("dispatch failed: %1").arg(message));
                   });

  auto *qsettings = new QSettings(QStringLiteral("ImgSLI"),
                                  QStringLiteral("ImgSLI"), &window);
  auto *settingsService = new imgsli::app::SettingsApplicationService(
      store, qsettings, &window);
  // Workspace tab registry — Phase 4. Adds an extra tab strip below the
  // canvas to verify that registered tabs can actually mount.
  const auto &registeredTabs = imgsli::app::TabRegistry::instance().tabs();
  if (!registeredTabs.empty()) {
    auto *workspaceTabs = new QTabWidget(central);
    for (auto *tab : registeredTabs) {
      QWidget *page = tab->createPage(workspaceTabs);
      workspaceTabs->addTab(page, tab->displayName());
    }
    layout->addWidget(workspaceTabs, 1);
  }

  auto *settingsButton =
      new sli::toolkit::Button(QStringLiteral("Settings…"),
                               sli::toolkit::Button::Variant::Surface, central);
  layout->addWidget(settingsButton);
  QObject::connect(settingsButton, &sli::toolkit::Button::clicked, &window,
                   [&window, state, settingsService]() {
                     imgsli::app::SettingsDialog dialog(&window);
                     const QString prevJson = dialog.normalizedJson();
                     if (dialog.exec() == QDialog::Accepted) {
                       const QString nextJson = dialog.normalizedJson();
                       const int changes =
                           settingsService->apply(prevJson, nextJson);
                       state->setPlainText(
                           QStringLiteral(
                               "settings dialog accepted (%1 changes)\n\n%2")
                               .arg(changes)
                               .arg(nextJson));
                     }
                   });

  auto *roundtrip = new QPlainTextEdit(central);
  roundtrip->setReadOnly(true);
  roundtrip->setPlainText(roundTripDemo());
  layout->addWidget(new QLabel(QStringLiteral("Round-tripped partial JSON:")));
  layout->addWidget(roundtrip, 1);

  window.setCentralWidget(central);
  window.resize(820, 720);
  window.show();
  const qsizetype compareIndex =
      startupArguments.indexOf(QStringLiteral("--compare"));
  comparison->horizontal =
      startupArguments.contains(QStringLiteral("--horizontal"));
  comparison->magnifier =
      !startupArguments.contains(QStringLiteral("--no-magnifier"));
  comparison->guides =
      !startupArguments.contains(QStringLiteral("--no-guides"));
  comparison->pasteOverlay =
      startupArguments.contains(QStringLiteral("--show-paste"));
  const qsizetype splitIndex =
      startupArguments.indexOf(QStringLiteral("--split"));
  if (splitIndex >= 0 && splitIndex + 1 < startupArguments.size()) {
    comparison->split =
        qBound(0.0F, startupArguments.at(splitIndex + 1).toFloat(), 1.0F);
  }
  if (compareIndex >= 0 && compareIndex + 2 < startupArguments.size()) {
    const QString leftPath = startupArguments.at(compareIndex + 1);
    const QString rightPath = startupArguments.at(compareIndex + 2);
    QTimer::singleShot(0, &app, [openPair, leftPath, rightPath]() {
      openPair(leftPath, rightPath);
    });
  } else {
    const qsizetype openIndex =
        startupArguments.indexOf(QStringLiteral("--open"));
    if (openIndex >= 0 && openIndex + 1 < startupArguments.size()) {
      const QString path = startupArguments.at(openIndex + 1);
      QTimer::singleShot(0, &app,
                         [openPair, path]() { openPair(path, QString()); });
    }
  }

  return app.exec();
}

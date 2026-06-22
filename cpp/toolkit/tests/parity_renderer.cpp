// C++ side of the cross-language widget parity harness.
//
// Driven by tests/parity/run_parity.py — both this executable and
// tests/parity/python_renderer.py read the same cases.json corpus, build a
// widget from the same config dict, force the requested state, and render
// to a PNG. The driver diffs the two PNGs pixel-by-pixel; any divergence
// proves the C++ port is doing something the Python original does not.
//
// Two modes:
//   --mode render --case <id> --output <png_path>
//   --mode query  --case <id>                              (prints to stdout)
//
// Cases corpus path is fixed via env var IMGSLI_PARITY_CASES; the CMake
// test entry sets it.

#include <QApplication>
#include <QColor>
#include <QFile>
#include <QFocusEvent>
#include <QFont>
#include <QHBoxLayout>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QPainter>
#include <QString>
#include <QTextStream>
#include <QWidget>

#include <iostream>
#include <memory>
#include <optional>
#include <utility>
#include <vector>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/capabilities/scroll_capability.h"
#include "sli/toolkit/buttons/controller.h"
#include "sli/toolkit/buttons/layers/ripple.h"
#include "sli/toolkit/buttons/state.h"
#include "sli/toolkit/theme.h"

using namespace sli::toolkit;

namespace {

Button::Variant parseVariant(const QString& name) {
  if (name == QStringLiteral("default")) return Button::Variant::Default;
  if (name == QStringLiteral("surface")) return Button::Variant::Surface;
  if (name == QStringLiteral("ghost")) return Button::Variant::Ghost;
  if (name == QStringLiteral("subtle")) return Button::Variant::Subtle;
  return Button::Variant::Surface;
}

QJsonObject loadCorpus(const QString& path) {
  QFile f(path);
  if (!f.open(QIODevice::ReadOnly)) {
    std::cerr << "parity_renderer: cannot open cases file: "
              << path.toStdString() << '\n';
    std::exit(2);
  }
  QJsonParseError err;
  const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
  if (doc.isNull()) {
    std::cerr << "parity_renderer: invalid JSON in cases file: "
              << err.errorString().toStdString() << '\n';
    std::exit(2);
  }
  return doc.object();
}

QJsonObject findById(const QJsonObject& corpus, const QString& section,
                     const QString& id) {
  const QJsonArray arr = corpus.value(section).toArray();
  for (const auto& v : arr) {
    const QJsonObject o = v.toObject();
    if (o.value(QStringLiteral("id")).toString() == id) {
      return o;
    }
  }
  std::cerr << "parity_renderer: case id not found in " << section.toStdString()
            << ": " << id.toStdString() << '\n';
  std::exit(2);
}

Button* buildButton(const QJsonObject& config, QWidget* parent) {
  Button::Config cfg;
  if (config.contains(QStringLiteral("text"))) {
    cfg.text = config.value(QStringLiteral("text")).toString();
  }
  if (config.contains(QStringLiteral("variant"))) {
    cfg.variant = parseVariant(config.value(QStringLiteral("variant")).toString());
  }
  if (config.contains(QStringLiteral("size"))) {
    const QJsonArray s = config.value(QStringLiteral("size")).toArray();
    if (s.size() == 2) {
      cfg.size = QSize(s.at(0).toInt(), s.at(1).toInt());
    }
  }
  if (config.contains(QStringLiteral("icon_size"))) {
    cfg.iconSize = config.value(QStringLiteral("icon_size")).toInt();
  }
  if (config.contains(QStringLiteral("toggle"))) {
    cfg.toggle = config.value(QStringLiteral("toggle")).toBool();
  }
  if (config.contains(QStringLiteral("scrollable"))) {
    const QJsonArray s = config.value(QStringLiteral("scrollable")).toArray();
    if (s.size() == 2) {
      cfg.scrollable = std::make_pair(s.at(0).toInt(), s.at(1).toInt());
    }
  }
  if (config.contains(QStringLiteral("long_press_ms"))) {
    cfg.longPressMs = config.value(QStringLiteral("long_press_ms")).toInt();
  }
  if (config.contains(QStringLiteral("show_underline"))) {
    cfg.showUnderline = config.value(QStringLiteral("show_underline")).toBool();
  }
  if (config.contains(QStringLiteral("background_color"))) {
    cfg.backgroundColor =
        QColor(config.value(QStringLiteral("background_color")).toString());
  }
  // `corner_radius` is a shape-spec parameter on the Python side — there's
  // no `Button::Config.cornerRadius` yet, so unsupported keys flag the gap
  // explicitly instead of being silently dropped.
  if (config.contains(QStringLiteral("corner_radius"))) {
    std::cerr << "parity_renderer: WARNING — config key 'corner_radius' is "
                 "not yet exposed via Button::Config; rendering with default.\n";
  }
  return new Button(cfg, parent);
}

void applyState(Button* btn, const QString& state) {
  if (state == QStringLiteral("default")) {
    return;
  }
  if (state == QStringLiteral("hover")) {
    // Force the controller's _main region into Hovered — this is how the
    // mouseMoveEvent path lands when the cursor enters. We bypass the
    // mouse event because offscreen Qt doesn't synthesize them reliably.
    auto* controller =
        btn->property("buttonController").value<buttons::ButtonController*>();
    if (controller != nullptr) {
      controller->setState(QStringLiteral("_main"),
                           buttons::ButtonState::Hovered, true);
    }
    return;
  }
  if (state == QStringLiteral("pressed")) {
    auto* controller =
        btn->property("buttonController").value<buttons::ButtonController*>();
    if (controller != nullptr) {
      controller->setState(QStringLiteral("_main"),
                           buttons::ButtonState::Pressed, true);
    }
    return;
  }
  if (state == QStringLiteral("checked")) {
    btn->setChecked(true);
    return;
  }
  if (state == QStringLiteral("focused")) {
    btn->setFocus();
    QFocusEvent ev(QEvent::FocusIn, Qt::OtherFocusReason);
    QApplication::sendEvent(btn, &ev);
    return;
  }
  if (state == QStringLiteral("disabled")) {
    btn->setEnabled(false);
    return;
  }
  std::cerr << "parity_renderer: unknown state: " << state.toStdString() << '\n';
  std::exit(2);
}

void renderCase(const QJsonObject& corpus, const QString& id,
                const QString& outputPath) {
  const QJsonObject testCase = findById(corpus, QStringLiteral("cases"), id);
  const QJsonArray canvasArr = testCase.value(QStringLiteral("canvas")).toArray();
  if (canvasArr.size() != 2) {
    std::cerr << "parity_renderer: case missing canvas: " << id.toStdString()
              << '\n';
    std::exit(2);
  }
  const QSize canvas(canvasArr.at(0).toInt(), canvasArr.at(1).toInt());

  auto host = std::make_unique<QWidget>();
  host->setObjectName(QStringLiteral("parity-host"));
  host->resize(canvas);
  // Background = theme window color, so both sides composite the button
  // against the same backdrop.
  QPalette pal = host->palette();
  pal.setColor(QPalette::Window, Theme::palette().window);
  host->setAutoFillBackground(true);
  host->setPalette(pal);

  const QJsonObject config = testCase.value(QStringLiteral("config")).toObject();
  Button* btn = buildButton(config, host.get());
  // Center the button in the canvas, using its sizeHint() unless explicit
  // size= was requested.
  QSize btnSize = btn->sizeHint();
  if (config.contains(QStringLiteral("size"))) {
    const QJsonArray s = config.value(QStringLiteral("size")).toArray();
    btnSize = QSize(s.at(0).toInt(), s.at(1).toInt());
  }
  btn->resize(btnSize);
  btn->move((canvas.width() - btnSize.width()) / 2,
            (canvas.height() - btnSize.height()) / 2);

  const QString state = testCase.value(QStringLiteral("state"))
                            .toString(QStringLiteral("default"));
  applyState(btn, state);

  host->ensurePolished();
  btn->ensurePolished();

  QImage image(canvas, QImage::Format_ARGB32_Premultiplied);
  image.fill(Theme::palette().window);
  QPainter painter(&image);
  host->render(&painter, QPoint(), QRegion(host->rect()),
               QWidget::DrawWindowBackground | QWidget::DrawChildren);
  painter.end();

  if (!image.save(outputPath, "PNG")) {
    std::cerr << "parity_renderer: failed to write " << outputPath.toStdString()
              << '\n';
    std::exit(3);
  }
}

void runQuery(const QJsonObject& corpus, const QString& id) {
  const QJsonObject q = findById(corpus, QStringLiteral("queries"), id);
  const QJsonObject config = q.value(QStringLiteral("config")).toObject();
  const QString query = q.value(QStringLiteral("query")).toString();

  auto host = std::make_unique<QWidget>();
  host->resize(200, 100);
  Button* btn = buildButton(config, host.get());

  QTextStream out(stdout);
  if (query == QStringLiteral("focusPolicy")) {
    switch (btn->focusPolicy()) {
      case Qt::NoFocus:      out << "NoFocus";      break;
      case Qt::TabFocus:     out << "TabFocus";     break;
      case Qt::ClickFocus:   out << "ClickFocus";   break;
      case Qt::StrongFocus:  out << "StrongFocus";  break;
      case Qt::WheelFocus:   out << "WheelFocus";   break;
    }
  } else if (query == QStringLiteral("hasExplicitCursor")) {
    out << (btn->testAttribute(Qt::WA_SetCursor) ? "true" : "false");
  } else if (query == QStringLiteral("isCheckable")) {
    out << (btn->isCheckable() ? "true" : "false");
  } else if (query == QStringLiteral("sizeHintWidth")) {
    // Match Python's measurement — query the actual instance width after
    // construction (Python's `size=` calls setFixedSize). On the C++ side
    // the Config ctor now does the same, so width() == requested w.
    out << btn->width();
  } else if (query == QStringLiteral("rippleActiveAfterPress")) {
    // Show, press the center, and inspect the controller's runtime ripple.
    host->show();
    btn->show();
    btn->resize(40, 40);
    auto* controller =
        btn->property("buttonController").value<buttons::ButtonController*>();
    if (controller != nullptr) {
      controller->setState(QStringLiteral("_main"),
                           buttons::ButtonState::Pressed, true);
      auto* ripple = controller->ripple(QStringLiteral("_main"));
      if (ripple != nullptr) {
        ripple->trigger(QPointF(20, 20));
      }
      out << (ripple != nullptr && ripple->isActive() ? "true" : "false");
    } else {
      out << "false";
    }
  } else {
    std::cerr << "parity_renderer: unknown query: " << query.toStdString()
              << '\n';
    std::exit(2);
  }
  out << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  // Offscreen platform is mandatory — the parity harness must not depend on
  // an X / Wayland session being available.
  qputenv("QT_QPA_PLATFORM", "offscreen");
  QApplication app(argc, argv);

  // Pin font + theme so the only variable across cases is the widget config.
  QFont f(QStringLiteral("Sans Serif"), 10);
  f.setStyleStrategy(static_cast<QFont::StyleStrategy>(
      QFont::NoSubpixelAntialias | QFont::PreferAntialias));
  app.setFont(f);
  Theme::apply(app, Theme::Mode::Light);

  QString mode, id, output;
  for (int i = 1; i < argc; ++i) {
    const QString a = QString::fromLocal8Bit(argv[i]);
    if (a == QStringLiteral("--mode") && i + 1 < argc) {
      mode = QString::fromLocal8Bit(argv[++i]);
    } else if (a == QStringLiteral("--case") && i + 1 < argc) {
      id = QString::fromLocal8Bit(argv[++i]);
    } else if (a == QStringLiteral("--output") && i + 1 < argc) {
      output = QString::fromLocal8Bit(argv[++i]);
    }
  }
  if (mode.isEmpty() || id.isEmpty()) {
    std::cerr
        << "usage: parity_renderer --mode render --case <id> --output <png>\n"
        << "       parity_renderer --mode query  --case <id>\n";
    return 2;
  }

  const QString casesPath =
      qEnvironmentVariable("IMGSLI_PARITY_CASES");
  if (casesPath.isEmpty()) {
    std::cerr << "parity_renderer: IMGSLI_PARITY_CASES env var must be set\n";
    return 2;
  }
  const QJsonObject corpus = loadCorpus(casesPath);

  if (mode == QStringLiteral("render")) {
    if (output.isEmpty()) {
      std::cerr << "parity_renderer: --output required in render mode\n";
      return 2;
    }
    renderCase(corpus, id, output);
  } else if (mode == QStringLiteral("query")) {
    runQuery(corpus, id);
  } else {
    std::cerr << "parity_renderer: unknown mode: " << mode.toStdString() << '\n';
    return 2;
  }
  return 0;
}

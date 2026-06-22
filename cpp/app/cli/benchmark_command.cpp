#include "benchmark_command.h"

#include <QApplication>
#include <QElapsedTimer>

#include <cstdio>
#include <memory>

#include "ui/canvas/canvas_widget.h"

namespace imgsli::app::cli {
namespace {

struct BenchmarkState {
  QElapsedTimer timer;
  int count = 0;
  bool finished = false;
};

}  // namespace

void installBenchmarkCommand(QApplication& app, CanvasWidget* canvas,
                             int frameCount) {
  if (frameCount <= 0) {
    return;
  }
  auto state = std::make_shared<BenchmarkState>();
  QObject::connect(
      canvas, &CanvasWidget::frameRecorded, canvas,
      [canvas, state, frameCount, &app]() {
        if (state->finished) {
          return;
        }
        if (!state->timer.isValid()) {
          state->timer.start();
        }
        ++state->count;
        if (state->count >= frameCount) {
          state->finished = true;
          const double seconds = state->timer.elapsed() / 1000.0;
          const double fps =
              seconds > 0.0 ? state->count / seconds : 0.0;
          std::fprintf(stdout, "IMGSLI_BENCHMARK_FPS=%.2f\n", fps);
          std::fflush(stdout);
          app.quit();
          return;
        }
        canvas->update();
      },
      Qt::QueuedConnection);
}

}  // namespace imgsli::app::cli

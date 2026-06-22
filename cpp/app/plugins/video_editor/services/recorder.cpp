#include "plugins/video_editor/services/recorder.h"

#include <QTimer>

#include <algorithm>

#include "plugins/comparison/controller.h"

namespace imgsli::app {

VideoRecorder::VideoRecorder(QObject* parent)
    : QObject(parent), sampleTimer_(new QTimer(this)) {
  sampleTimer_->setTimerType(Qt::PreciseTimer);
  connect(sampleTimer_, &QTimer::timeout, this, &VideoRecorder::onTick);
}

void VideoRecorder::bindCanvas(CanvasWidget* canvas) { canvas_ = canvas; }
void VideoRecorder::bindComparisonController(ComparisonController* c) {
  comparison_ = c;
}

void VideoRecorder::setFps(int fps) {
  fps_ = std::clamp(fps, 1, 144);
  if (state_ == State::Recording) {
    sampleTimer_->setInterval(1000 / fps_);
  }
}

qint64 VideoRecorder::durationMs() const {
  if (snapshots_.isEmpty()) {
    return 0;
  }
  const qint64 frameMs = 1000 / std::max(1, fps_);
  return snapshots_.last().timestampMs + frameMs;
}

qint64 VideoRecorder::lastTimestampMs() const {
  return snapshots_.isEmpty() ? 0 : snapshots_.last().timestampMs;
}

bool VideoRecorder::start() {
  if (canvas_ == nullptr || state_ == State::Recording) {
    return false;
  }
  snapshots_.clear();
  undoStack_.clear();
  redoStack_.clear();
  emit cleared();
  totalPausedMs_ = 0;
  wallClock_.start();
  sampleTimer_->setInterval(1000 / std::max(1, fps_));
  sampleTimer_->start();
  setState(State::Recording);
  // Capture the first frame immediately, mirroring the Python recorder
  // that calls QTimer::singleShot(0, capture_frame).
  QTimer::singleShot(0, this, [this]() { captureFrame(false); });
  return true;
}

void VideoRecorder::stop() {
  if (state_ == State::Idle) {
    return;
  }
  sampleTimer_->stop();
  // Flush a final frame so the trailing position is preserved.
  captureFrame(true);
  setState(State::Idle);
}

bool VideoRecorder::pause() {
  if (state_ != State::Recording) {
    return false;
  }
  sampleTimer_->stop();
  pauseStartedMs_ = wallClock_.elapsed();
  setState(State::Paused);
  return true;
}

bool VideoRecorder::resume() {
  if (state_ != State::Paused) {
    return false;
  }
  totalPausedMs_ += wallClock_.elapsed() - pauseStartedMs_;
  sampleTimer_->start();
  setState(State::Recording);
  return true;
}

void VideoRecorder::clear() {
  if (state_ != State::Idle) {
    return;
  }
  snapshots_.clear();
  undoStack_.clear();
  redoStack_.clear();
  emit cleared();
}

qint64 VideoRecorder::elapsedMs() const {
  if (!wallClock_.isValid()) {
    return 0;
  }
  const qint64 now = state_ == State::Paused ? pauseStartedMs_
                                              : wallClock_.elapsed();
  return std::max<qint64>(0, now - totalPausedMs_);
}

void VideoRecorder::captureFrame(bool forceAdvance) {
  if (canvas_ == nullptr || state_ == State::Paused) {
    return;
  }
  qint64 ts = elapsedMs();
  if (forceAdvance && !snapshots_.isEmpty()) {
    const qint64 frameMs = 1000 / std::max(1, fps_);
    ts = std::max(ts, snapshots_.last().timestampMs + frameMs);
  }

  VideoFrameSnapshot snap;
  snap.timestampMs = ts;
  snap.plan = canvas_->renderPlan();
  if (comparison_ != nullptr) {
    // ComparisonController stores the source paths internally; we expose
    // them via dedicated getters added for the recorder.
    snap.leftPath = comparison_->leftSourcePath();
    snap.rightPath = comparison_->rightSourcePath();
    snap.leftLabel = snap.plan.leftLabel;
    snap.rightLabel = snap.plan.rightLabel;
  }
  snapshots_.append(snap);
  emit snapshotCaptured(snapshots_.size());
}

void VideoRecorder::onTick() { captureFrame(false); }

void VideoRecorder::pushUndo() {
  if (undoStack_.size() >= kHistoryDepth) {
    undoStack_.removeFirst();
  }
  undoStack_.append(snapshots_);
  redoStack_.clear();
}

bool VideoRecorder::deleteAt(int index) {
  if (state_ != State::Idle || index < 0 || index >= snapshots_.size()) {
    return false;
  }
  pushUndo();
  snapshots_.removeAt(index);
  emit snapshotCaptured(snapshots_.size());
  return true;
}

bool VideoRecorder::deleteRange(int start, int end) {
  if (state_ != State::Idle || snapshots_.isEmpty()) {
    return false;
  }
  const int lo = std::max(0, std::min(start, end));
  const int hi = std::min(static_cast<int>(snapshots_.size()) - 1, std::max(start, end));
  if (lo > hi) {
    return false;
  }
  pushUndo();
  snapshots_.erase(snapshots_.begin() + lo, snapshots_.begin() + hi + 1);
  emit snapshotCaptured(snapshots_.size());
  return true;
}

bool VideoRecorder::trim(int start, int end) {
  if (state_ != State::Idle || snapshots_.isEmpty()) {
    return false;
  }
  const int lo = std::max(0, std::min(start, end));
  const int hi = std::min(static_cast<int>(snapshots_.size()) - 1, std::max(start, end));
  if (lo > hi) {
    return false;
  }
  pushUndo();
  const QVector<VideoFrameSnapshot> kept(snapshots_.begin() + lo,
                                          snapshots_.begin() + hi + 1);
  snapshots_ = kept;
  emit snapshotCaptured(snapshots_.size());
  return true;
}

bool VideoRecorder::undo() {
  if (state_ != State::Idle || undoStack_.isEmpty()) {
    return false;
  }
  if (redoStack_.size() >= kHistoryDepth) {
    redoStack_.removeFirst();
  }
  redoStack_.append(snapshots_);
  snapshots_ = undoStack_.takeLast();
  emit snapshotCaptured(snapshots_.size());
  return true;
}

VideoRecorder::TimeLookup VideoRecorder::lookupTimeMs(qint64 timeMs) const {
  TimeLookup r;
  if (snapshots_.isEmpty()) {
    return r;
  }
  if (timeMs <= snapshots_.first().timestampMs) {
    r.indexBefore = 0;
    r.indexAfter = 0;
    return r;
  }
  if (timeMs >= snapshots_.last().timestampMs) {
    const int last = static_cast<int>(snapshots_.size()) - 1;
    r.indexBefore = last;
    r.indexAfter = last;
    return r;
  }
  // Linear scan — recordings are short enough that std::lower_bound is
  // not worth the complexity for v1; switch later if profiling demands.
  for (int i = 1; i < snapshots_.size(); ++i) {
    if (snapshots_[i].timestampMs >= timeMs) {
      const qint64 a = snapshots_[i - 1].timestampMs;
      const qint64 b = snapshots_[i].timestampMs;
      r.indexBefore = i - 1;
      r.indexAfter = i;
      r.t = b > a ? static_cast<double>(timeMs - a) /
                        static_cast<double>(b - a)
                  : 0.0;
      return r;
    }
  }
  return r;
}

bool VideoRecorder::redo() {
  if (state_ != State::Idle || redoStack_.isEmpty()) {
    return false;
  }
  if (undoStack_.size() >= kHistoryDepth) {
    undoStack_.removeFirst();
  }
  undoStack_.append(snapshots_);
  snapshots_ = redoStack_.takeLast();
  emit snapshotCaptured(snapshots_.size());
  return true;
}

void VideoRecorder::setState(State next) {
  if (state_ == next) {
    return;
  }
  state_ = next;
  emit stateChanged(next);
}

}  // namespace imgsli::app

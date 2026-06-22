#pragma once

#include <QElapsedTimer>
#include <QObject>
#include <QString>
#include <QVector>

#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

class CanvasWidget;
class ComparisonController;

/// Holds a single captured frame from a recording session.
///
/// The full `CanvasRenderPlan` is the C++-side equivalent of the Python
/// `viewport_state` snapshot — it carries every visual attribute (split,
/// magnifier position/zoom, guides, divider) plus the texture ids needed
/// to recompose the frame later for preview or export.
struct VideoFrameSnapshot {
  qint64 timestampMs = 0;
  CanvasRenderPlan plan;
  QString leftPath;
  QString rightPath;
  QString leftLabel;
  QString rightLabel;
};

/// Records the live comparison canvas into a sequence of snapshots at a
/// fixed sample rate. Mirrors `src/plugins/video_editor/services/recorder.py`
/// without the keyframing engine — keyframes are derived from snapshots in a
/// later cutover step.
///
/// Lifecycle:
///   bindCanvas / bindComparisonController → start() → ticks capture frames
///   → pause()/resume() optional → stop() finalizes.
class VideoRecorder final : public QObject {
  Q_OBJECT

 public:
  enum class State { Idle, Recording, Paused };
  Q_ENUM(State)

  explicit VideoRecorder(QObject* parent = nullptr);

  void bindCanvas(CanvasWidget* canvas);
  void bindComparisonController(ComparisonController* controller);

  void setFps(int fps);  // clamped to [1, 144]
  int fps() const { return fps_; }

  State state() const { return state_; }
  int snapshotCount() const { return snapshots_.size(); }
  qint64 durationMs() const;
  qint64 lastTimestampMs() const;
  const QVector<VideoFrameSnapshot>& snapshots() const { return snapshots_; }

 public slots:
  bool start();
  void stop();
  bool pause();
  bool resume();
  void clear();
  /// Capture a single frame outside of the timer cadence (used at stop
  /// time to flush a final sample, matching Python's
  /// `capture_frame(force_advance_frame=True)`).
  void captureFrame(bool forceAdvance = false);

  // Snapshot editing. All ops are no-ops while recording is active.
  // Each mutation pushes the previous snapshot list onto an undo stack
  // (capped at kHistoryDepth) so the user can step back through edits.
  bool deleteAt(int index);
  bool deleteRange(int start, int end);  // inclusive on both ends
  bool trim(int start, int end);          // keep [start, end] only
  bool undo();
  bool redo();
  bool canUndo() const { return !undoStack_.isEmpty(); }
  bool canRedo() const { return !redoStack_.isEmpty(); }

 public:
  /// Result of locating a time within the recording.
  struct TimeLookup {
    int indexBefore = -1;
    int indexAfter = -1;
    double t = 0.0;  // [0,1] — fraction between the two snapshots
  };

  /// For a given timestamp, return the two snapshot indices that bracket
  /// it plus an interpolation fraction. Used by the preview/export
  /// pipeline to keyframe-style interpolate between recorded samples.
  ///   * empty recording → both indices -1.
  ///   * before first sample → both indices = 0, t = 0.
  ///   * after last sample → both indices = last, t = 0.
  TimeLookup lookupTimeMs(qint64 timeMs) const;

 signals:
  void stateChanged(State newState);
  void snapshotCaptured(int totalCount);
  void cleared();

 private slots:
  void onTick();

 private:
  void setState(State next);
  qint64 elapsedMs() const;

  static constexpr int kHistoryDepth = 50;
  void pushUndo();

  CanvasWidget* canvas_ = nullptr;
  ComparisonController* comparison_ = nullptr;
  int fps_ = 60;
  State state_ = State::Idle;
  QVector<VideoFrameSnapshot> snapshots_;
  QElapsedTimer wallClock_;
  qint64 totalPausedMs_ = 0;
  qint64 pauseStartedMs_ = 0;
  class QTimer* sampleTimer_ = nullptr;
  QVector<QVector<VideoFrameSnapshot>> undoStack_;
  QVector<QVector<VideoFrameSnapshot>> redoStack_;
};

}  // namespace imgsli::app

#pragma once

namespace imgsli::app::ui {

// Abstract sink fed by the rating gesture transaction. Implementations route
// the calls into whatever owns rating state (the comparison session in C++).
class RatingGestureHandler {
 public:
  virtual ~RatingGestureHandler() = default;
  virtual void incrementRating(int imageNumber, int itemIndex) = 0;
  virtual void decrementRating(int imageNumber, int itemIndex) = 0;
  virtual void setRating(int imageNumber, int itemIndex, int score) = 0;
};

// Mirror of Python `RatingGestureTransaction`. Accumulates per-step deltas and
// can roll the rating back to the captured starting score on cancel.
class RatingGestureTransaction {
 public:
  RatingGestureTransaction(RatingGestureHandler* handler, int imageNumber,
                           int itemIndex, int startingScore);

  void applyDelta(int delta);
  void rollback();
  void commit();
  bool hasChanges() const noexcept { return accumulatedDelta_ != 0; }

 private:
  RatingGestureHandler* handler_;
  int imageNumber_;
  int itemIndex_;
  int startingScore_;
  int accumulatedDelta_ = 0;
  bool finalized_ = false;
};

}  // namespace imgsli::app::ui

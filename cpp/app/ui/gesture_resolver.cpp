#include "ui/gesture_resolver.h"

namespace imgsli::app::ui {

RatingGestureTransaction::RatingGestureTransaction(RatingGestureHandler* handler,
                                                   int imageNumber, int itemIndex,
                                                   int startingScore)
    : handler_(handler),
      imageNumber_(imageNumber),
      itemIndex_(itemIndex),
      startingScore_(startingScore) {}

void RatingGestureTransaction::applyDelta(int delta) {
  if (finalized_ || delta == 0) {
    return;
  }
  accumulatedDelta_ += delta;
  if (!handler_) {
    return;
  }
  if (delta > 0) {
    for (int i = 0; i < delta; ++i) {
      handler_->incrementRating(imageNumber_, itemIndex_);
    }
  } else {
    for (int i = 0; i < -delta; ++i) {
      handler_->decrementRating(imageNumber_, itemIndex_);
    }
  }
}

void RatingGestureTransaction::rollback() {
  if (finalized_) {
    return;
  }
  if (accumulatedDelta_ != 0 && handler_) {
    handler_->setRating(imageNumber_, itemIndex_, startingScore_);
  }
  accumulatedDelta_ = 0;
  finalized_ = true;
}

void RatingGestureTransaction::commit() {
  if (finalized_) {
    return;
  }
  finalized_ = true;
}

}  // namespace imgsli::app::ui

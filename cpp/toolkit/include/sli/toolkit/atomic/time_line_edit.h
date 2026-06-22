#pragma once

#include <QColor>
#include <QFont>
#include <QSize>
#include <QString>
#include <QTimer>
#include <QTime>

#include <memory>

#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/layers/layer.h"
#include "sli/toolkit/helpers/wheel_scroll_policy.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

/// Toolkit-painted HH:mm input without native QTimeEdit chrome.
/// Mirrors Python `TimeLineEdit` from `time_line_edit.py`.
class TimeLineEdit final : public CustomLineEdit {
  Q_OBJECT

 public:
  static constexpr int STEP_BUTTON_WIDTH = 22;
  static constexpr int STEP_BUTTON_GAP = 0;
  static constexpr int STEP_BUTTON_OVERLAP = 1;
  static constexpr int STEP_ARROW_SIZE = 22;
  static constexpr int REPEAT_START_DELAY_MS = 350;
  static constexpr int REPEAT_INTERVAL_MS = 70;

  explicit TimeLineEdit(
      const QString& initialTime = QStringLiteral("00:05"),
      QWidget* parent = nullptr,
      Qt::Alignment alignment = Qt::AlignCenter,
      bool showStepButtons = true,
      bool wheelRequiresFocus = false,
      const QColor& underlineColor = QColor(),
      double underlineThickness = 1.0,
      const QColor& focusedUnderlineColor = QColor(),
      double focusedUnderlineThickness = 1.0);

  void setStepButtonsVisible(bool visible);
  bool stepButtonsVisible() const;
  void set_step_buttons_visible(bool visible);
  bool step_buttons_visible() const;

  QSize sizeHint() const override;
  QSize minimumSizeHint() const override;

  void setText(const QString& text);
  QTime time() const;
  void setTime(const QTime& timeObj);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;
  void resizeEvent(QResizeEvent* event) override;
  bool eventFilter(QObject* obj, QEvent* event) override;
  void wheelEvent(QWheelEvent* event) override;
  void focusOutEvent(QFocusEvent* event) override;
  void setEnabled(bool enabled);

 private:
  // ---- Nested types (implementation details) ----

  /// Overlay layer drawn on step buttons when hovered / pressed.
  /// Mirrors Python `_StepButtonOverlayLayer`.
  class StepButtonOverlayLayer : public buttons::Layer {
   public:
    buttons::LayerScope scope() const override {
      return buttons::LayerScope::Widget;
    }
    bool applies(const buttons::DrawContext& ctx) const override;
    void draw(const buttons::DrawContext& ctx,
              const Theme& theme) const override;
  };

  /// Step-button subclass that accepts mouse events to prevent propagation.
  /// Mirrors Python `_TimeLineStepButton`.
  class TimeLineStepButton : public Button {
   public:
    using Button::Button;
    static std::unique_ptr<TimeLineStepButton> create(
        const QString& text, QWidget* parent);

   protected:
    void mousePressEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void mouseDoubleClickEvent(QMouseEvent* event) override;
    void paintEvent(QPaintEvent* event) override;

   private:
    StepButtonOverlayLayer overlayLayer_;
  };

  // ---- helper methods ----

  TimeLineStepButton* _create_step_button(const QString& text, int delta);
  void _insert_digit(const QString& digit);
  void _insert_colon();
  void _apply_edit_candidate(const QString& proposed, int cursor);
  void _normalize_or_restore();
  void _step_minutes(int delta);
  void _start_step_hold(int delta);
  void _start_repeat_timer();
  void _repeat_step();
  void _stop_repeat();
  void _sync_text_margins();
  int _content_width() const;
  QRect _up_button_rect() const;
  QRect _down_button_rect() const;
  QRect _button_area_rect() const;
  void _sync_step_buttons();
  QString _normalize_text(const QString& text) const;
  bool _is_intermediate(const QString& text) const;

  // ---- data members ----

  bool showStepButtons_ = true;
  QString lastValidText_ = QStringLiteral("00:05");
  int activeStepDelta_ = 0;
  QTimer* repeatStartTimer_ = nullptr;
  QTimer* repeatTimer_ = nullptr;
  TimeLineStepButton* upButton_ = nullptr;
  TimeLineStepButton* downButton_ = nullptr;
  WheelScrollPolicy wheelScrollPolicy_;
};

}  // namespace sli::toolkit
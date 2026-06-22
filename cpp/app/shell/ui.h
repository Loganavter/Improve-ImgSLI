#pragma once

// Mirror of `src/ui/main_window/ui.py` (`Ui_ImageComparisonApp`).
// Owns widget construction only; layout assembly lives in
// `cpp/app/shell/layouts.{h,cpp}` and presenter / controller wiring lives
// in `cpp/app/shell/bootstrap.cpp`. Keep this file purely declarative —
// no QObject::connect, no addWidget — to match Python's separation.

#include <QColor>
#include <QSize>
#include <QSizePolicy>
#include <QString>

#include "sli/toolkit/atomic/instances_counter_button.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/composite/adaptive_tab_strip.h"

class QPushButton;
class QStackedWidget;
class QWidget;

namespace imgsli::app {
class CanvasWidget;
}

namespace imgsli::app::ui::widgets {
class ZoomIndicator;
}

namespace sli::toolkit {
class DragDropOverlay;
}

namespace sli::toolkit {
class CustomLineEdit;
class Label;
class Slider;
namespace comboboxes {
class ScrollableComboBox;
}
}  // namespace sli::toolkit

namespace imgsli::app::shell {

// Names + grouping mirror Python `_create_static_widgets`,
// `_create_selection_controls`, `_create_view_controls`,
// `_create_video_controls`, `_create_slider_controls`,
// `_create_text_and_status_widgets`. Member naming follows the Python
// attribute names so a cross-reference grep stays trivial.
struct MainWindowUi {
  // --- static widgets -------------------------------------------------------
  // Python: self.image_label = GLCanvas(main_window)
  imgsli::app::CanvasWidget* imageLabel = nullptr;
  // Python: self.length_warning_label = Label(parent=main_window)
  sli::toolkit::Label* lengthWarningLabel = nullptr;
  // Python: self.workspace_tabs = AdaptiveTabStrip(...)
  sli::toolkit::AdaptiveTabStrip* workspaceTabs = nullptr;
  // Python: self.btn_new_session = self.workspace_tabs.add_button
  sli::toolkit::Button* btnNewSession = nullptr;
  // Python: self.workspace_stack = QStackedWidget(main_window)
  QStackedWidget* workspaceStack = nullptr;
  QWidget* imageSessionPage = nullptr;
  QWidget* videoSessionPage = nullptr;
  // Python: self.video_session_widget = VideoSessionWidget(main_window)
  // Not yet ported — placeholder QWidget so layout slot stays valid.
  QWidget* videoSessionWidget = nullptr;
  QWidget* magnifierSettingsPanel = nullptr;
  // Python: self.resolution_label1/2 = Label("--x--", variant="group-title")
  // Constructed in createStaticWidgets to mirror Python's _create_static_widgets.
  sli::toolkit::Label* resolutionLabel1 = nullptr;
  sli::toolkit::Label* resolutionLabel2 = nullptr;

  // --- selection controls ---------------------------------------------------
  sli::toolkit::Button* btnImage1 = nullptr;
  sli::toolkit::Button* btnImage2 = nullptr;
  sli::toolkit::Button* btnSwap = nullptr;
  sli::toolkit::Button* btnClearList1 = nullptr;
  sli::toolkit::Button* btnClearList2 = nullptr;
  sli::toolkit::Button* helpButton = nullptr;
  sli::toolkit::Button* btnSettings = nullptr;
  sli::toolkit::Button* btnTextSettings = nullptr;
  sli::toolkit::Button* btnQuickSave = nullptr;
  sli::toolkit::Button* btnMagnifierOrientation = nullptr;
  sli::toolkit::Button* btnSave = nullptr;

  // Per-image rating labels (Python: label_rating1/2, variant="group-title")
  sli::toolkit::Label* labelRating1 = nullptr;
  sli::toolkit::Label* labelRating2 = nullptr;
  // ScrollableComboBox row
  sli::toolkit::comboboxes::ScrollableComboBox* comboImage1 = nullptr;
  sli::toolkit::comboboxes::ScrollableComboBox* comboImage2 = nullptr;
  // Python: self.combo_interpolation = ScrollableComboBox(parent)
  sli::toolkit::comboboxes::ScrollableComboBox* comboInterpolation = nullptr;

  // --- view controls (toolbar) ----------------------------------------------
  // Python: btn_orientation — scrollable (0,20), show_underline, toggle
  sli::toolkit::Button* btnOrientation = nullptr;
  sli::toolkit::Button* btnMagnifier = nullptr;
  // Python: btn_magnifier_instances = InstancesCounterButton(parent=parent)
  sli::toolkit::InstancesCounterButton* btnMagnifierInstances = nullptr;
  sli::toolkit::Button* btnFreeze = nullptr;
  sli::toolkit::Button* btnFileNames = nullptr;
  // Python: btn_diff_mode = Button(AppIcon.HIGHLIGHT_DIFFERENCES, menu=[], ...)
  sli::toolkit::Button* btnDiffMode = nullptr;
  // Python: btn_channel_mode = Button(AppIcon.PHOTO, menu=[], ...)
  sli::toolkit::Button* btnChannelMode = nullptr;
  // Python: btn_magnifier_color_settings = ColorSettingsButton(...)
  // ColorSettingsButton not yet ported — regular Button as placeholder.
  sli::toolkit::Button* btnMagnifierColorSettings = nullptr;
  // Python: btn_magnifier_guides — scrollable (0,10), show_underline, toggle
  sli::toolkit::Button* btnMagnifierGuides = nullptr;

  // Python: btn_orientation_simple — toggle, no scrollable
  sli::toolkit::Button* btnOrientationSimple = nullptr;
  // Python: btn_divider_visible — toggle, icon pair DividerVisible/DividerHidden
  sli::toolkit::Button* btnDividerVisible = nullptr;
  // Python: btn_divider_color — show_underline
  sli::toolkit::Button* btnDividerColor = nullptr;
  // Python: btn_divider_width — scrollable (1,20), show_underline
  sli::toolkit::Button* btnDividerWidth = nullptr;
  // Python: btn_magnifier_orientation_simple — toggle, no scrollable
  sli::toolkit::Button* btnMagnifierOrientationSimple = nullptr;
  // Python: btn_magnifier_divider_visible — toggle, icon pair
  sli::toolkit::Button* btnMagnifierDividerVisible = nullptr;
  // Python: btn_magnifier_color_settings_beginner = ColorSettingsButton(...)
  // Placeholder until ColorSettingsButton is ported.
  sli::toolkit::Button* btnMagnifierColorSettingsBeginner = nullptr;
  // Python: btn_magnifier_divider_width — scrollable (1,10), show_underline
  sli::toolkit::Button* btnMagnifierDividerWidth = nullptr;
  // Python: btn_magnifier_guides_simple — toggle only
  sli::toolkit::Button* btnMagnifierGuidesSimple = nullptr;
  // Python: btn_magnifier_guides_width — scrollable (1,10), show_underline
  sli::toolkit::Button* btnMagnifierGuidesWidth = nullptr;

  // --- video controls -------------------------------------------------------
  sli::toolkit::Button* btnRecord = nullptr;
  sli::toolkit::Button* btnPause = nullptr;
  // Python: btn_video_editor = Button(AppIcon.EXPORT_VIDEO, ...)
  sli::toolkit::Button* btnVideoEditor = nullptr;

  // --- slider controls ------------------------------------------------------
  // Python: slider_size   (magnifier size)
  sli::toolkit::Slider* sliderSize = nullptr;
  // Python: slider_capture
  sli::toolkit::Slider* sliderCapture = nullptr;
  // Python: slider_speed  (movement speed)
  sli::toolkit::Slider* sliderSpeed = nullptr;

  // --- text + status widgets ------------------------------------------------
  sli::toolkit::CustomLineEdit* editName1 = nullptr;
  sli::toolkit::CustomLineEdit* editName2 = nullptr;
  // Python: label_magnifier_size/capture_size/movement_speed/interpolation
  //         variant="group-title"
  sli::toolkit::Label* labelMagnifierSize = nullptr;
  sli::toolkit::Label* labelCaptureSize = nullptr;
  sli::toolkit::Label* labelMovementSpeed = nullptr;
  sli::toolkit::Label* labelInterpolation = nullptr;
  // Python: file_name_label1/2 variant="group-title"
  sli::toolkit::Label* fileNameLabel1 = nullptr;
  sli::toolkit::Label* fileNameLabel2 = nullptr;
  // Python: label_edit_name1/2 variant="group-title"
  sli::toolkit::Label* labelEditName1 = nullptr;
  sli::toolkit::Label* labelEditName2 = nullptr;

  // --- overlays (created by LayoutComposer) ---------------------------------
  // Mirror of Python ui.zoom_indicator (ZoomIndicator) and ui.drag_overlay
  // (DragDropOverlay). Both are created by LayoutComposer._create_zoom_indicator
  // and build() respectively; they are null until LayoutComposer::build runs.
  imgsli::app::ui::widgets::ZoomIndicator* zoomIndicator = nullptr;
  sli::toolkit::DragDropOverlay* dragOverlay = nullptr;
  // Python's ui.btn_zoom_reset is the reset button inside the ZoomIndicator.
  // Stored separately so bootstrap can wire it without coupling to the
  // ZoomIndicator subwidget API.
  QPushButton* btnZoomReset = nullptr;

  // --- entry point ----------------------------------------------------------
  // Constructs every widget above (parent = `mainWindow`) without touching
  // layout. Call once during composition; layout is the next stage.
  void setupUi(QWidget* mainWindow);

 private:
  void createStaticWidgets(QWidget* mainWindow);
  void createSelectionControls(QWidget* mainWindow);
  void createViewControls(QWidget* mainWindow);
  void createVideoControls(QWidget* mainWindow);
  void createSliderControls(QWidget* mainWindow);
  void createTextAndStatusWidgets(QWidget* mainWindow);
  void configureImageLabel();
  void initWarningLabel();
  void initDragOverlays();
};

}  // namespace imgsli::app::shell

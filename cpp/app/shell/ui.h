#pragma once

// Mirror of `src/ui/main_window/ui.py` (`Ui_ImageComparisonApp`).
// Owns widget construction only; layout assembly lives in
// `cpp/app/shell/layouts.{h,cpp}` and presenter / controller wiring lives
// in `cpp/app/shell/bootstrap.cpp`. Keep this file purely declarative —
// no QObject::connect, no addWidget — to match Python's separation.

#include <QColor>
#include <QString>

#include "sli/toolkit/buttons/button.h"

class QSlider;
class QTabBar;
class QLabel;
class QWidget;

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
  // --- static widgets ------------------------------------------------------
  QWidget* workspaceTabsBar = nullptr;
  QTabBar* workspaceTabs = nullptr;
  sli::toolkit::Button* btnNewSession = nullptr;
  QWidget* imageSessionPage = nullptr;
  QWidget* videoSessionPage = nullptr;
  QWidget* magnifierSettingsPanel = nullptr;

  // --- selection controls --------------------------------------------------
  sli::toolkit::Button* btnImage1 = nullptr;
  sli::toolkit::Button* btnImage2 = nullptr;
  sli::toolkit::Button* btnSwap = nullptr;
  sli::toolkit::Button* btnClearList1 = nullptr;
  sli::toolkit::Button* btnClearList2 = nullptr;
  sli::toolkit::Button* helpButton = nullptr;
  sli::toolkit::Button* btnSettings = nullptr;
  sli::toolkit::Button* btnTextSettings = nullptr;
  sli::toolkit::Button* btnQuickSave = nullptr;
  sli::toolkit::Button* btnSave = nullptr;

  // Per-image rating labels + ScrollableComboBox row (Python
  // `_combobox_row`). Sits between selection_widget's button row and the
  // toolbar.
  sli::toolkit::Label* labelRating1 = nullptr;
  sli::toolkit::Label* labelRating2 = nullptr;
  sli::toolkit::comboboxes::ScrollableComboBox* comboImage1 = nullptr;
  sli::toolkit::comboboxes::ScrollableComboBox* comboImage2 = nullptr;

  // --- view controls (toolbar) --------------------------------------------
  sli::toolkit::Button* btnOrientation = nullptr;
  sli::toolkit::Button* btnMagnifier = nullptr;
  sli::toolkit::Button* btnFreeze = nullptr;
  sli::toolkit::Button* btnFileNames = nullptr;
  sli::toolkit::Button* btnDiffMode = nullptr;
  sli::toolkit::Button* btnChannelMode = nullptr;
  sli::toolkit::Button* btnMagnifierGuides = nullptr;
  sli::toolkit::Button* btnMagnifierOrientation = nullptr;
  sli::toolkit::Button* btnMagnifierColor = nullptr;
  sli::toolkit::Button* btnMagnifierInstances = nullptr;

  // --- video controls -----------------------------------------------------
  sli::toolkit::Button* btnRecord = nullptr;
  sli::toolkit::Button* btnPause = nullptr;
  sli::toolkit::Button* btnVideoEditor = nullptr;

  // --- slider controls ----------------------------------------------------
  sli::toolkit::Slider* sliderSplit = nullptr;          // Python slider_size
  sli::toolkit::Slider* sliderMagnifierSize = nullptr;
  sli::toolkit::Slider* sliderCaptureSize = nullptr;
  sli::toolkit::Slider* sliderMovementSpeed = nullptr;

  // --- text + status widgets ----------------------------------------------
  sli::toolkit::CustomLineEdit* editName1 = nullptr;
  sli::toolkit::CustomLineEdit* editName2 = nullptr;
  sli::toolkit::Label* resolutionLabel1 = nullptr;
  sli::toolkit::Label* resolutionLabel2 = nullptr;
  sli::toolkit::Label* psnrLabel = nullptr;
  sli::toolkit::Label* ssimLabel = nullptr;
  sli::toolkit::Label* fileNameLabel1 = nullptr;
  sli::toolkit::Label* fileNameLabel2 = nullptr;

  // --- entry point ---------------------------------------------------------
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
};

}  // namespace imgsli::app::shell

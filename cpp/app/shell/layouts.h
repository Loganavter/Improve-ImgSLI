#pragma once

// Mirror of `src/ui/main_window/layouts.py` (`LayoutComposer`). Pulls the
// already-constructed widgets off MainWindowUi and arranges them inside
// the main window. No widget construction here, no controller wiring.

class QWidget;
class QVBoxLayout;

namespace imgsli::app {
class CanvasWidget;
}

namespace imgsli::app::shell {

struct MainWindowUi;

class LayoutComposer {
 public:
  // `ui` holds every widget the composer will lay out — same contract as
  // Python (`__init__(self, ui)` then `build(main_window)`).
  LayoutComposer(MainWindowUi& ui, CanvasWidget* canvas);

  // Top-level layout: workspace bar, session pages, footer. Mirrors
  // Python `LayoutComposer.build(main_window)`.
  void build(QWidget* mainWindow, QVBoxLayout* rootLayout);

 private:
  MainWindowUi& ui_;
  CanvasWidget* canvas_;

  // Section builders — one-to-one with Python methods of the same name.
  QWidget* buildWorkspaceTabsBar(QWidget* mainWindow);
  QWidget* buildSelectionWidget(QWidget* parent);
  QWidget* buildSelectionRow(QWidget* parent);
  QWidget* buildComboboxRow(QWidget* parent);
  QWidget* buildComparisonToolbar(QWidget* parent);
  QWidget* buildMagnifierSettingsPanel(QWidget* parent);
  QWidget* buildFilenameEditPanel(QWidget* parent);
  QWidget* buildFooterInfo(QWidget* parent);
  QWidget* buildSaveBar(QWidget* parent);

  // Finalization helpers — mirror Python LayoutComposer._finalize().
  void createZoomIndicator(QWidget* imageContainer);
  void createDragOverlay(QWidget* imageContainer);
  void applyIconSizes();
  void applyWorkspaceTabsVisibility();
};

}  // namespace imgsli::app::shell

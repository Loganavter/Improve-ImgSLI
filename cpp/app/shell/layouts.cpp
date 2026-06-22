// Mirror of `src/ui/main_window/layouts.py`. Pure layout assembly — no
// QObject::connect, no controller wiring (that's bootstrap.cpp).

#include "shell/layouts.h"

#include <QHBoxLayout>
#include <QTabBar>
#include <QVBoxLayout>
#include <QWidget>

#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/atomic/slider.h"
#include "sli/toolkit/atomic/text_labels.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/button_group.h"
#include "sli/toolkit/comboboxes/scrollable_combo_box.h"
#include "sli/toolkit/overlays/drag_drop_overlay.h"
#include "shell/ui.h"
#include "ui/canvas/canvas_widget.h"
#include "ui/widgets/zoom_indicator.h"

namespace imgsli::app::shell {

LayoutComposer::LayoutComposer(MainWindowUi& ui, CanvasWidget* canvas)
    : ui_(ui), canvas_(canvas) {}

void LayoutComposer::build(QWidget* mainWindow, QVBoxLayout* rootLayout) {
  rootLayout->setContentsMargins(0, 0, 0, 0);
  rootLayout->setSpacing(0);

  rootLayout->addWidget(buildWorkspaceTabsBar(mainWindow));
  rootLayout->addWidget(buildSelectionWidget(mainWindow));
  rootLayout->addWidget(buildComparisonToolbar(mainWindow));
  rootLayout->addWidget(buildSplitRow(mainWindow));
  rootLayout->addWidget(buildMagnifierSettingsPanel(mainWindow));

  // Wrap the canvas in a container so the ZoomIndicator and DragDropOverlay
  // can be positioned as overlays over it — matching Python's
  // `image_container_widget` which holds the canvas + zoom indicator +
  // drag-drop overlay.
  auto* canvasContainer = new QWidget(mainWindow);
  canvasContainer->setObjectName(QStringLiteral("imageContainerWidget"));
  canvasContainer->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
  auto* containerLayout = new QVBoxLayout(canvasContainer);
  containerLayout->setContentsMargins(0, 0, 0, 0);
  containerLayout->setSpacing(0);
  containerLayout->addWidget(canvas_);
  createZoomIndicator(canvasContainer);
  createDragOverlay(canvasContainer);
  rootLayout->addWidget(canvasContainer, 1);

  rootLayout->addWidget(buildFooterInfo(mainWindow));
  rootLayout->addWidget(buildFilenameEditPanel(mainWindow));
  rootLayout->addWidget(buildSaveBar(mainWindow));

  // Python defaults: split slider hidden until magnifier-edit mode;
  // magnifier panel + filename edit panel hidden until their toggles fire.
  ui_.sliderSplit->parentWidget()->setVisible(false);
  ui_.magnifierSettingsPanel->setVisible(false);

  // Mirror Python LayoutComposer._finalize().
  applyIconSizes();
  applyWorkspaceTabsVisibility();
}

QWidget* LayoutComposer::buildWorkspaceTabsBar(QWidget* /*mainWindow*/) {
  auto* layout = new QHBoxLayout(ui_.workspaceTabsBar);
  layout->setContentsMargins(8, 4, 8, 0);
  layout->setSpacing(4);
  layout->addWidget(ui_.workspaceTabs);
  layout->addWidget(ui_.btnNewSession);
  layout->addStretch();
  return ui_.workspaceTabsBar;
}

QWidget* LayoutComposer::buildSelectionWidget(QWidget* parent) {
  // Python `_selection_widget`: vertical pair of (button-row, combobox-row)
  // sharing tight inter-row spacing.
  auto* widget = new QWidget(parent);
  auto* layout = new QVBoxLayout(widget);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(3);
  layout->addWidget(buildSelectionRow(widget));
  layout->addWidget(buildComboboxRow(widget));
  return widget;
}

QWidget* LayoutComposer::buildSelectionRow(QWidget* parent) {
  auto* row = new QWidget(parent);
  auto* layout = new QHBoxLayout(row);
  // Python `_button_row` does NOT set contentsMargins — relies on Qt's
  // default 9-px gutter. Forcing a custom margin made the row sit tighter
  // than Python's.
  layout->setSpacing(8);
  ui_.btnImage1->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  ui_.btnImage2->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  layout->addWidget(ui_.btnImage1, 1);
  layout->addWidget(ui_.btnClearList1);
  layout->addWidget(ui_.btnSwap);
  layout->addWidget(ui_.btnImage2, 1);
  layout->addWidget(ui_.btnClearList2);
  return row;
}

QWidget* LayoutComposer::buildComboboxRow(QWidget* parent) {
  // Python `_combobox_row`: two rating-label + ScrollableComboBox pairs
  // side-by-side. Rating labels are fixed-width 30px, comboboxes expand.
  // No custom contentsMargins — Qt default 9px matches Python.
  auto* row = new QWidget(parent);
  auto* outer = new QHBoxLayout(row);
  outer->setSpacing(8);
  auto pair = [&](sli::toolkit::Label* rating,
                  sli::toolkit::comboboxes::ScrollableComboBox* combo) {
    auto* sub = new QHBoxLayout();
    sub->setSpacing(4);
    rating->setFixedWidth(30);
    rating->setAlignment(Qt::AlignCenter);
    combo->setMinimumHeight(28);
    combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    sub->addWidget(rating);
    sub->addWidget(combo, 1);
    return sub;
  };
  outer->addLayout(pair(ui_.labelRating1, ui_.comboImage1), 1);
  outer->addLayout(pair(ui_.labelRating2, ui_.comboImage2), 1);
  return row;
}

QWidget* LayoutComposer::buildComparisonToolbar(QWidget* parent) {
  auto* row = new QWidget(parent);
  auto* layout = new QHBoxLayout(row);
  layout->setContentsMargins(8, 4, 8, 4);
  layout->setSpacing(16);

  using sli::toolkit::ButtonGroup;
  auto* lineGroup = new ButtonGroup(
      std::vector<QWidget*>{ui_.btnOrientation}, QStringLiteral("Line"), row);
  auto* viewGroup = new ButtonGroup(
      std::vector<QWidget*>{ui_.btnDiffMode, ui_.btnChannelMode,
                            ui_.btnFileNames},
      QStringLiteral("View"), row);
  auto* magnifierGroup = new ButtonGroup(
      std::vector<QWidget*>{ui_.btnMagnifier, ui_.btnMagnifierInstances,
                            ui_.btnFreeze, ui_.btnMagnifierOrientation,
                            ui_.btnMagnifierColor, ui_.btnMagnifierGuides},
      QStringLiteral("Magnifier"), row);
  auto* recordGroup = new ButtonGroup(
      std::vector<QWidget*>{ui_.btnRecord, ui_.btnPause, ui_.btnVideoEditor},
      QStringLiteral("Record"), row);

  layout->addWidget(lineGroup);
  layout->addWidget(viewGroup);
  layout->addWidget(magnifierGroup);
  layout->addWidget(recordGroup);
  layout->addStretch(1);
  // Python's right-side toolbar trio: quick_save, settings, help. The
  // text-settings (Aa) button lives inside the filename edit panel, not
  // here — putting it in the toolbar is a port divergence.
  layout->addWidget(ui_.btnQuickSave);
  layout->addWidget(ui_.btnSettings);
  layout->addWidget(ui_.helpButton);
  return row;
}

QWidget* LayoutComposer::buildSplitRow(QWidget* parent) {
  auto* row = new QWidget(parent);
  auto* layout = new QHBoxLayout(row);
  layout->setContentsMargins(8, 0, 8, 4);
  layout->setSpacing(8);
  auto* label = new sli::toolkit::Label(QStringLiteral("Split position"));
  layout->addWidget(label);
  layout->addWidget(ui_.sliderSplit, 1);
  return row;
}

QWidget* LayoutComposer::buildMagnifierSettingsPanel(QWidget* parent) {
  // Reuse the QWidget MainWindowUi already allocated; just populate the
  // layout. Python `magnifier_settings_panel` carries the three sliders.
  auto* layout = new QVBoxLayout(ui_.magnifierSettingsPanel);
  layout->setContentsMargins(8, 4, 8, 4);
  layout->setSpacing(4);
  auto addRow = [&](const QString& title, sli::toolkit::Slider* slider) {
    auto* roww = new QWidget(ui_.magnifierSettingsPanel);
    auto* h = new QHBoxLayout(roww);
    h->setContentsMargins(0, 0, 0, 0);
    auto* l = new sli::toolkit::Label(title);
    h->addWidget(l);
    h->addWidget(slider, 1);
    layout->addWidget(roww);
  };
  addRow(QStringLiteral("Magnifier size"), ui_.sliderMagnifierSize);
  addRow(QStringLiteral("Capture size"), ui_.sliderCaptureSize);
  addRow(QStringLiteral("Movement speed"), ui_.sliderMovementSpeed);
  (void)parent;
  return ui_.magnifierSettingsPanel;
}

QWidget* LayoutComposer::buildFilenameEditPanel(QWidget* parent) {
  auto* row = new QWidget(parent);
  auto* layout = new QHBoxLayout(row);
  layout->setContentsMargins(8, 4, 8, 4);
  layout->setSpacing(8);
  auto* lbl1 = new sli::toolkit::Label(QStringLiteral("Name 1:"));
  auto* lbl2 = new sli::toolkit::Label(QStringLiteral("Name 2:"));
  layout->addWidget(lbl1);
  layout->addWidget(ui_.editName1, 1);
  layout->addWidget(lbl2);
  layout->addWidget(ui_.editName2, 1);
  // btn_text_settings rides inside this panel (Python places it as a side
  // toggle next to the edit fields, not in the main toolbar).
  layout->addWidget(ui_.btnTextSettings);
  row->setVisible(false);
  // Stash the row pointer on the filename toggle button so bootstrap can
  // wire its visibility without re-querying the layout tree.
  ui_.btnFileNames->setProperty("__filenameEditRow",
                                 QVariant::fromValue<QWidget*>(row));
  return row;
}

QWidget* LayoutComposer::buildFooterInfo(QWidget* parent) {
  auto* widget = new QWidget(parent);
  auto* layout = new QVBoxLayout(widget);
  layout->setContentsMargins(8, 4, 8, 4);
  layout->setSpacing(0);

  auto* resRow = new QHBoxLayout();
  resRow->addWidget(ui_.resolutionLabel1, 0, Qt::AlignLeft);
  resRow->addStretch();
  resRow->addWidget(ui_.psnrLabel);
  resRow->addSpacing(15);
  resRow->addWidget(ui_.ssimLabel);
  resRow->addStretch();
  resRow->addWidget(ui_.resolutionLabel2, 0, Qt::AlignRight);
  layout->addLayout(resRow);

  auto* fileRow = new QHBoxLayout();
  fileRow->setContentsMargins(0, 2, 0, 2);
  ui_.fileNameLabel1->setMinimumHeight(22);
  ui_.fileNameLabel2->setMinimumHeight(22);
  fileRow->addWidget(ui_.fileNameLabel1, 0, Qt::AlignLeft);
  fileRow->addStretch();
  fileRow->addWidget(ui_.fileNameLabel2, 0, Qt::AlignRight);
  layout->addLayout(fileRow);
  return widget;
}

QWidget* LayoutComposer::buildSaveBar(QWidget* parent) {
  auto* widget = new QWidget(parent);
  auto* layout = new QHBoxLayout(widget);
  layout->setContentsMargins(8, 4, 8, 8);
  layout->setSpacing(8);
  ui_.btnSave->setMinimumHeight(36);
  layout->addWidget(ui_.btnSave, 1);
  return widget;
}

// --- finalization helpers ---------------------------------------------------

void LayoutComposer::createZoomIndicator(QWidget* imageContainer) {
  // Mirror Python LayoutComposer._create_zoom_indicator().
  // ZoomIndicator is a floating overlay positioned at the top-right of its
  // parent. It shows current zoom level and a reset button.
  auto* indicator = new imgsli::app::ui::widgets::ZoomIndicator(
      imageContainer,
      // lang_provider: for the C++ port we emit a static "Zoom" prefix;
      // a proper i18n hook can be wired later via Bootstrap.
      []() { return QStringLiteral("Zoom"); },
      /* target= */ nullptr  // will be wired to canvas widget by Bootstrap
  );
  ui_.zoomIndicator = indicator;
  ui_.btnZoomReset = indicator->resetButton();
  // Python: zoom_indicator is hidden at startup (only shows when zoom ≠ 1).
  indicator->hide();
}

void LayoutComposer::createDragOverlay(QWidget* imageContainer) {
  // Mirror Python `ui.drag_overlay = DragDropOverlay(ui.image_container_widget)`.
  auto* overlay = new sli::toolkit::DragDropOverlay(imageContainer);
  ui_.dragOverlay = overlay;
  // Python _init_drag_overlays: starts hidden / no active state.
  overlay->setOverlayState(false, std::nullopt);
}

void LayoutComposer::applyIconSizes() {
  // Mirror Python LayoutComposer.apply_icon_sizes(). Only buttons that exist
  // in the C++ port are listed; Python-only buttons (btn_divider_color etc.)
  // are omitted until they are ported.
  ui_.btnQuickSave->setIconSizePx(24);
  ui_.helpButton->setIconSizePx(24);
  ui_.btnClearList1->setIconSizePx(22);
  ui_.btnClearList2->setIconSizePx(22);
}

void LayoutComposer::applyWorkspaceTabsVisibility() {
  // Mirror Python `apply_workspace_tabs_visibility(ui)`.
  // Python constant SHOW_WORKSPACE_TABS = False — the workspace tab bar is
  // hidden by default; it becomes visible only when the settings flag
  // `show_workspace_tabs` is True. In C++ we default to hidden here and
  // Bootstrap can re-show it if the QSettings flag is set.
  constexpr bool kDefaultShowWorkspaceTabs = false;
  ui_.workspaceTabsBar->setVisible(kDefaultShowWorkspaceTabs);
}

}  // namespace imgsli::app::shell

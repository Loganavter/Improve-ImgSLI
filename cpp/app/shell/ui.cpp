// Mirror of `src/ui/main_window/ui.py`. Each section corresponds 1:1 to
// the Python `_create_*_controls` method — same widget kind, same args,
// same accent-paint where Python passes `background_color=...`.

#include "shell/ui.h"

#include <QCursor>
#include <QSizePolicy>
#include <QStackedWidget>
#include <QWidget>

#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/atomic/instances_counter_button.h"
#include "sli/toolkit/atomic/slider.h"
#include "sli/toolkit/atomic/text_labels.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/scrollable_combo_box.h"
#include "sli/toolkit/composite/adaptive_tab_strip.h"
#include "sli/toolkit/theme.h"
#include "ui/canvas/canvas_widget.h"
#include "ui/icon_manager.h"

namespace imgsli::app::shell {

namespace {

using sli::toolkit::Button;

constexpr int kIconButtonSize = 28;
constexpr int kToggleIconSize = 32;

// Theme accent → Python `resolve_theme_color(tm, "accent")`. The destructive
// red is the same `#D93025` Python hard-codes for clear buttons.
QColor themeAccent() {
  return sli::toolkit::Theme::getColor(QStringLiteral("accent"));
}
QColor destructiveRed() { return QColor(QStringLiteral("#D93025")); }

Button* makeIconButton(QWidget* parent, ui::AppIcon icon, const QString& tooltip,
                      std::optional<QColor> bg = std::nullopt,
                      std::optional<int> longPressMs = std::nullopt) {
  Button::Config cfg;
  cfg.icon = ui::getAppIcon(icon);
  cfg.variant = Button::Variant::Surface;
  cfg.size = QSize(kIconButtonSize, kIconButtonSize);
  cfg.iconSize = 20;
  if (bg.has_value()) {
    cfg.backgroundColor = bg;
  }
  if (longPressMs.has_value()) {
    cfg.longPressMs = longPressMs;
  }
  auto* btn = new Button(cfg, parent);
  if (!tooltip.isEmpty()) {
    btn->setToolTip(tooltip);
  }
  return btn;
}

Button* makeIconTextButton(QWidget* parent, ui::AppIcon icon,
                           const QString& text, const QString& tooltip = {},
                           std::optional<QColor> bg = std::nullopt) {
  Button::Config cfg;
  cfg.text = text;
  cfg.icon = ui::getAppIcon(icon);
  cfg.variant = Button::Variant::Surface;
  cfg.iconSize = 20;
  if (bg.has_value()) {
    cfg.backgroundColor = bg;
  }
  auto* btn = new Button(cfg, parent);
  if (!tooltip.isEmpty()) {
    btn->setToolTip(tooltip);
  }
  return btn;
}

// Python's toolbar buttons (orientation / magnifier / diff_mode / ...) take
// variant="default" + no explicit size — they inherit the 36×36 ShapeSpec
// default and the «default» variant which has lighter borders than surface.
Button* makeToolbarIcon(QWidget* parent, ui::AppIcon icon,
                        const QString& tooltip, bool toggle = false,
                        std::optional<std::pair<int, int>> scrollable = {},
                        bool showUnderline = false,
                        std::optional<ui::AppIcon> iconChecked = std::nullopt) {
  Button::Config cfg;
  cfg.icon = ui::getAppIcon(icon);
  if (iconChecked.has_value()) {
    cfg.iconChecked = ui::getAppIcon(*iconChecked);
  }
  cfg.variant = Button::Variant::Default;
  cfg.toggle = toggle;
  // No `cfg.size` — let the spec's ShapeSpec drive 36×36 like Python.
  if (scrollable.has_value()) {
    cfg.scrollable = scrollable;
  }
  if (showUnderline) {
    cfg.showUnderline = true;
  }
  auto* btn = new Button(cfg, parent);
  if (!tooltip.isEmpty()) {
    btn->setToolTip(tooltip);
  }
  return btn;
}

}  // namespace

// ---------------------------------------------------------------------------
// setupUi — mirrors Python Ui_ImageComparisonApp.setupUi()
// ---------------------------------------------------------------------------
void MainWindowUi::setupUi(QWidget* mainWindow) {
  createStaticWidgets(mainWindow);
  createSelectionControls(mainWindow);
  createViewControls(mainWindow);
  createVideoControls(mainWindow);
  createSliderControls(mainWindow);
  createTextAndStatusWidgets(mainWindow);
  // Python: self._configure_image_label()
  configureImageLabel();
  // Python: self._init_warning_label()
  initWarningLabel();
  // Python: self._layout = LayoutComposer(self); self._layout.build(main_window)
  // → handled externally by shell/layouts.cpp after setupUi returns.
  // Python: self._init_drag_overlays()
  initDragOverlays();
}

// ---------------------------------------------------------------------------
// createStaticWidgets — mirrors Python _create_static_widgets()
// ---------------------------------------------------------------------------
void MainWindowUi::createStaticWidgets(QWidget* mainWindow) {
  // Python: self.resolution_label1 = Label("--x--", variant="group-title")
  resolutionLabel1 = new sli::toolkit::Label(QStringLiteral("--x--"),
                                              QStringLiteral("group-title"));
  resolutionLabel2 = new sli::toolkit::Label(QStringLiteral("--x--"),
                                              QStringLiteral("group-title"));

  // Python: self.magnifier_settings_panel = QWidget(main_window)
  magnifierSettingsPanel = new QWidget(mainWindow);

  // Python: self.image_label = GLCanvas(main_window)
  imageLabel = new imgsli::app::CanvasWidget(mainWindow);

  // Python: self.length_warning_label = Label(parent=main_window)
  lengthWarningLabel = new sli::toolkit::Label(QString{}, mainWindow);

  // Python: self.workspace_tabs = AdaptiveTabStrip(add_icon=..., close_icon=...,
  //             add_button_menu=[], parent=main_window)
  {
    sli::toolkit::AdaptiveTabStrip::Config cfg;
    cfg.addIcon = ui::getAppIcon(ui::AppIcon::Add);
    cfg.closeIcon = ui::getAppIcon(ui::AppIcon::Close);
    cfg.addButtonMenu = std::vector<std::pair<QString, QVariant>>{};
    workspaceTabs = new sli::toolkit::AdaptiveTabStrip(cfg, mainWindow);
  }
  // Python: self.btn_new_session = self.workspace_tabs.add_button
  // AdaptiveTabStrip exposes addButton_ via addButton() accessor if available;
  // fall back to nullptr — bootstrap wires addRequested() signal directly.
  btnNewSession = nullptr;  // set externally by bootstrap once tab strip is live

  // Python: self.workspace_stack = QStackedWidget(main_window)
  workspaceStack = new QStackedWidget(mainWindow);

  // Python: self.image_session_page = QWidget(main_window)
  imageSessionPage = new QWidget(mainWindow);
  // Python: self.video_session_page = QWidget(main_window)
  videoSessionPage = new QWidget(mainWindow);
  // Python: self.video_session_widget = VideoSessionWidget(main_window)
  // VideoSessionWidget not yet ported — placeholder QWidget
  videoSessionWidget = new QWidget(mainWindow);
}

// ---------------------------------------------------------------------------
// createSelectionControls — mirrors Python _create_selection_controls()
// ---------------------------------------------------------------------------
void MainWindowUi::createSelectionControls(QWidget* parent) {
  // 1:1 with Python `_create_selection_controls`.
  btnImage1 = makeIconTextButton(parent, ui::AppIcon::Photo,
                                  QStringLiteral("Add image 1"));
  btnImage2 = makeIconTextButton(parent, ui::AppIcon::Photo,
                                  QStringLiteral("Add image 2"));
  // btn_swap: accent paint + long_press
  btnSwap = makeIconButton(parent, ui::AppIcon::Sync,
                            QStringLiteral("Swap images"), themeAccent(),
                            std::optional<int>(600));
  // Clear buttons: destructive red, long_press
  btnClearList1 = makeIconButton(parent, ui::AppIcon::Delete,
                                  QStringLiteral("Clear left list"),
                                  destructiveRed(),
                                  std::optional<int>(600));
  btnClearList2 = makeIconButton(parent, ui::AppIcon::Delete,
                                  QStringLiteral("Clear right list"),
                                  destructiveRed(),
                                  std::optional<int>(600));
  const QColor accent = themeAccent();
  helpButton = makeIconButton(parent, ui::AppIcon::Help,
                               QStringLiteral("Help"), accent);
  btnSettings = makeIconButton(parent, ui::AppIcon::Settings,
                                QStringLiteral("Settings…"), accent);
  btnTextSettings = makeIconButton(parent, ui::AppIcon::TextManipulator,
                                    QStringLiteral("Text settings"), accent);
  btnQuickSave = makeIconButton(parent, ui::AppIcon::QuickSave,
                                 QStringLiteral("Quick save"), accent);
  // Python: btn_magnifier_orientation — toggle, icon pair, scrollable (0,10), show_underline
  btnMagnifierOrientation = makeToolbarIcon(
      parent, ui::AppIcon::VerticalSplit,
      QStringLiteral("Magnifier split orientation"),
      /*toggle=*/true, std::make_pair(0, 10), /*showUnderline=*/true,
      ui::AppIcon::HorizontalSplit);
  btnSave = makeIconTextButton(parent, ui::AppIcon::Save,
                                QStringLiteral("Save current comparison"));

  // Python: label_rating1/2 = Label("–", parent, variant="group-title", elide=False)
  labelRating1 = new sli::toolkit::Label(QStringLiteral("–"),
                                          QStringLiteral("group-title"), parent);
  labelRating2 = new sli::toolkit::Label(QStringLiteral("–"),
                                          QStringLiteral("group-title"), parent);

  comboImage1 = new sli::toolkit::comboboxes::ScrollableComboBox(parent);
  comboImage2 = new sli::toolkit::comboboxes::ScrollableComboBox(parent);

  // Python: self.combo_interpolation = ScrollableComboBox(parent)
  //         self.combo_interpolation.setAutoWidthEnabled(True)
  comboInterpolation = new sli::toolkit::comboboxes::ScrollableComboBox(parent);
  comboInterpolation->setAutoWidthEnabled(true);
}

// ---------------------------------------------------------------------------
// createViewControls — mirrors Python _create_view_controls()
// ---------------------------------------------------------------------------
void MainWindowUi::createViewControls(QWidget* parent) {
  // Python: btn_orientation — toggle, scrollable (0,20), show_underline, icon pair
  btnOrientation = makeToolbarIcon(
      parent, ui::AppIcon::VerticalSplit,
      QStringLiteral("Split orientation"), /*toggle=*/true,
      std::make_pair(0, 20), /*showUnderline=*/true,
      ui::AppIcon::HorizontalSplit);
  btnMagnifier = makeToolbarIcon(parent, ui::AppIcon::Magnifier,
                                  QStringLiteral("Magnifier"), /*toggle=*/true);
  // Python: btn_magnifier_instances = InstancesCounterButton(parent=parent)
  btnMagnifierInstances = new sli::toolkit::InstancesCounterButton(parent);
  btnFreeze = makeToolbarIcon(parent, ui::AppIcon::Freeze,
                               QStringLiteral("Freeze magnifier"), /*toggle=*/true);
  btnFileNames = makeToolbarIcon(parent, ui::AppIcon::TextFilename,
                                  QStringLiteral("Filenames"), /*toggle=*/true);

  // Python: btn_diff_mode = Button(AppIcon.HIGHLIGHT_DIFFERENCES, menu=[], ...)
  btnDiffMode = makeToolbarIcon(parent, ui::AppIcon::HighlightDifferences,
                                 QStringLiteral("Diff mode"));
  // Python: btn_channel_mode = Button(AppIcon.PHOTO, menu=[], ...)
  btnChannelMode = makeToolbarIcon(parent, ui::AppIcon::Photo,
                                    QStringLiteral("Channel mode"));

  // Python: btn_magnifier_color_settings = ColorSettingsButton(parent=parent, ...)
  // ColorSettingsButton not yet ported — use DividerColor icon as placeholder.
  btnMagnifierColorSettings = makeToolbarIcon(
      parent, ui::AppIcon::DividerColor, QStringLiteral("Magnifier colors"),
      /*toggle=*/false);

  // Python: btn_magnifier_guides — toggle, scrollable (0,10), show_underline
  btnMagnifierGuides = makeToolbarIcon(
      parent, ui::AppIcon::MagnifierGuides, QStringLiteral("Guides"),
      /*toggle=*/true, std::make_pair(0, 10), /*showUnderline=*/true);

  // ------ "beginner" / simple-panel buttons (below magnifier_settings_panel) -----

  // Python: btn_orientation_simple — toggle, icon pair, no scrollable
  btnOrientationSimple = makeToolbarIcon(
      parent, ui::AppIcon::VerticalSplit,
      QStringLiteral("Orientation (simple)"), /*toggle=*/true,
      /*scrollable=*/{}, /*showUnderline=*/false,
      ui::AppIcon::HorizontalSplit);

  // Python: btn_divider_visible — toggle, icon pair DividerVisible/DividerHidden
  btnDividerVisible = makeToolbarIcon(
      parent, ui::AppIcon::DividerVisible,
      QStringLiteral("Divider visible"), /*toggle=*/true,
      /*scrollable=*/{}, /*showUnderline=*/false,
      ui::AppIcon::DividerHidden);

  // Python: btn_divider_color = Button(AppIcon.DIVIDER_COLOR, show_underline=True, ...)
  btnDividerColor = makeToolbarIcon(
      parent, ui::AppIcon::DividerColor,
      QStringLiteral("Divider color"), /*toggle=*/false,
      /*scrollable=*/{}, /*showUnderline=*/true);

  // Python: btn_divider_width = Button(AppIcon.DIVIDER_WIDTH, scrollable=(1,20), show_underline=True, ...)
  btnDividerWidth = makeToolbarIcon(
      parent, ui::AppIcon::DividerWidth,
      QStringLiteral("Divider width"), /*toggle=*/false,
      std::make_pair(1, 20), /*showUnderline=*/true);

  // Python: btn_magnifier_orientation_simple — toggle, icon pair, no scrollable
  btnMagnifierOrientationSimple = makeToolbarIcon(
      parent, ui::AppIcon::VerticalSplit,
      QStringLiteral("Magnifier orientation (simple)"), /*toggle=*/true,
      /*scrollable=*/{}, /*showUnderline=*/false,
      ui::AppIcon::HorizontalSplit);

  // Python: btn_magnifier_divider_visible — toggle, icon pair DividerVisible/DividerHidden
  btnMagnifierDividerVisible = makeToolbarIcon(
      parent, ui::AppIcon::DividerVisible,
      QStringLiteral("Magnifier divider visible"), /*toggle=*/true,
      /*scrollable=*/{}, /*showUnderline=*/false,
      ui::AppIcon::DividerHidden);

  // Python: btn_magnifier_color_settings_beginner = ColorSettingsButton(...)
  // Placeholder until ColorSettingsButton is ported.
  btnMagnifierColorSettingsBeginner = makeToolbarIcon(
      parent, ui::AppIcon::CaptureAreaColor,
      QStringLiteral("Magnifier colors (simple)"), /*toggle=*/false);

  // Python: btn_magnifier_divider_width — scrollable (1,10), show_underline
  btnMagnifierDividerWidth = makeToolbarIcon(
      parent, ui::AppIcon::DividerWidth,
      QStringLiteral("Magnifier divider width"), /*toggle=*/false,
      std::make_pair(1, 10), /*showUnderline=*/true);

  // Python: btn_magnifier_guides_simple — toggle only
  btnMagnifierGuidesSimple = makeToolbarIcon(
      parent, ui::AppIcon::MagnifierGuides,
      QStringLiteral("Magnifier guides (simple)"), /*toggle=*/true);

  // Python: btn_magnifier_guides_width — scrollable (1,10), show_underline
  btnMagnifierGuidesWidth = makeToolbarIcon(
      parent, ui::AppIcon::DividerWidth,
      QStringLiteral("Magnifier guides width"), /*toggle=*/false,
      std::make_pair(1, 10), /*showUnderline=*/true);
}

// ---------------------------------------------------------------------------
// createVideoControls — mirrors Python _create_video_controls()
// ---------------------------------------------------------------------------
void MainWindowUi::createVideoControls(QWidget* parent) {
  // Python only disables btnPause until a recording is active — record and
  // video_editor stay enabled.
  btnRecord = makeToolbarIcon(parent, ui::AppIcon::Record,
                               QStringLiteral("Record"), /*toggle=*/true,
                               std::nullopt, /*showUnderline=*/false,
                               ui::AppIcon::Stop);
  btnPause = makeToolbarIcon(parent, ui::AppIcon::Pause,
                              QStringLiteral("Pause"), /*toggle=*/true,
                              std::nullopt, /*showUnderline=*/false,
                              ui::AppIcon::Play);
  btnPause->setEnabled(false);
  // Python: btn_video_editor = Button(AppIcon.EXPORT_VIDEO, ...)
  btnVideoEditor = makeToolbarIcon(parent, ui::AppIcon::ExportVideo,
                                    QStringLiteral("Video editor"));
}

// ---------------------------------------------------------------------------
// createSliderControls — mirrors Python _create_slider_controls()
// ---------------------------------------------------------------------------
void MainWindowUi::createSliderControls(QWidget* parent) {
  // Python: self.slider_size = Slider(Qt.Orientation.Horizontal, parent)
  sliderSize = new sli::toolkit::Slider(Qt::Horizontal, parent);
  sliderSize->setRange(10, 100);
  sliderSize->setValue(30);
  // Python: self.slider_capture = Slider(Qt.Orientation.Horizontal, parent)
  sliderCapture = new sli::toolkit::Slider(Qt::Horizontal, parent);
  sliderCapture->setRange(10, 100);
  sliderCapture->setValue(25);
  // Python: self.slider_speed = Slider(Qt.Orientation.Horizontal, parent)
  sliderSpeed = new sli::toolkit::Slider(Qt::Horizontal, parent);
  sliderSpeed->setRange(1, 50);
  sliderSpeed->setValue(10);
}

// ---------------------------------------------------------------------------
// createTextAndStatusWidgets — mirrors Python _create_text_and_status_widgets()
// ---------------------------------------------------------------------------
void MainWindowUi::createTextAndStatusWidgets(QWidget* parent) {
  editName1 = new sli::toolkit::CustomLineEdit(parent);
  editName2 = new sli::toolkit::CustomLineEdit(parent);

  // Python: label_magnifier_size/capture_size/movement_speed/interpolation
  //         Label(parent=parent, variant="group-title")
  labelMagnifierSize = new sli::toolkit::Label(
      QString{}, QStringLiteral("group-title"), parent);
  labelCaptureSize = new sli::toolkit::Label(
      QString{}, QStringLiteral("group-title"), parent);
  labelMovementSpeed = new sli::toolkit::Label(
      QString{}, QStringLiteral("group-title"), parent);
  labelInterpolation = new sli::toolkit::Label(
      QString{}, QStringLiteral("group-title"), parent);

  // Python: file_name_label1/2 = Label("--", parent, variant="group-title")
  fileNameLabel1 = new sli::toolkit::Label(
      QStringLiteral("--"), QStringLiteral("group-title"), parent);
  fileNameLabel2 = new sli::toolkit::Label(
      QStringLiteral("--"), QStringLiteral("group-title"), parent);

  // Python: label_edit_name1/2 = Label(parent=parent, variant="group-title")
  labelEditName1 = new sli::toolkit::Label(
      QString{}, QStringLiteral("group-title"), parent);
  labelEditName2 = new sli::toolkit::Label(
      QString{}, QStringLiteral("group-title"), parent);
}

// ---------------------------------------------------------------------------
// configureImageLabel — mirrors Python _configure_image_label()
// ---------------------------------------------------------------------------
void MainWindowUi::configureImageLabel() {
  // Python: self.image_label.setMinimumSize(200, 150)
  imageLabel->setMinimumSize(200, 150);
  // Python: self.image_label.setSizePolicy(Expanding, Expanding)
  imageLabel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
  // Python: self.image_label.setMouseTracking(True)
  imageLabel->setMouseTracking(true);
  // Python: self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
  imageLabel->setFocusPolicy(Qt::StrongFocus);
  // Python: self.image_label.setAutoFillBackground(True)
  imageLabel->setAutoFillBackground(true);
}

// ---------------------------------------------------------------------------
// initWarningLabel — mirrors Python _init_warning_label()
// ---------------------------------------------------------------------------
void MainWindowUi::initWarningLabel() {
  // Python: self.length_warning_label.setProperty("class", "warning-label")
  lengthWarningLabel->setProperty("class", QStringLiteral("warning-label"));
  // Python: self.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
  lengthWarningLabel->setAlignment(Qt::AlignCenter);
  // Python: self.length_warning_label.setVisible(False)
  lengthWarningLabel->setVisible(false);
}

// ---------------------------------------------------------------------------
// initDragOverlays — mirrors Python _init_drag_overlays()
// ---------------------------------------------------------------------------
void MainWindowUi::initDragOverlays() {
  // Python: self.image_label.set_drag_overlay_state(False)
  // CanvasWidget does not expose set_drag_overlay_state yet —
  // the overlay state is managed by the presenter after layout runs.
  // Nothing to do here; dragOverlay is set by LayoutComposer::build().
}

}  // namespace imgsli::app::shell

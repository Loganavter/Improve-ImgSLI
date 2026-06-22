// Mirror of `src/ui/main_window/ui.py`. Each section corresponds 1:1 to
// the Python `_create_*_controls` method — same widget kind, same args,
// same accent-paint where Python passes `background_color=...`.

#include "shell/ui.h"

#include <QCursor>
#include <QTabBar>
#include <QWidget>

#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/atomic/slider.h"
#include "sli/toolkit/atomic/text_labels.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/scrollable_combo_box.h"
#include "sli/toolkit/theme.h"
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

Button* makeToggleIconButton(QWidget* parent, ui::AppIcon icon,
                              const QString& tooltip,
                              std::optional<std::pair<int, int>> scrollable = {},
                              bool showUnderline = false) {
  Button::Config cfg;
  cfg.icon = ui::getAppIcon(icon);
  cfg.variant = Button::Variant::Surface;
  cfg.toggle = true;
  cfg.size = QSize(kToggleIconSize, kToggleIconSize);
  cfg.iconSize = 22;
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

void MainWindowUi::setupUi(QWidget* mainWindow) {
  createStaticWidgets(mainWindow);
  createSelectionControls(mainWindow);
  createViewControls(mainWindow);
  createVideoControls(mainWindow);
  createSliderControls(mainWindow);
  createTextAndStatusWidgets(mainWindow);
}

void MainWindowUi::createStaticWidgets(QWidget* mainWindow) {
  // Python uses `AdaptiveTabStrip` (custom toolkit widget); not yet ported
  // to C++ — see TOOLKIT_PORT_AUDIT. Fall back to QTabBar wrapped in a
  // container so the layout slot is still valid.
  workspaceTabsBar = new QWidget(mainWindow);
  workspaceTabsBar->setObjectName(QStringLiteral("WorkspaceTabsBar"));
  workspaceTabs = new QTabBar(workspaceTabsBar);
  workspaceTabs->setExpanding(false);
  workspaceTabs->setTabsClosable(true);
  workspaceTabs->addTab(QStringLiteral("Image Compare 1"));
  workspaceTabs->setTabButton(0, QTabBar::RightSide, nullptr);

  Button::Config addCfg;
  addCfg.text = QStringLiteral("+");
  addCfg.variant = Button::Variant::Ghost;
  addCfg.size = QSize(kIconButtonSize, kIconButtonSize);
  btnNewSession = new Button(addCfg, workspaceTabsBar);
  btnNewSession->setEnabled(false);  // multi-session not yet wired

  imageSessionPage = new QWidget(mainWindow);
  videoSessionPage = new QWidget(mainWindow);
  magnifierSettingsPanel = new QWidget(mainWindow);
}

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
  // Clear buttons: destructive red, long_press to clear-all vs clear-active
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
  btnTextSettings = makeIconButton(parent, ui::AppIcon::TextFilename,
                                    QStringLiteral("Text settings"), accent);
  btnQuickSave = makeIconButton(parent, ui::AppIcon::QuickSave,
                                 QStringLiteral("Quick save"), accent);
  btnSave = makeIconTextButton(parent, ui::AppIcon::Save,
                                QStringLiteral("Save current comparison"));

  // Combobox row — Python `_combobox_row` builds two rating-label +
  // ScrollableComboBox pairs sitting below the selection buttons.
  labelRating1 = new sli::toolkit::Label(QStringLiteral("–"));
  labelRating2 = new sli::toolkit::Label(QStringLiteral("–"));
  comboImage1 = new sli::toolkit::comboboxes::ScrollableComboBox(parent);
  comboImage2 = new sli::toolkit::comboboxes::ScrollableComboBox(parent);
}

void MainWindowUi::createViewControls(QWidget* parent) {
  // 1:1 with Python `_create_view_controls` — all toolbar buttons use the
  // «default» variant + default 36×36 size, NO fixed-size, NO Surface
  // variant (which Python reserves for the painted accent/red buttons).
  btnOrientation = makeToolbarIcon(
      parent, ui::AppIcon::VerticalSplit,
      QStringLiteral("Split orientation"), /*toggle=*/true,
      std::make_pair(0, 20), /*showUnderline=*/true,
      ui::AppIcon::HorizontalSplit);
  btnMagnifier = makeToolbarIcon(parent, ui::AppIcon::Magnifier,
                                  QStringLiteral("Magnifier"), true);
  btnFreeze = makeToolbarIcon(parent, ui::AppIcon::Freeze,
                               QStringLiteral("Freeze magnifier"), true);
  btnFileNames = makeToolbarIcon(parent, ui::AppIcon::TextFilename,
                                  QStringLiteral("Filenames"), true);
  btnDiffMode = makeToolbarIcon(parent, ui::AppIcon::HighlightDifferences,
                                 QStringLiteral("Diff mode"));
  btnChannelMode = makeToolbarIcon(parent, ui::AppIcon::Photo,
                                    QStringLiteral("Channel mode"));
  btnMagnifierGuides = makeToolbarIcon(
      parent, ui::AppIcon::MagnifierGuides, QStringLiteral("Guides"),
      /*toggle=*/true, std::make_pair(0, 10), /*showUnderline=*/true);
  btnMagnifierGuides->setChecked(true);
  btnMagnifierOrientation = makeToolbarIcon(
      parent, ui::AppIcon::VerticalSplit,
      QStringLiteral("Magnifier split"), /*toggle=*/true,
      std::make_pair(0, 10), /*showUnderline=*/true,
      ui::AppIcon::HorizontalSplit);
  btnMagnifierColor = makeToolbarIcon(parent, ui::AppIcon::DividerColor,
                                       QStringLiteral("Magnifier colors"),
                                       true);
  // Python uses `InstancesCounterButton` — custom toolkit widget not yet
  // ported to C++. Use a regular toggle as a placeholder so the layout slot
  // is occupied. Tracked in TOOLKIT_PORT_AUDIT.
  btnMagnifierInstances = makeToolbarIcon(
      parent, ui::AppIcon::AddCircle,
      QStringLiteral("Magnifier instances"), true);
}

void MainWindowUi::createVideoControls(QWidget* parent) {
  // Python only disables btnPause until a recording is active — record and
  // video_editor stay enabled. Disabling them all was a port slip.
  // Python uses icon-pairs for record/pause: record swaps to «stop» glyph
  // when checked, pause swaps to «play» glyph when checked.
  btnRecord = makeToolbarIcon(parent, ui::AppIcon::Record,
                               QStringLiteral("Record"), /*toggle=*/true,
                               std::nullopt, /*showUnderline=*/false,
                               ui::AppIcon::Stop);
  btnPause = makeToolbarIcon(parent, ui::AppIcon::Pause,
                              QStringLiteral("Pause"), /*toggle=*/true,
                              std::nullopt, /*showUnderline=*/false,
                              ui::AppIcon::Play);
  btnPause->setEnabled(false);
  btnVideoEditor = makeToolbarIcon(parent, ui::AppIcon::VideoEdit,
                                    QStringLiteral("Video editor"));
}

void MainWindowUi::createSliderControls(QWidget* parent) {
  sliderSplit = new sli::toolkit::Slider(Qt::Horizontal, parent);
  sliderSplit->setRange(0, 1000);
  sliderSplit->setValue(500);
  sliderMagnifierSize = new sli::toolkit::Slider(Qt::Horizontal, parent);
  sliderMagnifierSize->setRange(10, 100);
  sliderMagnifierSize->setValue(30);
  sliderCaptureSize = new sli::toolkit::Slider(Qt::Horizontal, parent);
  sliderCaptureSize->setRange(10, 100);
  sliderCaptureSize->setValue(25);
  sliderMovementSpeed = new sli::toolkit::Slider(Qt::Horizontal, parent);
  sliderMovementSpeed->setRange(1, 50);
  sliderMovementSpeed->setValue(10);
}

void MainWindowUi::createTextAndStatusWidgets(QWidget* parent) {
  editName1 = new sli::toolkit::CustomLineEdit(parent);
  editName2 = new sli::toolkit::CustomLineEdit(parent);
  resolutionLabel1 = new sli::toolkit::Label(QStringLiteral("--x--"));
  resolutionLabel2 = new sli::toolkit::Label(QStringLiteral("--x--"));
  psnrLabel = new sli::toolkit::Label(QStringLiteral("PSNR: --"));
  ssimLabel = new sli::toolkit::Label(QStringLiteral("SSIM: --"));
  fileNameLabel1 = new sli::toolkit::Label(QStringLiteral("--"));
  fileNameLabel2 = new sli::toolkit::Label(QStringLiteral("--"));
}

}  // namespace imgsli::app::shell

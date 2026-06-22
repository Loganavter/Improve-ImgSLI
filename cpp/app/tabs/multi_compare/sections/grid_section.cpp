#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QStandardPaths>
#include <QString>
#include <QVBoxLayout>
#include <QVariantMap>
#include <QWidget>

#include <algorithm>

#include "plugins/comparison/controller.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "tabs/multi_compare/grid.h"
#include "tabs/multi_compare/sections/sections.h"

namespace imgsli::app::multi_compare_sections {

void buildGridSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;
  ComparisonController* controller = ctx.controller;
  QLabel* status = ctx.status;

  auto* gridSectionHeader =
      new QLabel(tr(QStringLiteral("multi_compare.grid_section")), root);
  layout->addWidget(gridSectionHeader);
  auto* grid = new MultiCompareGrid(2, 2, root);
  grid->setObjectName(QStringLiteral("multiCompareGrid"));
  grid->setMinimumHeight(220);
  layout->addWidget(grid, 1);

  auto* playlist = new QListWidget(root);
  playlist->setObjectName(QStringLiteral("multiCompareGridPlaylist"));
  playlist->setMaximumHeight(120);
  layout->addWidget(playlist);

  auto* gridToolbar = new QWidget(root);
  auto* gridToolbarLayout = new QHBoxLayout(gridToolbar);
  gridToolbarLayout->setContentsMargins(0, 0, 0, 0);
  auto* addPair = new sli::toolkit::Button(
      tr(QStringLiteral("multi_compare.add_pair")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* removePair = new sli::toolkit::Button(
      tr(QStringLiteral("multi_compare.remove_pair")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* moveUp = new sli::toolkit::Button(
      tr(QStringLiteral("multi_compare.move_up")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* moveDown = new sli::toolkit::Button(
      tr(QStringLiteral("multi_compare.move_down")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* exportComposite = new sli::toolkit::Button(
      tr(QStringLiteral("multi_compare.export_composite")),
      sli::toolkit::Button::Variant::Default, root);
  auto* cellW = new sli::toolkit::SpinBox(root);
  cellW->setRange(64, 8192);
  cellW->setValue(960);
  cellW->setSuffix(QStringLiteral(" px"));
  auto* cellH = new sli::toolkit::SpinBox(root);
  cellH->setRange(64, 8192);
  cellH->setValue(540);
  cellH->setSuffix(QStringLiteral(" px"));
  gridToolbarLayout->addWidget(addPair);
  gridToolbarLayout->addWidget(removePair);
  gridToolbarLayout->addWidget(moveUp);
  gridToolbarLayout->addWidget(moveDown);
  gridToolbarLayout->addWidget(
      new QLabel(tr(QStringLiteral("multi_compare.cell_size")), root));
  gridToolbarLayout->addWidget(cellW);
  gridToolbarLayout->addWidget(cellH);
  gridToolbarLayout->addWidget(exportComposite);
  layout->addWidget(gridToolbar);

  const auto refreshPlaylistView = [grid, playlist]() {
    playlist->clear();
    for (const auto& entry : grid->playlist()) {
      playlist->addItem(
          QStringLiteral("%1 ⟷ %2").arg(entry.first, entry.second));
    }
  };

  const auto pushSharedPlan = [grid, controller]() {
    if (controller == nullptr) {
      grid->setSharedPlan(0.5F, false, true, false, false);
      return;
    }
    grid->setSharedPlan(controller->split(), controller->horizontal(),
                         controller->magnifierEnabled(),
                         controller->guidesEnabled(),
                         controller->pasteOverlayEnabled());
  };
  pushSharedPlan();

  QObject::connect(grid, &MultiCompareGrid::playlistChanged, root,
                    refreshPlaylistView);
  if (controller != nullptr) {
    QObject::connect(controller, &ComparisonController::comparisonChanged,
                      root, pushSharedPlan);
  }

  QObject::connect(
      addPair, &sli::toolkit::Button::clicked, root, [grid, root]() {
        const QString left = QFileDialog::getOpenFileName(
            root, tr(QStringLiteral("multi_compare.choose_left")));
        if (left.isEmpty()) return;
        const QString right = QFileDialog::getOpenFileName(
            root, tr(QStringLiteral("multi_compare.choose_right")),
            QFileInfo(left).absolutePath());
        grid->addPair(left, right);
      });
  QObject::connect(removePair, &sli::toolkit::Button::clicked, root,
                    [grid, playlist]() {
                      const int i = playlist->currentRow();
                      grid->removeAt(i);
                    });
  QObject::connect(moveUp, &sli::toolkit::Button::clicked, root,
                    [grid, playlist]() {
                      const int i = playlist->currentRow();
                      grid->moveUp(i);
                      playlist->setCurrentRow(std::max(0, i - 1));
                    });
  QObject::connect(moveDown, &sli::toolkit::Button::clicked, root,
                    [grid, playlist]() {
                      const int i = playlist->currentRow();
                      grid->moveDown(i);
                      playlist->setCurrentRow(
                          std::min(grid->playlistSize() - 1, i + 1));
                    });
  QObject::connect(
      exportComposite, &sli::toolkit::Button::clicked, root,
      [grid, cellW, cellH, status, root]() {
        QString directory =
            QStandardPaths::writableLocation(QStandardPaths::PicturesLocation);
        if (directory.isEmpty()) directory = QDir::homePath();
        const QString defaultPath =
            QDir(directory).filePath(QStringLiteral("imgsli-grid.png"));
        const QString out = QFileDialog::getSaveFileName(
            root,
            tr(QStringLiteral("multi_compare.choose_composite_output")),
            defaultPath, QStringLiteral("PNG (*.png)"));
        if (out.isEmpty()) return;
        const QVariantMap result = grid->exportComposite(
            out, cellW->value(), cellH->value(), QStringLiteral("PNG"), 95);
        if (result.value(QStringLiteral("ok")).toBool()) {
          status->setText(
              tr(QStringLiteral("multi_compare.composite_saved"))
                  .arg(result.value(QStringLiteral("width")).toInt())
                  .arg(result.value(QStringLiteral("height")).toInt())
                  .arg(out));
        } else {
          status->setText(
              tr(QStringLiteral("multi_compare.composite_failed"))
                  .arg(result.value(QStringLiteral("error")).toString()));
        }
      });
}

}  // namespace imgsli::app::multi_compare_sections

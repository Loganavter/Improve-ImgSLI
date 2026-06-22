#pragma once

#include <QImage>
#include <QObject>
#include <QPair>
#include <QString>
#include <QVector>
#include <QWidget>

class QGridLayout;
class QListWidget;

namespace imgsli::app {

class CanvasWidget;

/// Multi-pair comparison grid. Hosts N × M small `CanvasWidget` cells in a
/// `QGridLayout` and feeds each cell with a pair from an internal playlist.
/// Mirrors the spirit of `src/tabs/multi_compare/ui/gl_grid.py` for v1:
/// a fixed cell count with shared plan settings and a composite export
/// that tiles each cell's offscreen render into a single image.
///
/// Per-cell composition, drag/drop transport, and the full GL grid widget
/// remain Python-side until the dedicated grid renderer lands; the v1
/// implementation here delivers the user-visible playlist + composite
/// export contract end-to-end.
class MultiCompareGrid final : public QWidget {
  Q_OBJECT

 public:
  explicit MultiCompareGrid(int rows = 2, int cols = 2,
                            QWidget* parent = nullptr);

  int rows() const { return rows_; }
  int cols() const { return cols_; }
  int cellCount() const { return rows_ * cols_; }
  int playlistSize() const { return playlist_.size(); }

  /// Apply a plan to every cell (split, magnifier, guides, divider,
  /// orientation). Texture ids are overridden per cell so each cell
  /// shows its own pair.
  void setSharedPlan(float split, bool horizontal, bool magnifierEnabled,
                     bool guidesEnabled, bool pasteOverlayEnabled);

  void addPair(const QString& left, const QString& right);
  void removeAt(int index);
  void moveUp(int index);
  void moveDown(int index);

  /// Render each cell to `cellWidth × cellHeight`, tile into a single
  /// composite image, and write it to `path` via the export plugin.
  /// Returns a status map: { ok, path, width, height, error }.
  QVariantMap exportComposite(const QString& path, int cellWidth,
                              int cellHeight, const QString& format,
                              int quality) const;

  /// The playlist as (left, right) pairs.
  QVector<QPair<QString, QString>> playlist() const { return playlist_; }

 signals:
  void playlistChanged();

 private:
  void refreshCells();
  QImage decodeImage(const QString& path) const;

  int rows_;
  int cols_;
  QGridLayout* gridLayout_ = nullptr;
  QVector<CanvasWidget*> cells_;
  QVector<QPair<QString, QString>> playlist_;
  float split_ = 0.5F;
  bool horizontal_ = false;
  bool magnifierEnabled_ = true;
  bool guidesEnabled_ = false;
  bool pasteOverlayEnabled_ = false;
};

}  // namespace imgsli::app

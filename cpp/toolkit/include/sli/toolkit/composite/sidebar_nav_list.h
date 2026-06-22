#pragma once

#include <QColor>
#include <QHash>
#include <QPixmap>
#include <QScrollArea>
#include <QSize>
#include <QString>
#include <QVariant>
#include <QVector>
#include <QWidget>

class QVBoxLayout;

namespace sli::toolkit {

class Button;

// -----------------------------------------------------------------------
// IconListItem — lightweight data struct (mirrors Python @dataclass)
// -----------------------------------------------------------------------
struct IconListItem {
  QString text;
  QVariant icon;
  QVariant data;
  int rowHeight = 44;
  QVariant selectedIcon;
};

// -----------------------------------------------------------------------
// NavRowButton — one row in the sidebar nav list.
// A custom-painted clickable widget that mimics the Python _NavRowButton
// contract: no QAbstractButton toggle (managed externally), NoFocus policy,
// icon + text drawn left-aligned with ripple-like background on hover/check.
// -----------------------------------------------------------------------
class NavRowButton : public QWidget {
  Q_OBJECT

 public:
  explicit NavRowButton(const QString& text,
                        int rowHeight,
                        int iconSize,
                        QWidget* parent = nullptr);
  ~NavRowButton() override = default;

  bool isSelected() const { return selected_; }
  void setSelected(bool selected);

  void setNavPixmaps(const QPixmap& normal, const QPixmap& selected);
  const QPixmap& normalPixmap() const { return normalPixmap_; }
  const QPixmap& selectedPixmap() const { return selectedPixmap_; }

  void setText(const QString& text);
  QString text() const { return text_; }

 signals:
  void clicked();

 protected:
  void paintEvent(QPaintEvent* event) override;
  void enterEvent(QEnterEvent* event) override;
  void leaveEvent(QEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void mouseReleaseEvent(QMouseEvent* event) override;

 private:
  void updateBg();

  QString text_;
  int iconSizePx_ = 24;
  bool selected_ = false;
  bool hovered_ = false;
  bool pressed_ = false;
  QPixmap normalPixmap_;
  QPixmap selectedPixmap_;
};

// -----------------------------------------------------------------------
// IconListWidget — QScrollArea with NavRowButton rows
// -----------------------------------------------------------------------
class IconListWidget : public QWidget {
  Q_OBJECT

 public:
  explicit IconListWidget(QWidget* parent = nullptr,
                          QSize iconSize = QSize(24, 24),
                          int rowHeight = 44,
                          const QString& selectedIconMode = QStringLiteral("invert"));
  ~IconListWidget() override;

  // ----- items -----
  void setItems(const QVector<IconListItem>& items);
  int addItem(const QString& text,
              const QVariant& icon = {},
              const QVariant& data = {},
              int rowHeight = -1,
              const QVariant& selectedIcon = {});
  void clear();
  int count() const;

  // ----- selection -----
  int currentRow() const { return currentRow_; }
  void setCurrentRow(int idx);

  // ----- item access (proxy for QListWidgetItem-style API) -----
  QString itemText(int idx) const;
  QVariant itemData(int idx, int role = Qt::UserRole) const;
  void setItemSizeHint(int idx, const QSize& size);
  void setItemIcon(int idx, const QVariant& icon);
  void setItemSelectedIcon(int idx, const QVariant& icon);

  // ----- icon mode -----
  QSize iconSize() const { return iconSize_; }
  void setIconSize(const QSize& size);
  void refreshIcons();
  QString selectedIconMode() const { return selectedIconMode_; }
  void setSelectedIconMode(const QString& mode);

  // ----- scroll appearance -----
  void enableMinimalScrollbar();

 signals:
  void currentRowChanged(int row);
  void currentItemChanged(int row, int prevRow);

 private:
  struct RowSpec {
    QString text;
    QVariant icon;
    QVariant selectedIcon;
    int rowHeight = 44;
    NavRowButton* button = nullptr;
    QHash<int, QVariant> dataRoles;
    QPixmap normalPixmap;
    QPixmap selectedPixmap;
  };

  void appendRow(const IconListItem& spec);
  void onRowClicked(int idx);
  void applyIcon(RowSpec& row);
  QPixmap selectedPixmapForRow(RowSpec& row, const QPixmap& normalPixmap);
  QString normalizeSelectedIconMode(const QString& mode) const;
  QPixmap invertedPixmap(const QPixmap& base) const;

  static constexpr int kLeftPadding = 12;
  static constexpr int kIconTextGap = 10;

  int rowHeight_ = 44;
  QSize iconSize_{24, 24};
  QString selectedIconMode_ = QStringLiteral("invert");
  QVector<RowSpec> rows_;
  int currentRow_ = -1;
  QScrollArea* scroll_ = nullptr;
  QWidget* host_ = nullptr;
  QVBoxLayout* hostLayout_ = nullptr;
};

}  // namespace sli::toolkit
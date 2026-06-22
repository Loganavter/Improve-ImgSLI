#pragma once

#include <QPushButton>
#include <QSize>
#include <QString>
#include <QWidget>

class QLabel;
class QLineEdit;

namespace imgsli::app::ui::widgets {

// OK / Cancel-style trailing action bar. Mirror of Python
// `src/ui/widgets/form_controls.py::DialogActionBar`. The right-aligned
// `primaryButton()` is the affirmative action; the left of it is the
// secondary / cancel action.
class DialogActionBar : public QWidget {
  Q_OBJECT
 public:
  explicit DialogActionBar(const QString& primaryText, const QString& secondaryText,
                           QWidget* parent = nullptr,
                           const QSize& primaryMinSize = QSize(100, 36),
                           const QSize& secondaryMinSize = QSize(100, 36));

  QPushButton* primaryButton() const noexcept { return primary_; }
  QPushButton* secondaryButton() const noexcept { return secondary_; }

 private:
  QPushButton* primary_;
  QPushButton* secondary_;
};

// Output-path section (directory picker + favourite slot + filename input).
// Mirror of Python `OutputPathSection`. The owner wires `browseButton()`,
// `setFavoriteButton()` and `useFavoriteButton()` to actual handlers.
class OutputPathSection : public QWidget {
  Q_OBJECT
 public:
  struct Labels {
    QString directoryLabel;
    QString browseText;
    QString setFavoriteText;
    QString useFavoriteText;
    QString filenameLabel;
  };

  explicit OutputPathSection(const Labels& labels, QWidget* parent = nullptr);

  QLineEdit* directoryEdit() const noexcept { return dirEdit_; }
  QLineEdit* filenameEdit() const noexcept { return filenameEdit_; }
  QPushButton* browseButton() const noexcept { return browseButton_; }
  QPushButton* setFavoriteButton() const noexcept { return setFavoriteButton_; }
  QPushButton* useFavoriteButton() const noexcept { return useFavoriteButton_; }

 private:
  QLabel* dirLabel_;
  QLineEdit* dirEdit_;
  QPushButton* browseButton_;
  QPushButton* setFavoriteButton_;
  QPushButton* useFavoriteButton_;
  QLabel* filenameLabel_;
  QLineEdit* filenameEdit_;
};

}  // namespace imgsli::app::ui::widgets

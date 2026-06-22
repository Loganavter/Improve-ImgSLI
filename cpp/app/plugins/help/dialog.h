#pragma once

#include <QDialog>
#include <QString>
#include <QVector>

class QListWidget;
class QTextBrowser;
class QUrl;

namespace imgsli::app {

class HelpDialog final : public QDialog {
  Q_OBJECT

 public:
  explicit HelpDialog(const QString& helpRoot, const QString& language,
                      QWidget* parent = nullptr);

  void setLanguage(const QString& language);
  int sectionCount() const { return sections_.size(); }

 private slots:
  void showSection(int index);
  void handleLink(const QUrl& url);

 private:
  struct Section {
    QString slug;
    QString title;
    QString markdown;
  };

  void reload();
  QVector<Section> loadLanguage(const QString& language) const;
  static QString normalizedLanguage(const QString& language);
  static Section readSection(const QString& path);
  int indexForSlug(const QString& slug) const;

  QString helpRoot_;
  QString language_;
  QVector<Section> sections_;
  QListWidget* sidebar_ = nullptr;
  QTextBrowser* browser_ = nullptr;
};

}  // namespace imgsli::app

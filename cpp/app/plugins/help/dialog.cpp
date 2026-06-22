#include "plugins/help/dialog.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QListWidget>
#include <QRegularExpression>
#include <QScrollBar>
#include <QTextBrowser>
#include <QTextStream>
#include <QUrl>

#include "shell/i18n_helper.h"

namespace imgsli::app {

HelpDialog::HelpDialog(const QString& helpRoot, const QString& language,
                       QWidget* parent)
    : QDialog(parent), helpRoot_(helpRoot), language_(language) {
  setObjectName(QStringLiteral("HelpDialog"));
  resize(1000, 720);

  auto* layout = new QHBoxLayout(this);
  sidebar_ = new QListWidget(this);
  sidebar_->setObjectName(QStringLiteral("helpSidebar"));
  sidebar_->setMinimumWidth(220);
  browser_ = new QTextBrowser(this);
  browser_->setObjectName(QStringLiteral("helpBrowser"));
  browser_->setOpenLinks(false);
  browser_->setOpenExternalLinks(true);
  layout->addWidget(sidebar_);
  layout->addWidget(browser_, 1);

  connect(sidebar_, &QListWidget::currentRowChanged, this,
          &HelpDialog::showSection);
  connect(browser_, &QTextBrowser::anchorClicked, this,
          &HelpDialog::handleLink);
  reload();
}

void HelpDialog::setLanguage(const QString& language) {
  const QString normalized = normalizedLanguage(language);
  if (normalized == language_) {
    return;
  }
  language_ = normalized;
  reload();
}

void HelpDialog::reload() {
  sections_ = loadLanguage(language_);
  if (sections_.isEmpty() && language_ != QStringLiteral("en")) {
    sections_ = loadLanguage(QStringLiteral("en"));
  }
  setWindowTitle(imgsli::app::tr(QStringLiteral("help.title")));
  sidebar_->clear();
  for (const Section& section : sections_) {
    sidebar_->addItem(section.title);
  }
  if (!sections_.isEmpty()) {
    sidebar_->setCurrentRow(0);
  } else {
    browser_->setPlainText(
        imgsli::app::tr(QStringLiteral("help.no_content")));
  }
}

QVector<HelpDialog::Section> HelpDialog::loadLanguage(
    const QString& language) const {
  QDir dir(QDir(helpRoot_).filePath(normalizedLanguage(language)));
  const QStringList files =
      dir.entryList({QStringLiteral("*.md")}, QDir::Files, QDir::Name);
  QVector<Section> result;
  result.reserve(files.size());
  for (const QString& file : files) {
    Section section = readSection(dir.filePath(file));
    if (!section.markdown.isEmpty()) {
      result.push_back(std::move(section));
    }
  }
  return result;
}

QString HelpDialog::normalizedLanguage(const QString& language) {
  if (language.startsWith(QStringLiteral("pt"), Qt::CaseInsensitive)) {
    return QStringLiteral("pt_BR");
  }
  if (language.startsWith(QStringLiteral("ru"), Qt::CaseInsensitive)) {
    return QStringLiteral("ru");
  }
  if (language.startsWith(QStringLiteral("zh"), Qt::CaseInsensitive)) {
    return QStringLiteral("zh");
  }
  return QStringLiteral("en");
}

HelpDialog::Section HelpDialog::readSection(const QString& path) {
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
    return {};
  }
  const QString markdown = QString::fromUtf8(file.readAll());
  const QStringList lines = markdown.split(u'\n');
  QString title;
  static const QRegularExpression heading(
      QStringLiteral(R"(^\s*#{1,2}\s+(.+?)\s*$)"));
  for (const QString& line : lines) {
    const QRegularExpressionMatch match = heading.match(line);
    if (match.hasMatch()) {
      title = match.captured(1);
      title.remove(QRegularExpression(QStringLiteral(R"(\s*\{#[^}]+\}\s*$)")));
      break;
    }
  }
  const QFileInfo info(path);
  QString slug = info.completeBaseName();
  slug.remove(QRegularExpression(QStringLiteral(R"(^\d+_)")));
  if (title.isEmpty()) {
    title = slug;
  }
  return {.slug = slug, .title = title, .markdown = markdown};
}

void HelpDialog::showSection(int index) {
  if (index < 0 || index >= sections_.size()) {
    return;
  }
  browser_->setMarkdown(sections_[index].markdown);
  browser_->verticalScrollBar()->setValue(0);
}

void HelpDialog::handleLink(const QUrl& url) {
  if (url.scheme() != QStringLiteral("help")) {
    browser_->setSource(url);
    return;
  }
  QString slug = url.host();
  if (slug.isEmpty()) {
    slug = url.path();
    slug.remove(0, slug.startsWith(u'/') ? 1 : 0);
  }
  const int index = indexForSlug(slug);
  if (index >= 0) {
    sidebar_->setCurrentRow(index);
    if (!url.fragment().isEmpty()) {
      browser_->scrollToAnchor(url.fragment());
    }
  }
}

int HelpDialog::indexForSlug(const QString& slug) const {
  for (int i = 0; i < sections_.size(); ++i) {
    if (sections_[i].slug == slug) {
      return i;
    }
  }
  return -1;
}

}  // namespace imgsli::app

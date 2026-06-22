#pragma once

#include <QDialog>
#include <QScrollArea>
#include <QSize>
#include <QString>
#include <QTextBrowser>
#include <QUrl>
#include <QVector>

#include <optional>
#include <tuple>

class QVBoxLayout;

namespace sli::toolkit {

class IconListWidget;

// -----------------------------------------------------------------------
// MarkdownHelpSection — frozen data record (mirrors Python @dataclass(frozen=True))
// -----------------------------------------------------------------------
struct MarkdownHelpSection {
  int order = 0;
  QString slug;
  QString title;
  QString bodyMd;
};

// -----------------------------------------------------------------------
// HTML stub helpers (mirrors Python free functions)
// -----------------------------------------------------------------------

/// Strip Pandoc-style {#id} suffix from a heading title.
QString stripHeadingAttrSuffix(const QString& text);

/// Slugify text for anchor use (NFKD → ASCII → [^a-zA-Z0-9]+ → "-").
QString slugifyAnchor(const QString& text);

/// Remove all HTML tags from a string.
QString stripHtmlTags(const QString& text);

/// Ensure every <h1..h6> heading has an id attribute. Missing ids are
/// generated from the heading text (slugified) with deduplication.
QString ensureHeadingIds(const QString& html, const QString& fallbackPrefix);

/// Build a TOC <nav> from <h3 id="..."> headings. Returns empty string
/// when fewer than two h3 items exist.
QString buildPageToc(const QString& html, const QString& title);

// -----------------------------------------------------------------------
// Help sections file helpers (from Python help_sections.py)
// -----------------------------------------------------------------------

/// Normalize a language code: "en", "ru", "zh", "pt_BR" are valid;
/// everything else maps to "en". Strips region suffix (e.g. "en_US" → "en").
QString normalizeHelpLanguage(const QString& language);

/// Return the "On this page" TOC title for a given language.
QString tocTitleForLanguage(const QString& language);

/// Extract the first heading (# Title) from raw markdown text as the title,
/// and return (title, body_without_title). If no heading found, derive title
/// from fallbackSlug.
std::tuple<QString, QString> extractMarkdownTitleAndBody(
    const QString& rawText, const QString& fallbackSlug);

/// Read *.md files matching `NNN_slug.md` from a directory and return
/// sorted MarkdownHelpSections.
QVector<MarkdownHelpSection> readMarkdownHelpSections(
    const QString& directoryPath);

// -----------------------------------------------------------------------
// MarkdownHelpPageBrowser — QTextBrowser configured for help content
// -----------------------------------------------------------------------
class MarkdownHelpPageBrowser : public QTextBrowser {
  Q_OBJECT

 public:
  explicit MarkdownHelpPageBrowser(QWidget* parent = nullptr);

  QSize sizeHint() const override;
  QSize minimumSizeHint() const override;

  /// Find the vertical pixel offset of a named anchor in the document.
  std::optional<int> anchorVerticalOffset(const QString& anchor) const;

 protected:
  void resizeEvent(QResizeEvent* event) override;
};

// -----------------------------------------------------------------------
// MarkdownHelpDialog — sidebar + content help dialog
// -----------------------------------------------------------------------
class MarkdownHelpDialog : public QDialog {
  Q_OBJECT

 public:
  explicit MarkdownHelpDialog(
      const QString& title = QStringLiteral("Help"),
      const QString& tocTitle = QStringLiteral("On this page"),
      const QVector<MarkdownHelpSection>& sections = {},
      QWidget* parent = nullptr);
  ~MarkdownHelpDialog() override;

  void setSections(const QVector<MarkdownHelpSection>& sections);
  void setSectionsFromDirectory(const QString& directory,
                                const QString& language = {});
  void setTocTitle(const QString& title);

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override;

 private:
  void setupUi();
  void changePage(int index);
  void syncPageWidth(MarkdownHelpPageBrowser* page);
  void onAnchorClicked(const QUrl& url);

  int findSectionIndex(const QString& slug) const;
  void navigateToHelpTarget(const QString& slug,
                            const QString& anchor = {});
  void scrollCurrentPageToAnchor(const QString& anchor);

  // Markdown processing
  QString normalizeMarkdownLists(const QString& mdText) const;
  QString fallbackPlainlistToHtml(const QString& mdText) const;
  QString renderSectionHtml(const MarkdownHelpSection& section) const;
  void applyStyles();

  struct InternalPage {
    MarkdownHelpPageBrowser* browser = nullptr;
  };

  IconListWidget* navWidget_ = nullptr;
  QScrollArea* scrollArea_ = nullptr;
  QVector<InternalPage> pages_;
  QVector<MarkdownHelpSection> sections_;
  QString tocTitleText_;
};

}  // namespace sli::toolkit
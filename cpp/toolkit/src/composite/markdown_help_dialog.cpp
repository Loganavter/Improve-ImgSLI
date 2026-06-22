#include "sli/toolkit/composite/markdown_help_dialog.h"

#include <QAbstractTextDocumentLayout>
#include <QDesktopServices>
#include <QDir>
#include <QEvent>
#include <QFile>
#include <QFileInfo>
#include <QFontMetrics>
#include <QHBoxLayout>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QScrollBar>
#include <QSizePolicy>
#include <QTextBlock>
#include <QTextDocument>
#include <QTextFragment>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <cstdint>

#include "sli/toolkit/composite/sidebar_nav_list.h"
#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// =====================================================================
// Free functions (HTML / markdown helpers)
// =====================================================================

QString stripHeadingAttrSuffix(const QString& text) {
  // Matches optional whitespace + {#id-suffix} at end
  static const QRegularExpression re(QStringLiteral(R"(\s*\{#[-a-zA-Z0-9_:.]+\}\s*$)"));
  QString result = text;
  result.replace(re, QString());
  return result.trimmed();
}

QString slugifyAnchor(const QString& text) {
  // NFKD normalize, strip non-ASCII, replace non-alphanum runs with "-"
  QString normalized = text.normalized(QString::NormalizationForm_KD);
  QString ascii;
  for (const QChar& c : normalized) {
    if (c.unicode() < 128)
      ascii += c;
  }
  static const QRegularExpression nonAlpha(QStringLiteral("[^a-zA-Z0-9]+"));
  QString slug = ascii;
  slug.replace(nonAlpha, QStringLiteral("-"));
  slug = slug.trimmed();
  // Remove leading/trailing '-' characters
  while (slug.startsWith(QLatin1Char('-'))) slug = slug.mid(1);
  while (slug.endsWith(QLatin1Char('-'))) slug.chop(1);
  return slug.toLower();
}

QString stripHtmlTags(const QString& text) {
  static const QRegularExpression tagRe(QStringLiteral("<[^>]+>"));
  QString result = text;
  result.replace(tagRe, QString());
  return result;
}

QString ensureHeadingIds(const QString& html, const QString& fallbackPrefix) {
  // Match <h1..h6 ...>...</h1..h6>
  static const QRegularExpression headingRe(
      QStringLiteral("<h(?P<level>[1-6])(?P<attrs>[^>]*)>(?P<text>.*?)</h\\k<level>>"),
      QRegularExpression::CaseInsensitiveOption | QRegularExpression::DotMatchesEverythingOption);
  static const QRegularExpression idRe(
      QStringLiteral(R"**(\sid\s*=\s*["'][^"']+["'])**"),
      QRegularExpression::CaseInsensitiveOption);

  QHash<QString, int> counters;
  int generatedIndex = 0;

  QString result;
  int lastEnd = 0;

  auto it = headingRe.globalMatch(html);
  while (it.hasNext()) {
    auto match = it.next();
    result += html.mid(lastEnd, match.capturedStart() - lastEnd);

    QString attrs = match.captured(QStringLiteral("attrs"));
    QString level = match.captured(QStringLiteral("level"));
    QString innerText = match.captured(QStringLiteral("text"));

    // If already has an id, keep it
    if (idRe.match(attrs).hasMatch()) {
      result += match.captured(0);
      lastEnd = match.capturedEnd();
      continue;
    }

    QString plainText = stripHtmlTags(innerText).trimmed();
    QString base = slugifyAnchor(plainText);
    if (base.isEmpty()) {
      base = QStringLiteral("%1-section-%2").arg(fallbackPrefix).arg(generatedIndex);
      ++generatedIndex;
    }

    int count = counters.value(base, 0);
    counters[base] = count + 1;
    QString anchorId = (count == 0) ? base : QStringLiteral("%1-%2").arg(base).arg(count + 1);

    result += QStringLiteral("<h%1%2 id=\"%3\">%4</h%5>")
                  .arg(level, attrs, anchorId, innerText, level);
    lastEnd = match.capturedEnd();
  }
  result += html.mid(lastEnd);
  return result;
}

QString buildPageToc(const QString& html, const QString& title) {
  // Match <h3 id="...">...</h3>
  static const QRegularExpression h3Re(
      QStringLiteral("<h3(?P<attrs>[^>]*)\\sid=\"(?P<id>[^\"]+)\"[^>]*>(?P<text>.*?)</h3>"),
      QRegularExpression::CaseInsensitiveOption | QRegularExpression::DotMatchesEverythingOption);

  struct TocItem {
    QString id;
    QString text;
  };
  QVector<TocItem> items;

  auto it = h3Re.globalMatch(html);
  while (it.hasNext()) {
    auto match = it.next();
    QString anchorId = match.captured(QStringLiteral("id")).trimmed();
    QString text = stripHtmlTags(match.captured(QStringLiteral("text"))).trimmed();
    if (!anchorId.isEmpty() && !text.isEmpty())
      items.append({anchorId, text});
  }

  if (items.size() < 2)
    return {};

  QString links;
  for (const auto& item : items) {
    links += QStringLiteral("<li><a href=\"#%1\">%2</a></li>").arg(item.id, item.text);
  }

  return QStringLiteral(
      "<nav class=\"help-toc\">"
      "<div class=\"help-toc-title\">%1</div>"
      "<ul>%2</ul>"
      "</nav>")
      .arg(title.toHtmlEscaped(), links);
}

// =====================================================================
// Help sections file helpers
// =====================================================================

static const QRegularExpression kSectionFilenameRe(
    QStringLiteral(R"(^(?P<order>\d{3})_(?P<slug>.+)\.md$)"));

QString normalizeHelpLanguage(const QString& language) {
  QString langNorm;
  try {
    langNorm = language.trimmed();
  } catch (...) {
    langNorm = QStringLiteral("en");
  }
  if (langNorm.isEmpty())
    langNorm = QStringLiteral("en");

  QString base = langNorm;
  if (base.contains(QLatin1Char('_')))
    base = base.split(QLatin1Char('_')).first().toLower();
  else
    base = base.toLower();

  if (base == QStringLiteral("pt"))
    return QStringLiteral("pt_BR");
  if (base.startsWith(QStringLiteral("zh")))
    return QStringLiteral("zh");
  if (base == QStringLiteral("ru") || base == QStringLiteral("en"))
    return base;
  return QStringLiteral("en");
}

QString tocTitleForLanguage(const QString& language) {
  QString lang = normalizeHelpLanguage(language);
  if (lang == QStringLiteral("ru"))
    return QStringLiteral("На этой странице");
  if (lang == QStringLiteral("pt_BR"))
    return QStringLiteral("Nesta pagina");
  if (lang == QStringLiteral("zh"))
    return QStringLiteral("本页内容");
  return QStringLiteral("On this page");
}

std::tuple<QString, QString> extractMarkdownTitleAndBody(
    const QString& rawText, const QString& fallbackSlug) {
  QStringList lines = rawText.split(QLatin1Char('\n'));
  int titleIndex = -1;
  QString title;

  for (int i = 0; i < lines.size(); ++i) {
    QString stripped = lines[i].trimmed();
    if (stripped.isEmpty()) continue;
    titleIndex = i;
    // Remove leading '#', trim, strip attr suffix
    QString afterHash = stripped;
    while (afterHash.startsWith(QLatin1Char('#')))
      afterHash = afterHash.mid(1);
    title = stripHeadingAttrSuffix(afterHash.trimmed());
    break;
  }

  if (title.isEmpty()) {
    title = fallbackSlug;
    title.replace(QLatin1Char('_'), QLatin1Char(' '));
    title.replace(QLatin1Char('-'), QLatin1Char(' '));
    title = title.trimmed();
    // Title-case each word
    QStringList words = title.split(QLatin1Char(' '));
    for (int i = 0; i < words.size(); ++i) {
      if (!words[i].isEmpty()) {
        words[i][0] = words[i][0].toUpper();
      }
    }
    title = words.join(QLatin1Char(' '));
  }

  QStringList bodyLines = lines;
  if (titleIndex >= 0) {
    bodyLines.removeAt(titleIndex);
    while (!bodyLines.isEmpty() && bodyLines.first().trimmed().isEmpty())
      bodyLines.removeFirst();
  }

  return {title, bodyLines.join(QLatin1Char('\n'))};
}

QVector<MarkdownHelpSection> readMarkdownHelpSections(
    const QString& directoryPath) {
  QDir dir(directoryPath);
  if (!dir.exists())
    return {};

  QVector<MarkdownHelpSection> sections;
  QStringList entries = dir.entryList(QDir::Files | QDir::Readable, QDir::Name);

  for (const QString& fileName : entries) {
    auto match = kSectionFilenameRe.match(fileName);
    if (!match.hasMatch())
      continue;

    QFile file(dir.absoluteFilePath(fileName));
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
      continue;

    QString rawText = QString::fromUtf8(file.readAll());
    file.close();

    QString slug = match.captured(QStringLiteral("slug"));
    auto [title, bodyMd] = extractMarkdownTitleAndBody(rawText, slug);

    sections.append(MarkdownHelpSection{
        .order = match.captured(QStringLiteral("order")).toInt(),
        .slug = slug,
        .title = title,
        .bodyMd = bodyMd});
  }

  std::sort(sections.begin(), sections.end(),
            [](const MarkdownHelpSection& a, const MarkdownHelpSection& b) {
              if (a.order != b.order) return a.order < b.order;
              return a.slug < b.slug;
            });

  return sections;
}

// =====================================================================
// MarkdownHelpPageBrowser
// =====================================================================

MarkdownHelpPageBrowser::MarkdownHelpPageBrowser(QWidget* parent)
    : QTextBrowser(parent) {
  setOpenLinks(false);
  setOpenExternalLinks(false);
  setFrameShape(QFrame::NoFrame);
  setReadOnly(true);
  setLineWrapMode(QTextBrowser::WidgetWidth);
  setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
  setStyleSheet(QStringLiteral("background: transparent; border: none;"));
  document()->setDocumentMargin(25);

  // Forward document size changes to update geometry
  connect(document()->documentLayout(), &QAbstractTextDocumentLayout::documentSizeChanged,
          this, [this] { updateGeometry(); });
}

QSize MarkdownHelpPageBrowser::sizeHint() const {
  int height = std::max(200, static_cast<int>(std::round(document()->size().height())) + 8);
  return QSize(400, height);
}

QSize MarkdownHelpPageBrowser::minimumSizeHint() const {
  return sizeHint();
}

void MarkdownHelpPageBrowser::resizeEvent(QResizeEvent* event) {
  QTextBrowser::resizeEvent(event);
  int viewportWidth = std::max(1, viewport()->width());
  double margin = document()->documentMargin() * 2.0;
  document()->setTextWidth(std::max(1.0, static_cast<double>(viewportWidth) - margin));
  updateGeometry();
}

std::optional<int> MarkdownHelpPageBrowser::anchorVerticalOffset(
    const QString& anchor) const {
  QString anc = anchor.trimmed();
  if (anc.isEmpty())
    return std::nullopt;

  auto* layout = document()->documentLayout();
  if (!layout)
    return std::nullopt;

  QTextBlock block = document()->begin();
  while (block.isValid()) {
    for (auto it = block.begin(); !it.atEnd(); ++it) {
      QTextFragment fragment = it.fragment();
      if (fragment.isValid()) {
        QTextCharFormat fmt = fragment.charFormat();
        if (fmt.isAnchor()) {
          for (const QString& name : fmt.anchorNames()) {
            if (name == anc) {
              QRectF r = layout->blockBoundingRect(block);
              return std::max(0, static_cast<int>(std::round(r.top())));
            }
          }
        }
      }
    }
    block = block.next();
  }
  return std::nullopt;
}

// =====================================================================
// MarkdownHelpDialog
// =====================================================================

MarkdownHelpDialog::MarkdownHelpDialog(
    const QString& title,
    const QString& tocTitle,
    const QVector<MarkdownHelpSection>& sections,
    QWidget* parent)
    : QDialog(parent),
      sections_(sections),
      tocTitleText_(tocTitle) {
  setObjectName(QStringLiteral("MarkdownHelpDialog"));
  setWindowTitle(title);
  setWindowFlags(Qt::Window | Qt::WindowTitleHint | Qt::WindowCloseButtonHint);
  setSizeGripEnabled(true);
  resize(800, 600);

  setupUi();
  setSections(sections_);
  applyStyles();

  // Re-apply styles on theme change
  Theme::onThemeChanged(this, [this] { applyStyles(); });
}

MarkdownHelpDialog::~MarkdownHelpDialog() = default;

void MarkdownHelpDialog::setupUi() {
  auto* mainLayout = new QHBoxLayout(this);
  mainLayout->setContentsMargins(0, 0, 0, 0);
  mainLayout->setSpacing(0);

  // Sidebar side
  auto* sidebarContainer = new QWidget(this);
  auto* sidebarVBox = new QVBoxLayout(sidebarContainer);
  sidebarVBox->setContentsMargins(0, 0, 0, 0);
  sidebarVBox->setSpacing(0);

  navWidget_ = new IconListWidget(sidebarContainer);
  navWidget_->enableMinimalScrollbar();
  sidebarVBox->addWidget(navWidget_);

  // Content area
  scrollArea_ = new QScrollArea(this);
  scrollArea_->setFrameShape(QFrame::NoFrame);
  scrollArea_->setWidgetResizable(true);
  scrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  scrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  scrollArea_->setVerticalScrollBar(new unified_flyout::MinimalistScrollBar());
  scrollArea_->setHorizontalScrollBar(new unified_flyout::MinimalistScrollBar());
  scrollArea_->viewport()->installEventFilter(this);

  mainLayout->addWidget(sidebarContainer);
  mainLayout->addWidget(scrollArea_, 1);

  connect(navWidget_, &IconListWidget::currentRowChanged,
          this, &MarkdownHelpDialog::changePage);
}

void MarkdownHelpDialog::setTocTitle(const QString& title) {
  tocTitleText_ = title;
  applyStyles();
}

void MarkdownHelpDialog::setSectionsFromDirectory(
    const QString& directory, const QString& language) {
  auto sections = readMarkdownHelpSections(directory);
  setSections(sections);
  if (!language.isEmpty())
    setTocTitle(tocTitleForLanguage(language));
}

void MarkdownHelpDialog::setSections(
    const QVector<MarkdownHelpSection>& sections) {
  // Sort by (order, slug)
  sections_ = sections;
  std::sort(sections_.begin(), sections_.end(),
            [](const MarkdownHelpSection& a, const MarkdownHelpSection& b) {
              if (a.order != b.order) return a.order < b.order;
              return a.slug < b.slug;
            });

  navWidget_->clear();

  // Remove old scroll area widget
  QWidget* old = scrollArea_->takeWidget();
  if (old) old->deleteLater();

  // Clear existing pages
  for (auto& page : pages_) {
    if (page.browser) page.browser->deleteLater();
  }
  pages_.clear();

  // Build new nav + content pages
  for (const auto& section : sections_) {
    int idx = navWidget_->addItem(section.title);
    navWidget_->setItemSizeHint(idx, QSize(0, 35));

    auto* page = new MarkdownHelpPageBrowser();
    connect(page, &QTextBrowser::anchorClicked,
            this, &MarkdownHelpDialog::onAnchorClicked);
    pages_.append({page});
  }

  if (navWidget_->count() > 0)
    navWidget_->setCurrentRow(0);

  // Update nav width
  int maxTextWidth = 0;
  QFontMetrics metrics(navWidget_->font());
  for (int i = 0; i < navWidget_->count(); ++i) {
    maxTextWidth = std::max(maxTextWidth,
                            metrics.horizontalAdvance(navWidget_->itemText(i)));
  }
  navWidget_->setMinimumWidth(maxTextWidth + 32);

  applyStyles();
}

void MarkdownHelpDialog::changePage(int index) {
  if (index < 0 || index >= pages_.size())
    return;

  QWidget* oldWidget = scrollArea_->takeWidget();
  if (oldWidget) {
    oldWidget->hide();
    oldWidget->setParent(nullptr);
  }

  MarkdownHelpPageBrowser* page = pages_[index].browser;
  scrollArea_->setWidget(page);
  syncPageWidth(page);
  page->show();
  page->adjustSize();
  scrollArea_->verticalScrollBar()->setValue(0);
}

void MarkdownHelpDialog::syncPageWidth(MarkdownHelpPageBrowser* page) {
  if (!page) return;

  int viewportWidth = std::max(1, scrollArea_->viewport()->width());
  page->resize(viewportWidth, page->height());
  double margin = page->document()->documentMargin() * 2.0;
  page->document()->setTextWidth(std::max(1.0, static_cast<double>(viewportWidth) - margin));
  page->updateGeometry();
  page->adjustSize();
}

bool MarkdownHelpDialog::eventFilter(QObject* watched, QEvent* event) {
  if (watched == scrollArea_->viewport() && event->type() == QEvent::Resize) {
    auto* current = qobject_cast<MarkdownHelpPageBrowser*>(scrollArea_->widget());
    if (current)
      syncPageWidth(current);
  }
  return QDialog::eventFilter(watched, event);
}

int MarkdownHelpDialog::findSectionIndex(const QString& slug) const {
  for (int i = 0; i < sections_.size(); ++i) {
    if (sections_[i].slug == slug)
      return i;
  }
  return -1;
}

void MarkdownHelpDialog::navigateToHelpTarget(
    const QString& slug, const QString& anchor) {
  int index = findSectionIndex(slug);
  if (index < 0) return;
  navWidget_->setCurrentRow(index);
  if (!anchor.isEmpty())
    scrollCurrentPageToAnchor(anchor);
}

void MarkdownHelpDialog::scrollCurrentPageToAnchor(const QString& anchor) {
  int current = navWidget_->currentRow();
  if (current < 0 || current >= pages_.size()) return;

  auto* page = pages_[current].browser;
  auto y = page->anchorVerticalOffset(anchor);
  if (y.has_value())
    scrollArea_->verticalScrollBar()->setValue(*y);
}

void MarkdownHelpDialog::onAnchorClicked(const QUrl& url) {
  if (url.isRelative()) {
    QString anchor = url.fragment().trimmed();
    if (!anchor.isEmpty())
      scrollCurrentPageToAnchor(anchor);
    return;
  }

  QString scheme = url.scheme().toLower();
  if (scheme == QStringLiteral("http") || scheme == QStringLiteral("https")) {
    QDesktopServices::openUrl(url);
    return;
  }

  if (scheme == QStringLiteral("help")) {
    QString slug = url.host().trimmed();
    if (slug.isEmpty())
      slug = url.path().trimmed();
    // Remove leading '/'
    while (slug.startsWith(QLatin1Char('/'))) slug = slug.mid(1);
    if (!slug.isEmpty())
      navigateToHelpTarget(slug, url.fragment().trimmed());
  }
}

// -----------------------------------------------------------------------
// Markdown processing
// -----------------------------------------------------------------------

QString MarkdownHelpDialog::normalizeMarkdownLists(const QString& mdText) const {
  QStringList lines = mdText.split(QLatin1Char('\n'));
  QStringList out;

  for (const QString& line : lines) {
    QString stripped = line.trimmed();
    bool isListItem =
        stripped.startsWith(QStringLiteral("- ")) ||
        stripped.startsWith(QStringLiteral("* ")) ||
        stripped.startsWith(QStringLiteral("+ ")) ||
        (stripped.size() > 2 &&
         stripped[0].isDigit() &&
         stripped.mid(1, 2) == QStringLiteral(". "));

    bool prevIsList = false;
    if (!out.isEmpty()) {
      QString prevStripped = out.last().trimmed();
      prevIsList =
          prevStripped.startsWith(QStringLiteral("- ")) ||
          prevStripped.startsWith(QStringLiteral("* ")) ||
          prevStripped.startsWith(QStringLiteral("+ ")) ||
          (prevStripped.size() > 2 &&
           prevStripped[0].isDigit() &&
           prevStripped.mid(1, 2) == QStringLiteral(". "));
    }

    if (isListItem && !out.isEmpty() && !out.last().trimmed().isEmpty() && !prevIsList)
      out.append(QString());

    out.append(line);
  }
  return out.join(QLatin1Char('\n'));
}

bool isBullet(const QString& s) {
  QString st = s.trimmed();
  if (st.startsWith(QStringLiteral("- ")) ||
      st.startsWith(QStringLiteral("* ")) ||
      st.startsWith(QStringLiteral("+ ")))
    return true;
  int i = 0;
  while (i < st.size() && st[i].isDigit())
    ++i;
  return (i > 0 && i + 1 < st.size() && st[i] == QLatin1Char('.') && st[i + 1] == QLatin1Char(' '));
}

QString MarkdownHelpDialog::fallbackPlainlistToHtml(const QString& mdText) const {
  QStringList htmlParts;
  bool inList = false;
  QString listTag = QStringLiteral("ul");

  const auto lines = mdText.split(QLatin1Char('\n'));
  for (const QString& rawLine : lines) {
    QString line = rawLine.trimmed();
    if (isBullet(line)) {
      QString s = line.trimmed();
      int i = 0;
      while (i < s.size() && s[i].isDigit())
        ++i;
      bool isOrdered = (i > 0 && i + 1 < s.size() && s[i] == QLatin1Char('.') && s[i + 1] == QLatin1Char(' '));
      QString desiredTag = isOrdered ? QStringLiteral("ol") : QStringLiteral("ul");
      if (!inList || listTag != desiredTag) {
        if (inList)
          htmlParts.append(QStringLiteral("</%1>").arg(listTag));
        listTag = desiredTag;
        inList = true;
        htmlParts.append(QStringLiteral("<%1>").arg(listTag));
      }
      QString content = (listTag == QStringLiteral("ul"))
                            ? s.mid(2)
                            : s.mid(i + 2);
      htmlParts.append(QStringLiteral("<li>%1</li>").arg(content.toHtmlEscaped()));
    } else {
      if (inList) {
        htmlParts.append(QStringLiteral("</%1>").arg(listTag));
        inList = false;
      }
      if (line.trimmed().isEmpty())
        htmlParts.append(QString());
      else
        htmlParts.append(QStringLiteral("<p>%1</p>").arg(line.toHtmlEscaped()));
    }
  }
  if (inList)
    htmlParts.append(QStringLiteral("</%1>").arg(listTag));

  return htmlParts.join(QLatin1Char('\n'));
}

QString MarkdownHelpDialog::renderSectionHtml(
    const MarkdownHelpSection& section) const {
  QString mdText = normalizeMarkdownLists(section.bodyMd);

  // Convert markdown to HTML using Qt's QTextDocument
  QTextDocument tempDoc;
  tempDoc.setMarkdown(mdText);
  QString htmlContent = tempDoc.toHtml();

  // Detect if list conversion failed — if no <ul>/<ol> tags found and
  // plain list markers exist, use fallback
  bool hasListTags = htmlContent.contains(QStringLiteral("<ul")) ||
                     htmlContent.contains(QStringLiteral("<ol"));
  if (!hasListTags) {
    bool hasMarkers = false;
    const auto mdLines = mdText.split(QLatin1Char('\n'));
    for (const QString& l : mdLines) {
      QString st = l.trimmed();
      if (st.startsWith(QStringLiteral("- ")) ||
          st.startsWith(QStringLiteral("* ")) ||
          st.startsWith(QStringLiteral("+ ")) ||
          (st.size() > 1 && st[0].isDigit() && st.mid(1, 2) == QStringLiteral(". "))) {
        hasMarkers = true;
        break;
      }
    }
    if (hasMarkers)
      htmlContent = fallbackPlainlistToHtml(mdText);
  }

  htmlContent = ensureHeadingIds(htmlContent, section.slug);
  QString tocHtml = buildPageToc(htmlContent, tocTitleText_);
  return tocHtml + htmlContent;
}

void MarkdownHelpDialog::applyStyles() {
  // Use Theme tokens
  QColor textColor = Theme::getColor(QStringLiteral("dialog.text"));
  QColor separatorColor = Theme::getColor(QStringLiteral("help.separator"));
  QColor dialogBgColor = Theme::getColor(QStringLiteral("dialog.background"));
  QColor accentColor = Theme::getColor(QStringLiteral("accent"));

  // Helper lambdas
  auto hexToRgb = [](const QString& h) -> std::tuple<int, int, int> {
    QString hex = h;
    if (hex.startsWith(QLatin1Char('#')))
      hex = hex.mid(1);
    if (hex.size() == 8)
      hex = hex.mid(2);
    bool ok1, ok2, ok3;
    int r = hex.mid(0, 2).toInt(&ok1, 16);
    int g = hex.mid(2, 2).toInt(&ok2, 16);
    int b = hex.mid(4, 2).toInt(&ok3, 16);
    if (!ok1 || !ok2 || !ok3)
      return {0, 0, 0};
    return {r, g, b};
  };

  auto rgbToHex = [](int r, int g, int b) -> QString {
    r = std::clamp(r, 0, 255);
    g = std::clamp(g, 0, 255);
    b = std::clamp(b, 0, 255);
    return QStringLiteral("#%1%2%3")
        .arg(r, 2, 16, QLatin1Char('0'))
        .arg(g, 2, 16, QLatin1Char('0'))
        .arg(b, 2, 16, QLatin1Char('0'))
        .toUpper();
  };

  auto luminance = [](int r, int g, int b) -> double {
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };

  auto shade = [](int r, int g, int b, double amount) -> std::tuple<int, int, int> {
    double nr, ng, nb;
    if (amount >= 0) {
      nr = r + (255.0 - r) * amount;
      ng = g + (255.0 - g) * amount;
      nb = b + (255.0 - b) * amount;
    } else {
      nr = r * (1.0 + amount);
      ng = g * (1.0 + amount);
      nb = b * (1.0 + amount);
    }
    return {static_cast<int>(std::round(nr)),
            static_cast<int>(std::round(ng)),
            static_cast<int>(std::round(nb))};
  };

  auto [bgR, bgG, bgB] = hexToRgb(dialogBgColor.name());
  double bgLum = luminance(bgR, bgG, bgB);

  auto [codeBgR, codeBgG, codeBgB] = shade(bgR, bgG, bgB, (bgLum > 128) ? -0.08 : 0.12);
  auto [codeBorderR, codeBorderG, codeBorderB] = shade(bgR, bgG, bgB, (bgLum > 128) ? -0.18 : 0.18);
  QString codeBg = rgbToHex(codeBgR, codeBgG, codeBgB);
  QString codeBorder = rgbToHex(codeBorderR, codeBorderG, codeBorderB);
  QString textName = textColor.name();
  QString sepName = separatorColor.name();
  QString accentName = accentColor.name();

  QString wrapper = QStringLiteral(
      "<style>"
      "  body { font-size: 14px; color: %1; }"
      "  h2 { margin-bottom: 8px; border-bottom: 1px solid %2; padding-bottom: 4px; }"
      "  h3 { margin: 12px 0 6px 0; }"
      "  ul, ol { margin: 8px 0; padding-left: 24px; }"
      "  li { margin: 0 0 6px 0; display: list-item; }"
      "  p { overflow-wrap: anywhere; word-break: normal; }"
      "  b, strong { color: %1; }"
      "  code { background-color: %3; color: %1; padding: 2px 4px; border-radius: 4px; border: 1px solid %4; }"
      "  pre { background-color: %3; color: %1; padding: 10px 12px; border-radius: 6px; white-space: pre-wrap; border: 1px solid %4; }"
      "  pre code { background-color: transparent; color: %1; padding: 0; border: none; }"
      "  kbd { background-color: %3; color: %1; padding: 2px 6px; border-radius: 4px; border: 1px solid %4; font-family: inherit; }"
      "  a { color: %5; text-decoration: none; }"
      "  .help-toc { margin: 0 0 16px 0; padding: 10px 14px; border: 1px solid %2; border-radius: 8px; }"
      "  .help-toc-title { font-weight: 600; margin-bottom: 6px; }"
      "  .help-toc ul { margin: 0; padding-left: 18px; }"
      "  .help-toc li { margin-bottom: 4px; }"
      "</style>")
      .arg(textName, sepName, codeBg, codeBorder, accentName);

  // Set HTML on each page
  for (int i = 0; i < pages_.size() && i < sections_.size(); ++i) {
    MarkdownHelpPageBrowser* page = pages_[i].browser;
    if (page)
      page->setHtml(wrapper + renderSectionHtml(sections_[i]));
  }
}

}  // namespace sli::toolkit
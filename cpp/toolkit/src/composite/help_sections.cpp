#include "sli/toolkit/composite/help_sections.h"

#include <QDir>
#include <QFile>
#include <QRegularExpression>
#include <QTextStream>

namespace sli::toolkit {

namespace {

// Strip trailing {#anchor-id} attribute suffix from a heading line.
// Mirrors Python's strip_heading_attr_suffix.
QString stripHeadingAttrSuffix(const QString& text) {
  static const QRegularExpression re(
      QStringLiteral(R"(\s*\{#[-a-zA-Z0-9_:.]+\}\s*$)"));
  QString result = text;
  result.remove(re);
  return result.trimmed();
}

// Match filename pattern  NNN_slug.md
QRegularExpression sectionFilenameRe() {
  return QRegularExpression(
      QStringLiteral(R"(^(?<order>\d{3})_(?<slug>.+)\.md$)"));
}

}  // anonymous namespace

// ---------------------------------------------------------------------------
// normalizeHelpLanguage
// ---------------------------------------------------------------------------

QString normalizeHelpLanguage(const QString& language) {
  QString langNorm;
  try {
    langNorm = (language.isEmpty() ? QStringLiteral("en") : language).trimmed();
  } catch (...) {
    langNorm = QStringLiteral("en");
  }
  QString base = langNorm;
  int underscoreIdx = langNorm.indexOf(QLatin1Char('_'));
  if (underscoreIdx >= 0) {
    base = langNorm.left(underscoreIdx).toLower();
  } else {
    base = langNorm.toLower();
  }
  if (base == QStringLiteral("pt")) return QStringLiteral("pt_BR");
  if (base.startsWith(QStringLiteral("zh"))) return QStringLiteral("zh");
  if (base == QStringLiteral("ru") || base == QStringLiteral("en"))
    return base;
  return QStringLiteral("en");
}

// ---------------------------------------------------------------------------
// tocTitleForLanguage
// ---------------------------------------------------------------------------

QString tocTitleForLanguage(const QString& language) {
  const QString lang = normalizeHelpLanguage(language);
  if (lang == QStringLiteral("ru"))
    return QStringLiteral("На этой странице");
  if (lang == QStringLiteral("pt_BR"))
    return QStringLiteral("Nesta pagina");
  if (lang == QStringLiteral("zh"))
    return QStringLiteral("本页内容");
  return QStringLiteral("On this page");
}

// ---------------------------------------------------------------------------
// extractMarkdownTitleAndBody
// ---------------------------------------------------------------------------

std::tuple<QString, QString> extractMarkdownTitleAndBody(
    const QString& rawText, const QString& fallbackSlug) {
  const QStringList lines = rawText.split(QLatin1Char('\n'));
  int titleIndex = -1;
  QString title;

  for (int idx = 0; idx < lines.size(); ++idx) {
    const QString stripped = lines[idx].trimmed();
    if (stripped.isEmpty()) continue;
    titleIndex = idx;
    QString withoutHash = stripped;
    withoutHash.remove(QRegularExpression(QStringLiteral("^#+")));
    title = stripHeadingAttrSuffix(withoutHash);
    break;
  }

  if (title.isEmpty()) {
    QString slug = fallbackSlug;
    title = slug.replace(QLatin1Char('_'), QLatin1Char(' '))
                .replace(QLatin1Char('-'), QLatin1Char(' '))
                .trimmed();
    if (!title.isEmpty()) {
      // Simple title-case: uppercase first letter of each word
      QStringList words = title.split(QLatin1Char(' '));
      for (auto& w : words) {
        if (!w.isEmpty()) w[0] = w[0].toUpper();
      }
      title = words.join(QLatin1Char(' '));
    }
  }

  QStringList bodyLines = lines;
  if (titleIndex >= 0) {
    bodyLines.removeAt(titleIndex);
    while (!bodyLines.isEmpty() && bodyLines.first().trimmed().isEmpty()) {
      bodyLines.removeFirst();
    }
  }

  return std::make_tuple(title, bodyLines.join(QLatin1Char('\n')));
}

// ---------------------------------------------------------------------------
// readMarkdownHelpSections
// ---------------------------------------------------------------------------

QVector<MarkdownHelpSection> readMarkdownHelpSections(
    const QString& directory) {
  QDir dir(directory);
  if (!dir.exists()) return {};

  const QRegularExpression re = sectionFilenameRe();
  QVector<MarkdownHelpSection> sections;

  const QFileInfoList entries =
      dir.entryInfoList(QDir::Files | QDir::Readable, QDir::Name);
  for (const QFileInfo& info : entries) {
    const QRegularExpressionMatch match = re.match(info.fileName());
    if (!match.hasMatch()) continue;

    QFile file(info.absoluteFilePath());
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) continue;

    QTextStream stream(&file);
    stream.setEncoding(QStringConverter::Utf8);
    const QString rawText = stream.readAll();
    file.close();

    auto [title, bodyMd] =
        extractMarkdownTitleAndBody(rawText, match.captured(QStringLiteral("slug")));

    sections.append(MarkdownHelpSection{
        .order = match.captured(QStringLiteral("order")).toInt(),
        .slug = match.captured(QStringLiteral("slug")),
        .title = title,
        .body_md = bodyMd,
    });
  }

  std::sort(sections.begin(), sections.end(),
            [](const MarkdownHelpSection& a, const MarkdownHelpSection& b) {
              return std::tie(a.order, a.slug) < std::tie(b.order, b.slug);
            });
  return sections;
}

}  // namespace sli::toolkit
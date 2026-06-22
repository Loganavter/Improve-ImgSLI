#pragma once

#include <QString>
#include <QStringList>
#include <QVector>

#include <tuple>

namespace sli::toolkit {

/// Lightweight data struct mirroring Python's MarkdownHelpSection dataclass.
struct MarkdownHelpSection {
  int order = 0;
  QString slug;
  QString title;
  QString body_md;
};

/// Normalize a language code (e.g. "en_US" -> "en", "pt-BR" -> "pt_BR").
/// Mirrors Python's normalize_help_language.
QString normalizeHelpLanguage(const QString& language);

/// Localised "On this page" title for the given language.
/// Mirrors Python's toc_title_for_language.
QString tocTitleForLanguage(const QString& language);

/// Extract the first heading as title and the remaining body from raw
/// markdown text.  Mirrors Python's extract_markdown_title_and_body.
std::tuple<QString, QString> extractMarkdownTitleAndBody(
    const QString& rawText, const QString& fallbackSlug);

/// Read all numbered `NNN_slug.md` files from a directory and return
/// sorted MarkdownHelpSection entries.  Mirrors Python's
/// read_markdown_help_sections.
QVector<MarkdownHelpSection> readMarkdownHelpSections(
    const QString& directory);

}  // namespace sli::toolkit
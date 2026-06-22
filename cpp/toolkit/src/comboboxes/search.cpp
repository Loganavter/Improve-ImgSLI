#include "sli/toolkit/comboboxes/search.h"

#include <QChar>
#include <QStringList>

#include <algorithm>

namespace sli::toolkit::comboboxes {

QString normalizeForSearch(const QString& text) {
  // QString::normalized(NormalizationForm_KD) approximates NFKD; we then drop
  // combining marks (categoryMark*) and casefold.
  const QString nfkd = text.normalized(QString::NormalizationForm_KD).toCaseFolded();
  QString stripped;
  stripped.reserve(nfkd.size());
  for (const QChar& ch : nfkd) {
    if (!ch.isMark()) {
      stripped.append(ch);
    }
  }
  // Collapse whitespace.
  return stripped.split(QChar::Space, Qt::SkipEmptyParts).join(QChar::Space);
}

std::optional<int> matchScoreNormalized(const QString& normQuery,
                                         const QString& normText) {
  if (normQuery.isEmpty()) {
    return 0;
  }
  if (normText.isEmpty()) {
    return std::nullopt;
  }
  if (normText.startsWith(normQuery)) {
    return 0;
  }
  const auto words = normText.split(QChar::Space, Qt::SkipEmptyParts);
  for (int i = 0; i < words.size(); ++i) {
    if (words[i].startsWith(normQuery)) {
      return 10 + i;
    }
  }
  const int substringPos = normText.indexOf(normQuery);
  if (substringPos >= 0) {
    return 40 + substringPos;
  }
  int queryPos = 0;
  int firstMatch = -1;
  int lastMatch = -1;
  for (int i = 0; i < normText.size(); ++i) {
    if (queryPos < normQuery.size() && normText[i] == normQuery[queryPos]) {
      if (firstMatch < 0) {
        firstMatch = i;
      }
      lastMatch = i;
      ++queryPos;
      if (queryPos == normQuery.size()) {
        const int gap = std::max(
            0, static_cast<int>(lastMatch - firstMatch - normQuery.size() + 1));
        return 100 + firstMatch + gap;
      }
    }
  }
  return std::nullopt;
}

std::optional<int> matchScore(const QString& query, const QString& text) {
  return matchScoreNormalized(normalizeForSearch(query),
                               normalizeForSearch(text));
}

std::vector<int> visibleIndices(const std::vector<QString>& normalizedItems,
                                 bool searchEnabled,
                                 const QString& searchText) {
  if (!searchEnabled || searchText.isEmpty()) {
    std::vector<int> all;
    all.reserve(normalizedItems.size());
    for (int i = 0; i < static_cast<int>(normalizedItems.size()); ++i) {
      all.push_back(i);
    }
    return all;
  }
  const QString normQuery = normalizeForSearch(searchText);
  std::vector<std::pair<int, int>> matches;
  for (int i = 0; i < static_cast<int>(normalizedItems.size()); ++i) {
    if (auto score = matchScoreNormalized(normQuery, normalizedItems[i]);
        score.has_value()) {
      matches.emplace_back(*score, i);
    }
  }
  std::sort(matches.begin(), matches.end());
  std::vector<int> out;
  out.reserve(matches.size());
  for (const auto& [_score, idx] : matches) {
    out.push_back(idx);
  }
  return out;
}

}  // namespace sli::toolkit::comboboxes

#pragma once

#include <QString>

#include <optional>
#include <vector>

namespace sli::toolkit::comboboxes {

QString normalizeForSearch(const QString& text);
std::optional<int> matchScore(const QString& query, const QString& text);
std::optional<int> matchScoreNormalized(const QString& normQuery,
                                         const QString& normText);

std::vector<int> visibleIndices(const std::vector<QString>& normalizedItems,
                                bool searchEnabled, const QString& searchText);

}  // namespace sli::toolkit::comboboxes

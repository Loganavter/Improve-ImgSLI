from __future__ import annotations

import unicodedata

def normalize_for_search(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text)).casefold()
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_marks.split())

def match_score(query: str, text: str) -> int | None:
    norm_query = normalize_for_search(query)
    norm_text = normalize_for_search(text)
    return match_score_normalized(norm_query, norm_text)

def match_score_normalized(norm_query: str, norm_text: str) -> int | None:
    if not norm_query:
        return 0
    if not norm_text:
        return None
    if norm_text.startswith(norm_query):
        return 0

    for word_index, word in enumerate(norm_text.split()):
        if word.startswith(norm_query):
            return 10 + word_index

    substring_pos = norm_text.find(norm_query)
    if substring_pos >= 0:
        return 40 + substring_pos

    query_pos = 0
    first_match = -1
    last_match = -1
    for text_index, char in enumerate(norm_text):
        if query_pos < len(norm_query) and char == norm_query[query_pos]:
            if first_match < 0:
                first_match = text_index
            last_match = text_index
            query_pos += 1
            if query_pos == len(norm_query):
                gap_penalty = max(0, last_match - first_match - len(norm_query) + 1)
                return 100 + first_match + gap_penalty
    return None

def visible_indices(
    items: list[object],
    *,
    search_enabled: bool,
    search_text: str,
) -> list[int]:
    if not search_enabled or not search_text:
        return list(range(len(items)))

    matches: list[tuple[int, int]] = []
    for idx, item in enumerate(items):
        score = match_score(search_text, getattr(item, "text", ""))
        if score is not None:
            matches.append((score, idx))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [idx for _score, idx in matches]

def visible_indices_normalized(
    normalized_items: list[str],
    *,
    search_enabled: bool,
    search_text: str,
) -> list[int]:
    if not search_enabled or not search_text:
        return list(range(len(normalized_items)))

    norm_query = normalize_for_search(search_text)
    matches: list[tuple[int, int]] = []
    for idx, norm_text in enumerate(normalized_items):
        score = match_score_normalized(norm_query, norm_text)
        if score is not None:
            matches.append((score, idx))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [idx for _score, idx in matches]

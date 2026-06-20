//! Playlist index math.
//!
//! Mirrors the tricky parts of
//! `src/services/workflow/playlist_components/list_operations.py`:
//! - `remove_at` returns the new current index after removing `index`
//!   from a list whose current pointer is `current`.
//! - `reorder` returns the new current index after moving `source` to
//!   `dest` within a single list.
//! - `resolve_after_cross_move` reproduces
//!   `_resolve_current_index_after_cross_move` for the cross-list drop
//!   case where the watcher tracks a previous path.
//!
//! Pure functions, fully testable, with the same edge cases as the
//! Python source.

/// New current index after removing `removed_at` from a list of length
/// `len_before_remove`, given the previous `current` index. Returns -1
/// when the list becomes empty or the removal index is out of range.
pub fn remove_at(len_before_remove: i32, current: i32, removed_at: i32) -> i32 {
    if removed_at < 0 || removed_at >= len_before_remove {
        return current;
    }
    let len_after = len_before_remove - 1;
    if len_after <= 0 {
        return -1;
    }
    if removed_at < current {
        current - 1
    } else if removed_at == current {
        removed_at.min(len_after - 1)
    } else {
        current
    }
}

/// New current index after moving `source` to `dest` within a single
/// list. Mirrors `reorder_item_in_list`.
pub fn reorder(current: i32, source: i32, mut dest: i32) -> i32 {
    if source < dest {
        dest -= 1;
    }
    if current == source {
        dest
    } else if source < current && dest >= current {
        current - 1
    } else if source > current && dest <= current {
        current + 1
    } else {
        current
    }
}

/// Cross-list move resolver. Reproduces
/// `_resolve_current_index_after_cross_move`. `previous_path_match` is
/// the index of the previously-tracked path inside the target list
/// after the move, or -1 when not present. `target_len_after_move` is
/// the length of the target list after both the pop and the insert.
pub fn resolve_after_cross_move(
    previous_path_match: i32,
    target_len_after_move: i32,
    same_list_and_was_current: bool,
    source_index: i32,
) -> i32 {
    if previous_path_match >= 0 {
        return previous_path_match;
    }
    if target_len_after_move <= 0 {
        return -1;
    }
    if same_list_and_was_current {
        return source_index.min(target_len_after_move - 1);
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn remove_before_current_shifts_left() {
        assert_eq!(remove_at(5, 3, 1), 2);
    }

    #[test]
    fn remove_after_current_unchanged() {
        assert_eq!(remove_at(5, 1, 3), 1);
    }

    #[test]
    fn remove_at_current_clamps_to_end() {
        // Removing the last (current=4) from a list of 5
        assert_eq!(remove_at(5, 4, 4), 3);
        // Removing the only element
        assert_eq!(remove_at(1, 0, 0), -1);
    }

    #[test]
    fn remove_out_of_range_is_noop() {
        assert_eq!(remove_at(3, 1, 9), 1);
        assert_eq!(remove_at(3, 1, -1), 1);
    }

    #[test]
    fn reorder_current_item_follows_dest() {
        // Move current=2 to dest=4 in a list of 5 — after the
        // `source < dest -= 1` adjustment, lands at 3
        assert_eq!(reorder(2, 2, 4), 3);
        // Move current=2 to dest=0
        assert_eq!(reorder(2, 2, 0), 0);
    }

    #[test]
    fn reorder_source_before_current_pulled_past_current() {
        // current=3, source=1, dest=5 → dest becomes 4 (since src<dest)
        // src<curr<=dest → curr-1
        assert_eq!(reorder(3, 1, 5), 2);
    }

    #[test]
    fn reorder_source_after_current_pushed_back() {
        // current=2, source=4, dest=1 → src>curr>=dest → curr+1
        assert_eq!(reorder(2, 4, 1), 3);
    }

    #[test]
    fn reorder_no_overlap_keeps_current() {
        assert_eq!(reorder(2, 5, 7), 2);
    }

    #[test]
    fn cross_move_prefers_previous_path() {
        assert_eq!(resolve_after_cross_move(4, 10, false, 0), 4);
    }

    #[test]
    fn cross_move_empty_returns_minus_one() {
        assert_eq!(resolve_after_cross_move(-1, 0, false, 0), -1);
    }

    #[test]
    fn cross_move_same_list_current_clamps_to_end() {
        // source list, was-current item was popped — clamp to end.
        assert_eq!(resolve_after_cross_move(-1, 3, true, 5), 2);
        assert_eq!(resolve_after_cross_move(-1, 4, true, 1), 1);
    }

    #[test]
    fn cross_move_other_list_defaults_to_zero() {
        assert_eq!(resolve_after_cross_move(-1, 4, false, 0), 0);
    }
}

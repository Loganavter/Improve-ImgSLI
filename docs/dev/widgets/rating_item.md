# RatingListItem

App-owned rating list row with +/- buttons, wheel-rating, drag & drop and
touch gestures — moved out of `sli-ui-toolkit` because rating is
Improve-ImgSLI domain UI. Builds rows for the toolkit `ListPanel` via
`make_rating_row_factory`.

Source: `src/ui/widgets/rating_item.py`

## Construction

`Button`-family row; see `make_rating_row_factory` for the row factory the
picklists use. State read from `index`, `full_path`, `list_num`,
`image_number`, `item_type`, `position`, `is_current`, `is_selected`.

## Inspection

Family `RatingListItem`; state: `index`, `full_path`, `list_num`,
`image_number`, `item_type`, `position`, `is_current`, `is_selected`;
token family `list_item.background.*`; regions and layers enabled
(Button-family extras).

Used by: `unified_list_picker` (double-list rating picker).

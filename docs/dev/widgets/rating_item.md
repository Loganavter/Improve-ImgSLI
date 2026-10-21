# RatingListItem

App-owned rating list row with +/- buttons, wheel-rating, drag & drop and
touch gestures — moved out of `sli-ui-toolkit` because rating is
Improve-ImgSLI domain UI. Builds rows for the toolkit `ListPanel` via
`make_rating_row_factory`.

Source: `src/ui/widgets/rating_item.py`

## Construction

```python
RatingListItem(
    index, text, rating, full_path,      # required, positional
    list_num=None,                       # required in effect: one of
    image_number=None,                   #   list_num / image_number (TypeError otherwise)
    get_rating=None, increment_rating=None, decrement_rating=None,
    create_rating_gesture=None,
    on_update_drop_indicator=None, on_clear_drop_indicator=None,
    parent=None, is_current=False,
    item_height=36, item_font=None,
    item_type="image", position="middle", wheel_requires_focus=False,
)
```

State read from `index`, `full_path`, `list_num`,
`image_number`, `item_type`, `position`, `is_current`, `is_selected`.
The row factory `make_rating_row_factory(get_rating, increment_rating,
decrement_rating, create_rating_gesture)` builds these from a `ListRowSpec`.

## Inspection

Family `RatingListItem`; state: `index`, `full_path`, `list_num`,
`image_number`, `item_type`, `position`, `is_current`, `is_selected`;
token family `list_item.background.*`; regions and layers enabled
(Button-family extras).

Used by: `unified_list_picker` (double-list rating picker).

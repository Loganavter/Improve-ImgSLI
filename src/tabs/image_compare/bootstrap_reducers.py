"""Reducer registration for image_compare — imported once at plugin load."""

from core.state_management.extension_reducers import (
    register_render_config_reducer,
    register_session_data_reducer,
)
from core.state_management.slot_reducers import register_state_slot_reducer
from tabs.image_compare.state.reducer import DocumentReducer
from tabs.image_compare.state.reducers import (
    ImageRenderConfigReducer,
    SessionDataReducer,
)

register_state_slot_reducer("document", DocumentReducer.reduce)
register_session_data_reducer("image_compare", SessionDataReducer().reduce)
register_render_config_reducer(ImageRenderConfigReducer.reduce)

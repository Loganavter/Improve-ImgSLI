
def swap_current_images(controller):
    controller.playlist_manager.swap_current_images()

def swap_entire_lists(controller):
    controller.playlist_manager.swap_entire_lists()

def remove_current_image_from_list(controller, image_number: int):
    controller.playlist_manager.remove_current_image_from_list(image_number)

def remove_specific_image_from_list(controller, image_number: int, index_to_remove: int):
    controller.playlist_manager.remove_specific_image_from_list(image_number, index_to_remove)

def clear_image_list(controller, image_number: int):
    controller.playlist_manager.clear_image_list(image_number)

def reorder_item_in_list(controller, image_number: int, source_index: int, dest_index: int):
    controller.playlist_manager.reorder_item_in_list(image_number, source_index, dest_index)

def move_item_between_lists(controller, source_list_num: int, source_index: int, dest_list_num: int, dest_index: int):
    controller.playlist_manager.move_item_between_lists(
        source_list_num, source_index, dest_list_num, dest_index
    )

def on_edit_name_changed(controller, image_number, new_name):
    controller.playlist_manager.on_edit_name_changed(image_number, new_name)

def increment_rating(controller, image_number: int, index: int):
    controller.playlist_manager.increment_rating(image_number, index)

def decrement_rating(controller, image_number: int, index: int):
    controller.playlist_manager.decrement_rating(image_number, index)

def set_rating(controller, image_number: int, index_to_set: int, new_score: int):
    controller.playlist_manager.set_rating(image_number, index_to_set, new_score)

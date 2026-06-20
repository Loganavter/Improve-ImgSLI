add_library(sli_ui_toolkit_cpp STATIC
    include/sli/toolkit/button.h
    include/sli/toolkit/check_box.h
    include/sli/toolkit/combo_box.h
    include/sli/toolkit/group_box.h
    include/sli/toolkit/radio_button.h
    include/sli/toolkit/spin_box.h
    include/sli/toolkit/theme.h
    src/button.cpp
    src/check_box.cpp
    src/combo_box.cpp
    src/group_box.cpp
    src/radio_button.cpp
    src/spin_box.cpp
    src/theme.cpp
)

target_include_directories(sli_ui_toolkit_cpp
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(sli_ui_toolkit_cpp
    PUBLIC
        Qt6::Core
        Qt6::Gui
        Qt6::Widgets
)

add_executable(imgsli_app
    canvas_features.cpp
    canvas_widget.cpp
    canvas_widget.h
    feature_passes.cpp
    feature_passes.h
    feature_registry.cpp
    feature_registry.h
    main.cpp
    render_pass.h
    render_pass_registry.cpp
    render_pass_registry.h
    settings_dialog.cpp
    settings_dialog.h
    store.cpp
    store.h
)

qt_add_shaders(imgsli_app imgsli_canvas_shaders
    PREFIX "/imgsli/shaders"
    BASE "shaders"
    FILES
        shaders/canvas.vert
        shaders/canvas.frag
        shaders/feature.vert
        shaders/feature.frag
        shaders/overlay.vert
        shaders/overlay.frag
)

target_link_libraries(imgsli_app
    PRIVATE
        Qt6::Core
        Qt6::Gui
        Qt6::GuiPrivate
        Qt6::Widgets
        imgsli_core_bridge
        sli_ui_toolkit_cpp
)

target_include_directories(imgsli_app PRIVATE
    ${CMAKE_SOURCE_DIR}/include
)

add_test(
    NAME phase3_contracts
    COMMAND
        ${CMAKE_COMMAND} -E env
        QT_QPA_PLATFORM=offscreen
        IMGSLI_RHI_BACKEND=null
        $<TARGET_FILE:imgsli_app>
        --contract-check
)

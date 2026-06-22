add_executable(imgsli_app
    # domain (Python `src/domain/`) — POD types + Qt adapters + workspace.
    domain/types.h
    domain/qt_adapters.h
    domain/workspace.h

    # utils (Python `src/utils/`) — geometry mgmt + resource path helpers.
    utils/geometry.cpp
    utils/geometry.h
    utils/resource_loader.cpp
    utils/resource_loader.h

    # ui top-level helpers (Python `src/ui/icon_manager.py`, `gesture_resolver.py`)
    ui/icon_manager.cpp
    ui/icon_manager.h
    ui/gesture_resolver.cpp
    ui/gesture_resolver.h

    # ui overlay + form widgets (Python `src/ui/widgets/{rounded_overlay,
    # startup_placeholder,zoom_indicator,form_controls}.py`). Feature flyouts
    # (font_settings, magnifier_color, magnifier_visibility, video_session)
    # are architecturally replaced by their owning plugin's controllers.
    ui/widgets/rounded_overlay.cpp
    ui/widgets/rounded_overlay.h
    ui/widgets/startup_placeholder.cpp
    ui/widgets/startup_placeholder.h
    ui/widgets/zoom_indicator.cpp
    ui/widgets/zoom_indicator.h
    ui/widgets/form_controls.cpp
    ui/widgets/form_controls.h

    # ui/managers (Python `src/ui/managers/`). dialog_manager + transient_ui
    # are architecturally replaced by the toolkit Flyout + bootstrap wiring;
    # message_manager and tray_manager are real ports below.
    ui/managers/message_manager.cpp
    ui/managers/message_manager.h
    ui/managers/tray_manager.cpp
    ui/managers/tray_manager.h

    # services/system (Python `src/services/system/{clipboard,notifications}.py`)
    services/system/clipboard.cpp
    services/system/clipboard.h
    services/system/notifications.cpp
    services/system/notifications.h

    # services/io — synchronous image loader (Python `src/services/io/image_loader.py`).
    # The progressive / QtConcurrent path stays in `plugins/comparison/use_cases/loading.cpp`.
    services/io/image_loader.cpp
    services/io/image_loader.h

    # shared/rendering helpers (Python `src/shared/rendering/{interpolation,
    # live_snapshot,target_surface}.py`) + canonical canvas plan builder
    # (Python `plan_builder.py`, now in Rust `shared::rendering::plan_builder`).
    shared/rendering/interpolation.cpp
    shared/rendering/interpolation.h
    shared/rendering/live_snapshot.cpp
    shared/rendering/live_snapshot.h
    shared/rendering/target_surface.h
    shared/rendering/plan_builder.cpp
    shared/rendering/plan_builder.h

    # shared/image_processing helpers (Python `src/shared/image_processing/`).
    # `progressive_loader.py` stays Python-only — its consumer lives in the
    # comparison plugin's QtConcurrent path.
    shared/image_processing/qt_conversion.cpp
    shared/image_processing/qt_conversion.h
    shared/image_processing/prescale.cpp
    shared/image_processing/prescale.h
    shared/image_processing/resize.cpp
    shared/image_processing/resize.h
    shared/image_processing/regions.cpp
    shared/image_processing/regions.h
    shared/image_processing/analysis_pair.cpp
    shared/image_processing/analysis_pair.h

    # shell / entry
    shell/main.cpp
    shell/bootstrap.cpp
    shell/bootstrap.h
    shell/ui.cpp
    shell/ui.h
    shell/layouts.cpp
    shell/layouts.h
    shell/custom_window.cpp
    shell/custom_window.h
    shell/i18n_helper.h

    # core runtime (store, registries, render pass contracts)
    core/store.cpp
    core/store.h
    core/feature_registry.cpp
    core/feature_registry.h
    core/plugin_registry.cpp
    core/plugin_registry.h
    core/tab_registry.cpp
    core/tab_registry.h
    core/render_pass.h
    core/render_pass_registry.cpp
    core/render_pass_registry.h

    # ui / canvas (widget + shared rasterizers)
    ui/canvas/canvas_widget.cpp
    ui/canvas/canvas_widget.h
    ui/canvas/passes/background_pass.h
    ui/canvas/passes/shape_pass.cpp
    ui/canvas/passes/shape_pass.h
    ui/canvas/passes/filename_overlay_pass.cpp
    ui/canvas/passes/filename_overlay_pass.h
    ui/canvas/vulkan_smoke.h

    # ui / canvas features (per-feature command handlers + pass binding)
    ui/canvas_features/registry.cpp
    ui/canvas_features/registry.h
    ui/canvas_features/divider/feature.cpp
    ui/canvas_features/magnifier/feature.cpp
    ui/canvas_features/guides/feature.cpp
    ui/canvas_features/capture/feature.cpp
    ui/canvas_features/paste_overlay/feature.cpp
    ui/canvas_features/filename_overlay/feature.cpp

    # cli commands
    cli/analysis_snapshot_command.cpp
    cli/analysis_snapshot_command.h
    cli/benchmark_command.cpp
    cli/benchmark_command.h
    cli/comparison_command.cpp
    cli/comparison_command.h
    cli/contract_check_command.cpp
    cli/contract_check_command.h
    cli/session_blueprint_command.cpp
    cli/session_blueprint_command.h
    cli/snapshot_command.cpp
    cli/snapshot_command.h
    cli/startup_options.cpp
    cli/startup_options.h
    cli/video_transcode_command.cpp
    cli/video_transcode_command.h

    # plugins
    plugins/analysis/plugin.cpp
    plugins/analysis/controller.cpp
    plugins/analysis/controller.h
    plugins/analysis/services/metrics.cpp
    plugins/analysis/services/runtime.cpp
    plugins/comparison/plugin.cpp
    plugins/comparison/controller.cpp
    plugins/comparison/controller.h
    plugins/comparison/use_cases/loading.cpp
    plugins/comparison/use_cases/navigation.cpp
    plugins/export/plugin.cpp
    plugins/export/services/offscreen_renderer.cpp
    plugins/export/services/offscreen_renderer.h
    plugins/export/services/image_export.cpp
    plugins/export/services/image_export.h
    plugins/export/services/canvas_export.cpp
    plugins/export/services/canvas_export.h
    plugins/help/plugin.cpp
    plugins/help/dialog.cpp
    plugins/help/dialog.h
    plugins/layout/plugin.cpp
    plugins/settings/plugin.cpp
    plugins/settings/dialog.cpp
    plugins/settings/dialog.h
    plugins/settings/application_service.cpp
    plugins/settings/application_service.h
    plugins/settings/pages/page.h
    plugins/settings/pages/general_page.cpp
    plugins/settings/pages/general_page.h
    plugins/settings/pages/interface_page.cpp
    plugins/settings/pages/interface_page.h
    plugins/settings/pages/performance_page.cpp
    plugins/settings/pages/performance_page.h
    plugins/settings/pages/analysis_page.cpp
    plugins/settings/pages/analysis_page.h
    plugins/video_editor/plugin.cpp
    plugins/video_editor/controller.cpp
    plugins/video_editor/controller.h
    plugins/video_editor/services/recorder.cpp
    plugins/video_editor/services/recorder.h
    plugins/video_editor/services/keyframe_policy.cpp
    plugins/video_editor/services/keyframe_policy.h
    plugins/video_editor/services/plugin_state.cpp
    plugins/video_editor/services/plugin_state.h
    plugins/video_editor/services/timeline_router.cpp
    plugins/video_editor/services/timeline_router.h
    plugins/video_editor/services/project_router.cpp
    plugins/video_editor/services/project_router.h
    plugins/video_editor/services/export_router.cpp
    plugins/video_editor/services/export_router.h
    plugins/video_editor/services/recorder_router.cpp
    plugins/video_editor/services/recorder_router.h
    plugins/video_editor/services/preview_router.cpp
    plugins/video_editor/services/preview_router.h

    # tabs
    tabs/export/tab.cpp
    tabs/multi_compare/tab.cpp
    tabs/multi_compare/grid.cpp
    tabs/multi_compare/grid.h
    tabs/multi_compare/sections/sections.cpp
    tabs/multi_compare/sections/sections.h
    tabs/multi_compare/sections/comparison_controls_section.cpp
    tabs/multi_compare/sections/analysis_controls_section.cpp
    tabs/multi_compare/sections/grid_section.cpp
    tabs/video_editor/tab.cpp
    tabs/video_editor/sections/sections.cpp
    tabs/video_editor/sections/sections.h
    tabs/video_editor/sections/project_section.cpp
    tabs/video_editor/sections/recording_section.cpp
    tabs/video_editor/sections/preview_section.cpp
    tabs/video_editor/sections/timeline_section.cpp
    tabs/video_editor/sections/export_section.cpp
)

target_compile_definitions(imgsli_app PRIVATE
    IMGSLI_I18N_ROOT="${CMAKE_SOURCE_DIR}/../src/resources/i18n"
    IMGSLI_HELP_ROOT="${CMAKE_SOURCE_DIR}/../src/resources/help"
    IMGSLI_DEFAULT_RESOURCE_ROOT="${CMAKE_SOURCE_DIR}/../src/resources"
)

qt_add_shaders(imgsli_app imgsli_canvas_shaders
    PREFIX "/imgsli/shaders"
    BASE "ui/canvas/shaders"
    FILES
        ui/canvas/shaders/canvas.vert
        ui/canvas/shaders/canvas.frag
        ui/canvas/shaders/feature.vert
        ui/canvas/shaders/feature.frag
        ui/canvas/shaders/overlay.vert
        ui/canvas/shaders/overlay.frag
)

target_link_libraries(imgsli_app
    PRIVATE
        Qt6::Core
        Qt6::Concurrent
        Qt6::Gui
        Qt6::GuiPrivate
        Qt6::Widgets
        imgsli_core_bridge
        sli_ui_toolkit_cpp
)

target_include_directories(imgsli_app PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}
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

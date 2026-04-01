from plugins.video_editor.services.export_config import ExportConfigBuilder

class ExportCoordinator:
    def __init__(self, view, main_controller, model, editor_service, preview_coordinator):
        self.view = view
        self.main_controller = main_controller
        self.model = model
        self.editor_service = editor_service
        self.preview_coordinator = preview_coordinator

    def detach_view(self):
        self.view = None

    def export_video(self, emit_export_started):
        if self.view is None:
            return
        export_options = self.view.get_export_options()
        export_options["fit_content"] = self.preview_coordinator.fit_content_mode

        config_params = {
            key: value
            for key, value in export_options.items()
            if key
            not in ["output_dir", "file_name", "fit_content", "fit_content_fill_color"]
        }
        config = ExportConfigBuilder.build_export_config(**config_params)
        export_options.update(config)

        if self.main_controller and getattr(self.main_controller, "video_export", None):
            self.main_controller.video_export.export_video_from_editor(
                self.editor_service.get_current_recording(),
                self.model.fps,
                self.model.get_resolution(),
                export_options,
            )
            emit_export_started()

    def stop_export(self):
        if self.main_controller is not None and getattr(
            self.main_controller, "video_export", None
        ):
            self.main_controller.video_export.cancel_video_export()

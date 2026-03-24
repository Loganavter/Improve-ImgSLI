from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from plugins.video_editor.model import VideoSessionSnapshot
from shared_toolkit.ui.widgets.atomic.custom_button import CustomButton
from shared_toolkit.ui.widgets.atomic.text_labels import BodyLabel, CaptionLabel
from ui.icon_manager import AppIcon

class VideoSessionWidget(QWidget):
    create_image_compare_requested = pyqtSignal()
    advance_timeline_requested = pyqtSignal()
    attach_resource_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.title_label = BodyLabel(self, "Video Workspace")
        self.subtitle_label = CaptionLabel(
            "Dedicated video session state is active for this tab.", self
        )
        self.subtitle_label.setWordWrap(True)

        self.session_info_label = CaptionLabel("", self)
        self.session_info_label.setWordWrap(True)
        self.timeline_label = CaptionLabel("", self)
        self.timeline_label.setWordWrap(True)
        self.selection_label = CaptionLabel("", self)
        self.selection_label.setWordWrap(True)
        self.resources_label = CaptionLabel("", self)
        self.resources_label.setWordWrap(True)
        self.metadata_label = CaptionLabel("", self)
        self.metadata_label.setWordWrap(True)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.btn_advance_timeline = CustomButton(AppIcon.PLAY, "Advance Timeline", self)
        self.btn_attach_resource = CustomButton(
            AppIcon.LINK, "Attach Decoder", self
        )
        self.btn_create_image_compare = CustomButton(
            AppIcon.PHOTO, "Open Image Compare", self
        )

        self.btn_advance_timeline.clicked.connect(self.advance_timeline_requested.emit)
        self.btn_attach_resource.clicked.connect(self.attach_resource_requested.emit)
        self.btn_create_image_compare.clicked.connect(
            self.create_image_compare_requested.emit
        )

        actions_layout.addWidget(self.btn_advance_timeline)
        actions_layout.addWidget(self.btn_attach_resource)
        actions_layout.addWidget(self.btn_create_image_compare)
        actions_layout.addStretch(1)

        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addSpacing(4)
        layout.addWidget(self.session_info_label)
        layout.addWidget(self.timeline_label)
        layout.addWidget(self.selection_label)
        layout.addWidget(self.resources_label)
        layout.addWidget(self.metadata_label)
        layout.addSpacing(8)
        layout.addLayout(actions_layout)
        layout.addStretch(1)

    def clear(self):
        self.title_label.setText("Video Workspace")
        self.session_info_label.setText("Session ID: -")
        self.timeline_label.setText("Timeline: -")
        self.selection_label.setText("Selection: -")
        self.resources_label.setText("Resources: -")
        self.metadata_label.setText("Metadata: -")

    def set_snapshot(self, snapshot: VideoSessionSnapshot):
        self.title_label.setText(snapshot.title)
        self.session_info_label.setText(f"Session ID: {snapshot.session_id}")

        timeline = snapshot.timeline
        selection = snapshot.selection
        source = snapshot.source
        decoder = snapshot.decoder
        metadata = snapshot.metadata

        self.timeline_label.setText(f"Timeline: position={timeline.position}")
        if selection.is_empty():
            selection_text = "empty"
        else:
            selection_parts = []
            if selection.start is not None:
                selection_parts.append(f"start={selection.start}")
            if selection.end is not None:
                selection_parts.append(f"end={selection.end}")
            selection_text = ", ".join(selection_parts)
        self.selection_label.setText(f"Selection: {selection_text}")

        if snapshot.resource_namespaces:
            resource_text = ", ".join(snapshot.resource_namespaces)
        else:
            resource_text = "none"
        if source is not None:
            resource_text += (
                f" | source(id={source.source_id}, type={source.source_type}, "
                f"timeline_position={source.timeline_position})"
            )
        if decoder is not None:
            resource_text += (
                f" | decoder(status={decoder.status}, timeline_position={decoder.timeline_position})"
            )
        self.resources_label.setText(f"Resources: {resource_text}")

        if metadata:
            metadata_text = ", ".join(f"{key}={value}" for key, value in metadata.items())
        else:
            metadata_text = "none"
        self.metadata_label.setText(f"Metadata: {metadata_text}")

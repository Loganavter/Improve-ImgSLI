import os
import sys
from types import SimpleNamespace

from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "packages",
        "sli-ui-toolkit",
        "src",
    ),
)

from plugins.export.services.image_export import ExportService
from plugins.video_editor.services.video_export_models import VideoRenderRequest
from plugins.video_editor.services.video_snapshot_rendering import (
    PreparedCanvasFrame,
    SnapshotFrameRenderer,
)
from shared.rendering import TargetSurfaceSpec

class _FakeGpuExportService:
    def __init__(self):
        self.calls = []

    def render_plan(self, plan, *, store=None, diff_image=None):
        self.calls.append(
            {
                "plan": plan,
                "store": store,
                "diff_image": diff_image,
            }
        )
        return Image.new("RGBA", (8, 8), (0, 0, 0, 0)), {}

def test_export_service_passes_cached_diff_image_to_gpu_render_plan(tmp_path):
    gpu = _FakeGpuExportService()
    service = ExportService(font_path_absolute="", gpu_export_service=gpu)

    diff_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    render_store = SimpleNamespace(
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(cached_diff_image=diff_image)
            )
        )
    )
    export_options = {
        "output_dir": str(tmp_path),
        "file_name": "diff-export",
        "format": "PNG",
        "fill_background": False,
        "include_metadata": False,
    }

    out_path = service.export_image(
        store=SimpleNamespace(),
        original_image1=Image.new("RGBA", (8, 8), (0, 0, 0, 255)),
        original_image2=Image.new("RGBA", (8, 8), (255, 255, 255, 255)),
        export_options=export_options,
        render_plan=SimpleNamespace(),
        render_store=render_store,
    )

    assert os.path.isfile(out_path)
    assert gpu.calls[0]["diff_image"] is diff_image

def test_snapshot_frame_renderer_passes_cached_diff_image_to_gpu_preview():
    gpu = _FakeGpuExportService()
    renderer = SnapshotFrameRenderer(image_loader=lambda *_args, **_kwargs: None, gpu_export_service=gpu)

    diff_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    prepared = PreparedCanvasFrame(
        store=SimpleNamespace(
            viewport=SimpleNamespace(
                session_data=SimpleNamespace(
                    render_cache=SimpleNamespace(cached_diff_image=diff_image)
                )
            )
        ),
        plan=SimpleNamespace(canvas_w=8, canvas_h=8),
        output_width=8,
        output_height=8,
        image_dest_x=0,
        image_dest_y=0,
        fill_rgba=(0, 0, 0, 0),
        debug={},
    )
    request = VideoRenderRequest(
        target_surface=TargetSurfaceSpec(width=8, height=8, fill_rgba=(0, 0, 0, 0)),
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
    )

    result = renderer._render_prepared(prepared, request)

    assert result.image.size == (8, 8)
    assert gpu.calls[0]["diff_image"] is diff_image

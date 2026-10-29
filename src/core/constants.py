class AppConstants:
    # Kept in sync by hand with the packaging templates under build/ (AUR
    # PKGBUILD's pkgver, the Flatpak metainfo <release> entries, and Inno
    # Setup's MyAppVersion) -- this is the one copy the app itself reads at
    # runtime, e.g. for QApplication.setApplicationVersion and for the
    # last-seen-version check in core.bootstrap that offers a one-time
    # stale-cache purge notice after upgrading from an untracked version.
    APP_VERSION = "11.0.0"

    MIN_NAME_LENGTH_LIMIT = 10
    MAX_NAME_LENGTH_LIMIT = 150
    DEFAULT_JPEG_QUALITY = 93
    #: Default sampler filter. Nearest on purpose: it is the only filter whose
    #: result is the real pixels (blocks you can count), and every other choice
    #: is a taste for smoothing — see docs/dev/rendering/display-image-pipeline.md.
    DEFAULT_INTERPOLATION_METHOD = "NEAREST"
    BASE_MOVEMENT_SPEED = 0.5
    MIN_CHANGE_THRESHOLD = 0.0001
    SMOOTHING_FACTOR_POS = 0.15
    SMOOTHING_FACTOR_SPACING = 0.2
    SMOOTHING_FACTOR_SPLIT = 0.2
    LERP_STOP_THRESHOLD = 0.001
    MAX_TARGET_DELTA_PER_TICK = 0.1

    INTERPOLATION_METHODS_MAP = {
        "NEAREST": "Nearest Neighbor",
        "BILINEAR": "Bilinear",
        "BICUBIC": "Bicubic",
        "LANCZOS": "Lanczos",
        "EWA_LANCZOS": "EWA Lanczos",
    }

    INTERPOLATION_SPEED_ORDER = {
        "NEAREST": 0,
        "BILINEAR": 1,
        "BICUBIC": 2,
        "LANCZOS": 3,
        "EWA_LANCZOS": 4,
    }

    FLYOUT_ANIMATION_DURATION_MS = 150
    TEXT_SETTINGS_FLYOUT_ANIMATION_DURATION_MS = 150
    TRANSIENT_HOVER_OPEN_DELAY_MS = 150
    TRANSIENT_AUTO_HIDE_DELAY_MS = 300
    TRANSIENT_WHEEL_AUTO_HIDE_DELAY_MS = 1200
    TRANSIENT_FLYOUT_SHOW_DELAY_MS = 250
    TRANSIENT_FLYOUT_HIDE_CHECK_DELAY_MS = 300

    PROGRESSIVE_LOAD_THRESHOLD_BYTES = 2 * 1024 * 1024
    PROGRESSIVE_LOAD_THRESHOLD_PIXELS = 1920 * 1080
    # Decode-backend safety bound against pathological/corrupt files, applied
    # by the PIL/imagecodecs full-frame decode path only. When pyvips
    # streaming decode is available for a file (see
    # shared/image_processing/progressive_loader.py::pyvips_can_stream) the
    # bound does not apply — libvips streams strips straight to the memmap
    # without a full-frame decode buffer.
    MAX_SUPPORTED_IMAGE_DIMENSION = 65536
    # Host tile size for TiledPixelStore (GEGL-style always-tiled storage).
    # Separate from GPU live tile extent (8192 in rhi_renderer/resources.py).
    PIXEL_TILE_SIZE = 512

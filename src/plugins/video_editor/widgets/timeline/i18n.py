from __future__ import annotations

from resources.translations import get_current_language, tr

_TOKEN_KEYS = {
    "ON": "common.switch.switch_on",
    "OFF": "common.switch.switch_off",
    "NEAREST": "magnifier.nearest_neighbor",
    "BILINEAR": "magnifier.bilinear",
    "BICUBIC": "magnifier.bicubic",
    "LANCZOS": "magnifier.lanczos",
    "EWA_LANCZOS": "magnifier.ewa_lanczos",
    "LEFT": "common.position.left",
    "CENTER": "common.position.center",
    "RIGHT": "common.position.right",
    "RGB": "video.rgb",
    "R": "video.red",
    "G": "video.green",
    "B": "video.blue",
    "L": "video.luminance",
    "HIGHLIGHT": "video.highlight",
    "GRAYSCALE": "video.grayscale",
    "EDGES": "video.edge_comparison",
    "SSIM": "video.ssim_map",
}

def localize_token(token: str) -> str:
    normalized = str(token).strip()
    if not normalized:
        return normalized
    key = _TOKEN_KEYS.get(normalized.upper())
    if key is None:
        return normalized
    translated = tr(key, get_current_language())
    return translated if translated != key else normalized

def localize_value(value) -> str:
    if isinstance(value, bool):
        return localize_token("ON" if value else "OFF")
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, str):
        if ";" in value:
            parts = [localize_token(part) for part in value.split(";") if part.strip()]
            return ";".join(parts) if parts else value
        return localize_token(value)
    return str(value)

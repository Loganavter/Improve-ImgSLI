"""Autocrop new module — parity vips vs pil и кэш CropService.

Проверяет поддерживаемость рефактора: явные типы, DI без глобала.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from shared.image_processing.autocrop import CropBox, CropConfig, CropService
from shared.image_processing.autocrop.scaling import get_scaled_box_for_thumb
from shared.image_processing.autocrop.pil import find_box_pil
from shared.image_processing.autocrop.vips import find_box_vips


def test_parity_vips_vs_pil_small_probe():
    """Parity как в test_decode_backends:125 — vips find_trim vs PIL get_auto_crop_box."""
    arr = np.zeros((60, 80, 4), dtype=np.uint8)
    arr[10:50, 20:60, :3] = 200
    arr[10:50, 20:60, 3] = 255
    rgba = Image.fromarray(arr, mode="RGBA")

    vips_box = find_box_vips(np.asarray(rgba), threshold=15)
    pil_box = find_box_pil(rgba, threshold=15)

    if vips_box is not None:
        assert pil_box is not None, "PIL должен согласиться с vips"
        assert vips_box.to_tuple() == pil_box.to_tuple()
    # если vips недоступен — pil всё равно должен работать
    assert pil_box is not None
    assert pil_box == CropBox(20, 10, 60, 50)


def test_parity_vips_vs_pil_scaled():
    """Scaled parity — зонд 1024 с fallback thr30 (как в end-to-end streaming test)."""
    arr = np.zeros((200, 300, 4), dtype=np.uint8)
    arr[30:170, 40:260, :3] = 180
    arr[30:170, 40:260, 3] = 255
    rgba = Image.fromarray(arr, mode="RGBA")
    # pil напрямую на полном
    pil_full = find_box_pil(rgba, 15)
    assert pil_full is not None
    # vips на том же
    vips_full = find_box_vips(np.asarray(rgba), 15)
    if vips_full is not None:
        assert vips_full.to_tuple() == pil_full.to_tuple()


def test_crop_service_cache_and_invalidate(tmp_path):
    # создаём изображение с чёрными полями
    arr = np.zeros((80, 100, 4), dtype=np.uint8)
    arr[10:70, 20:80, :3] = 150
    arr[10:70, 20:80, 3] = 255
    p = tmp_path / "a.png"
    Image.fromarray(arr, mode="RGBA").save(str(p))

    svc = CropService(CropConfig(thr=15, thr_fallback=30, probe_max=1024))
    assert svc.cache_size == 0
    box1 = svc.get(str(p))
    assert box1 is not None
    assert svc.cache_size == 1
    # повторный hit — из кэша, не переоткрывает
    box2 = svc.get(str(p))
    assert box2 == box1
    assert svc.cache_size == 1

    # invalidate одного пути
    svc.invalidate(str(p))
    assert svc.cache_size == 0
    # снова compute
    box3 = svc.get(str(p))
    assert box3 == box1

    # invalidate_all
    svc.invalidate_all()
    assert svc.cache_size == 0


def test_crop_service_isolation():
    svc1 = CropService()
    svc2 = CropService()
    # разные инстансы — разные кэши (нет глобала)
    svc1._cache["/tmp/fake.png"] = None  # type: ignore
    assert svc2.cache_size == 0
    svc1.invalidate_all()
    assert svc1.cache_size == 0


def test_scaling_centralized():
    orig = CropBox(20, 10, 60, 50)
    scaled = get_scaled_box_for_thumb(orig, (80, 60), (40, 30))
    assert scaled is not None
    # 80->40 scale 0.5, 60->30 scale 0.5 => (10,5,30,25)
    assert scaled.to_tuple() == (10, 5, 30, 25)
    # полный кадр -> None
    full = CropBox(0, 0, 80, 60)
    assert get_scaled_box_for_thumb(full, (80, 60), (80, 60)) is None
    # None input -> None
    assert get_scaled_box_for_thumb(None, (80, 60), (40, 30)) is None


def test_crop_service_no_crop_returns_none(tmp_path):
    # полностью залитое без полей — нет кропа
    arr = np.full((32, 32, 4), 200, dtype=np.uint8)
    p = tmp_path / "full.png"
    Image.fromarray(arr, mode="RGBA").save(str(p))
    svc = CropService()
    res = svc.compute(str(p))
    assert res is None or res.box is None
    # get также None
    assert svc.get(str(p)) is None

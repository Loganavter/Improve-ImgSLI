
import logging
from typing import Optional, Tuple

import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger("ImproveImgSLI")

def calculate_psnr(image1: Image.Image, image2: Image.Image) -> Optional[float]:
    if not image1 or not image2 or image1.size != image2.size:
        return None

    try:
        arr1 = np.array(image1.convert("RGB"))
        arr2 = np.array(image2.convert("RGB"))
        return psnr(arr1, arr2, data_range=255)
    except Exception as e:
        logger.error(f"Error calculating PSNR: {e}", exc_info=True)
        return None

def calculate_ssim(image1: Image.Image, image2: Image.Image) -> Optional[float]:
    if not image1 or not image2 or image1.size != image2.size:
        return None

    try:
        arr1 = np.array(image1.convert("RGB"))
        arr2 = np.array(image2.convert("RGB"))
        return ssim(arr1, arr2, data_range=255, channel_axis=2)
    except Exception as e:
        logger.error(f"Error calculating SSIM: {e}", exc_info=True)
        return None

def calculate_metrics(image1: Image.Image, image2: Image.Image) -> Optional[Tuple[float, float]]:
    if not image1 or not image2 or image1.size != image2.size:
        return None

    try:
        arr1 = np.array(image1.convert("RGB"))
        arr2 = np.array(image2.convert("RGB"))

        psnr_val = psnr(arr1, arr2, data_range=255)
        ssim_val = ssim(arr1, arr2, data_range=255, channel_axis=2)

        return psnr_val, ssim_val
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}", exc_info=True)
        return None


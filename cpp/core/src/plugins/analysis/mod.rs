//! Pure image-analysis operations used by the C++ analysis plugin.
//!
//! Input/output pixels are tightly packed RGBA8. Metrics use RGB channels;
//! SSIM is calculated over luminance with a local 7×7 window and integral
//! images, matching the local-window semantics of skimage without pulling Qt
//! or Python dependencies into the core.

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Metrics {
    pub psnr: f64,
    pub ssim: f64,
}

#[derive(Debug, thiserror::Error)]
pub enum AnalysisError {
    #[error("image dimensions are invalid")]
    InvalidDimensions,
    #[error("pixel buffer length does not match image dimensions")]
    InvalidBuffer,
    #[error("analysis mode is not supported: {0}")]
    UnsupportedMode(String),
}

fn validate(left: &[u8], right: &[u8], width: u32, height: u32) -> Result<usize, AnalysisError> {
    if width == 0 || height == 0 {
        return Err(AnalysisError::InvalidDimensions);
    }
    let pixels = (width as usize)
        .checked_mul(height as usize)
        .ok_or(AnalysisError::InvalidDimensions)?;
    let bytes = pixels
        .checked_mul(4)
        .ok_or(AnalysisError::InvalidDimensions)?;
    if left.len() != bytes || right.len() != bytes {
        return Err(AnalysisError::InvalidBuffer);
    }
    Ok(pixels)
}

pub fn metrics(
    left: &[u8],
    right: &[u8],
    width: u32,
    height: u32,
) -> Result<Metrics, AnalysisError> {
    let pixels = validate(left, right, width, height)?;
    let mut squared_error = 0.0;
    for index in 0..pixels {
        let offset = index * 4;
        for channel in 0..3 {
            let delta = left[offset + channel] as f64 - right[offset + channel] as f64;
            squared_error += delta * delta;
        }
    }
    let mse = squared_error / (pixels * 3) as f64;
    let psnr = if mse == 0.0 {
        f64::INFINITY
    } else {
        10.0 * ((255.0 * 255.0) / mse).log10()
    };
    let (ssim, _) = local_ssim(left, right, width as usize, height as usize, false);
    Ok(Metrics { psnr, ssim })
}

pub fn diff(
    left: &[u8],
    right: &[u8],
    width: u32,
    height: u32,
    mode: &str,
    channel_mode: &str,
) -> Result<Vec<u8>, AnalysisError> {
    let pixels = validate(left, right, width, height)?;
    let left_channel = channel(left, width, height, channel_mode)?;
    let right_channel = channel(right, width, height, channel_mode)?;
    let left = left_channel.as_slice();
    let right = right_channel.as_slice();
    match mode {
        "highlight" => Ok(highlight(left, right, pixels, 10)),
        "grayscale" => Ok(grayscale(left, right, pixels)),
        "edges" => Ok(edges(left, width as usize, height as usize)),
        "ssim" => {
            let (_, map) = local_ssim(left, right, width as usize, height as usize, true);
            Ok(map)
        }
        other => Err(AnalysisError::UnsupportedMode(other.to_string())),
    }
}

pub fn channel(
    image: &[u8],
    width: u32,
    height: u32,
    mode: &str,
) -> Result<Vec<u8>, AnalysisError> {
    let pixels = validate(image, image, width, height)?;
    if mode == "RGB" {
        return Ok(image.to_vec());
    }
    let mut out = vec![0; pixels * 4];
    for index in 0..pixels {
        let offset = index * 4;
        match mode {
            "R" => out[offset] = image[offset],
            "G" => out[offset + 1] = image[offset + 1],
            "B" => out[offset + 2] = image[offset + 2],
            "L" => {
                let value = luma(&image[offset..offset + 4]).round() as u8;
                out[offset..offset + 3].fill(value);
            }
            other => return Err(AnalysisError::UnsupportedMode(other.to_string())),
        }
        out[offset + 3] = image[offset + 3];
    }
    Ok(out)
}

fn luma(pixel: &[u8]) -> f64 {
    pixel[0] as f64 * 0.299 + pixel[1] as f64 * 0.587 + pixel[2] as f64 * 0.114
}

fn gray_delta(left: &[u8], right: &[u8]) -> u8 {
    let red = (left[0] as i16 - right[0] as i16).unsigned_abs() as f64;
    let green = (left[1] as i16 - right[1] as i16).unsigned_abs() as f64;
    let blue = (left[2] as i16 - right[2] as i16).unsigned_abs() as f64;
    (red * 0.299 + green * 0.587 + blue * 0.114)
        .round()
        .clamp(0.0, 255.0) as u8
}

fn highlight(left: &[u8], right: &[u8], pixels: usize, threshold: u8) -> Vec<u8> {
    let mut out = left.to_vec();
    for index in 0..pixels {
        let offset = index * 4;
        if gray_delta(&left[offset..offset + 4], &right[offset..offset + 4]) > threshold {
            out[offset] = 255;
            out[offset + 1] = 90;
            out[offset + 2] = 120;
            out[offset + 3] = 255;
        }
    }
    out
}

fn grayscale(left: &[u8], right: &[u8], pixels: usize) -> Vec<u8> {
    let mut values = Vec::with_capacity(pixels);
    let mut minimum = u8::MAX;
    let mut maximum = u8::MIN;
    for index in 0..pixels {
        let offset = index * 4;
        let value = gray_delta(&left[offset..offset + 4], &right[offset..offset + 4]);
        minimum = minimum.min(value);
        maximum = maximum.max(value);
        values.push(value);
    }
    let mut out = vec![0; pixels * 4];
    for (index, value) in values.into_iter().enumerate() {
        let normalized = if maximum > minimum {
            ((value.saturating_sub(minimum)) as f64 * 255.0 / (maximum - minimum) as f64).round()
                as u8
        } else {
            value
        };
        let offset = index * 4;
        out[offset..offset + 3].fill(normalized);
        out[offset + 3] = 255;
    }
    out
}

fn edges(image: &[u8], width: usize, height: usize) -> Vec<u8> {
    let gray: Vec<f64> = image.chunks_exact(4).map(luma).collect();
    let mut out = vec![0; width * height * 4];
    let sample = |x: isize, y: isize| -> f64 {
        let x = x.clamp(0, width as isize - 1) as usize;
        let y = y.clamp(0, height as isize - 1) as usize;
        gray[y * width + x]
    };
    for y in 0..height {
        for x in 0..width {
            let x = x as isize;
            let y = y as isize;
            let gx = -sample(x - 1, y - 1) + sample(x + 1, y - 1) - 2.0 * sample(x - 1, y)
                + 2.0 * sample(x + 1, y)
                - sample(x - 1, y + 1)
                + sample(x + 1, y + 1);
            let gy = -sample(x - 1, y - 1) - 2.0 * sample(x, y - 1) - sample(x + 1, y - 1)
                + sample(x - 1, y + 1)
                + 2.0 * sample(x, y + 1)
                + sample(x + 1, y + 1);
            let value = (gx.hypot(gy) / 4.0).clamp(0.0, 255.0) as u8;
            let offset = (y as usize * width + x as usize) * 4;
            out[offset..offset + 3].fill(value);
            out[offset + 3] = 255;
        }
    }
    out
}

fn integral(values: &[f64], width: usize, height: usize) -> Vec<f64> {
    let stride = width + 1;
    let mut result = vec![0.0; (width + 1) * (height + 1)];
    for y in 0..height {
        let mut row = 0.0;
        for x in 0..width {
            row += values[y * width + x];
            result[(y + 1) * stride + x + 1] = result[y * stride + x + 1] + row;
        }
    }
    result
}

fn rect_sum(
    table: &[f64],
    stride: usize,
    left: usize,
    top: usize,
    right: usize,
    bottom: usize,
) -> f64 {
    table[bottom * stride + right] - table[top * stride + right] - table[bottom * stride + left]
        + table[top * stride + left]
}

fn local_ssim(
    left: &[u8],
    right: &[u8],
    width: usize,
    height: usize,
    with_map: bool,
) -> (f64, Vec<u8>) {
    let x: Vec<f64> = left.chunks_exact(4).map(luma).collect();
    let y: Vec<f64> = right.chunks_exact(4).map(luma).collect();
    let x2: Vec<f64> = x.iter().map(|v| v * v).collect();
    let y2: Vec<f64> = y.iter().map(|v| v * v).collect();
    let xy: Vec<f64> = x.iter().zip(&y).map(|(a, b)| a * b).collect();
    let sx = integral(&x, width, height);
    let sy = integral(&y, width, height);
    let sx2 = integral(&x2, width, height);
    let sy2 = integral(&y2, width, height);
    let sxy = integral(&xy, width, height);
    let stride = width + 1;
    let c1 = (0.01_f64 * 255.0).powi(2);
    let c2 = (0.03_f64 * 255.0).powi(2);
    let mut total = 0.0;
    let mut map = if with_map {
        vec![0; width * height * 4]
    } else {
        Vec::new()
    };
    for py in 0..height {
        for px in 0..width {
            let left_edge = px.saturating_sub(3);
            let top = py.saturating_sub(3);
            let right_edge = (px + 4).min(width);
            let bottom = (py + 4).min(height);
            let count = ((right_edge - left_edge) * (bottom - top)) as f64;
            let mean_x = rect_sum(&sx, stride, left_edge, top, right_edge, bottom) / count;
            let mean_y = rect_sum(&sy, stride, left_edge, top, right_edge, bottom) / count;
            let variance_x = rect_sum(&sx2, stride, left_edge, top, right_edge, bottom) / count
                - mean_x * mean_x;
            let variance_y = rect_sum(&sy2, stride, left_edge, top, right_edge, bottom) / count
                - mean_y * mean_y;
            let covariance = rect_sum(&sxy, stride, left_edge, top, right_edge, bottom) / count
                - mean_x * mean_y;
            let numerator = (2.0 * mean_x * mean_y + c1) * (2.0 * covariance + c2);
            let denominator = (mean_x * mean_x + mean_y * mean_y + c1)
                * (variance_x.max(0.0) + variance_y.max(0.0) + c2);
            let value = if denominator == 0.0 {
                1.0
            } else {
                (numerator / denominator).clamp(-1.0, 1.0)
            };
            total += value;
            if with_map {
                let difference = ((1.0 - value) * 127.5).clamp(0.0, 255.0) as u8;
                let offset = (py * width + px) * 4;
                map[offset] = difference;
                map[offset + 1] = (difference as f32 * 0.35) as u8;
                map[offset + 2] = 255_u8.saturating_sub(difference);
                map[offset + 3] = 255;
            }
        }
    }
    (total / (width * height) as f64, map)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn solid(value: u8, width: u32, height: u32) -> Vec<u8> {
        [value, value, value, 255].repeat((width * height) as usize)
    }

    #[test]
    fn identical_metrics_are_perfect() {
        let image = solid(80, 8, 8);
        let result = metrics(&image, &image, 8, 8).unwrap();
        assert!(result.psnr.is_infinite());
        assert!((result.ssim - 1.0).abs() < 1e-9);
    }

    #[test]
    fn diff_modes_return_rgba_shape() {
        let left = solid(0, 8, 8);
        let right = solid(255, 8, 8);
        for mode in ["highlight", "grayscale", "edges", "ssim"] {
            assert_eq!(
                diff(&left, &right, 8, 8, mode, "RGB").unwrap().len(),
                8 * 8 * 4
            );
        }
    }

    #[test]
    fn channel_extraction_preserves_requested_component() {
        let image = [10, 20, 30, 255].repeat(4);
        assert_eq!(&channel(&image, 2, 2, "R").unwrap()[..4], &[10, 0, 0, 255]);
        assert_eq!(&channel(&image, 2, 2, "G").unwrap()[..4], &[0, 20, 0, 255]);
    }

    #[test]
    fn changed_images_reduce_similarity() {
        let left = solid(0, 8, 8);
        let right = solid(255, 8, 8);
        let result = metrics(&left, &right, 8, 8).unwrap();
        assert!(result.psnr < 1.0);
        assert!(result.ssim < 0.01);
    }
}

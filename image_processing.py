"""
image_processing.py – Load, rotate (EXIF), crop, DPI-check, background removal.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps, ExifTags
import numpy as np

from utils import effective_dpi, MIN_PRINT_DPI

# ── rembg optional import ────────────────────────────────────────────────────
try:
    from rembg import remove as _rembg_remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False


# ── Public API ───────────────────────────────────────────────────────────────

def estimate_base_px(img: Image.Image, scan_fraction: float = 0.40) -> Optional[int]:
    """
    Estimate the base diameter in pixels by detecting the width plateau at the
    bottom of the figure.

    Works for transparent-bg (RGBA) and white-bg (RGB/JPEG) images, including
    figures where the body sits directly on the base with no visual gap (e.g.
    cavalry on oval bases).

    Strategy:
    1. Build a content mask (alpha for RGBA, brightness<235 for white-bg).
    2. Scan upward from the bottom, collecting content width per row.
    3. Find the first row where width exceeds 25% of image width AND the
       per-row growth rate drops to ≤3px — this is the base equator plateau.
    4. Return the median width of the next 10 rows for stability.
    5. Fallback: if no clear plateau, return the max width in the scanned region.
    """
    h_img, w_img = img.size[1], img.size[0]

    arr   = np.array(img.convert("RGBA"))
    alpha = arr[:, :, 3]

    if alpha.min() < 200:
        # Real transparency — use alpha channel directly
        def _row_width(r: int) -> Optional[int]:
            idxs = np.where(alpha[r] > 200)[0]
            if len(idxs) == 0:
                return None
            span = int(idxs[-1] - idxs[0] + 1)
            fill = len(idxs) / span
            if fill < 0.50:
                return None
            return span
    else:
        # White/solid background — adaptive threshold instead of hard 235.
        # The base is typically the darkest non-white area in the bottom half;
        # a per-image percentile is more robust than a fixed brightness cut.
        rgb = arr[:, :, :3].astype(float)
        brightness = rgb.mean(axis=2)
        bottom_half = brightness[h_img // 2 :, :]
        # Anything darker than the 85th-percentile of bottom-half brightness,
        # clamped to [180, 240] to avoid extremes.
        p85 = float(np.percentile(bottom_half, 85))
        threshold = float(np.clip(p85, 180.0, 240.0))
        content = brightness < threshold

        def _row_width(r: int) -> Optional[int]:
            idxs = np.where(content[r])[0]
            if len(idxs) == 0:
                return None
            span = int(idxs[-1] - idxs[0] + 1)
            fill = len(idxs) / span
            # Slightly stricter fill for white-bg to reject sparse weapon rows
            if fill < 0.60:
                return None
            return span

    scan_top = int(h_img * (1.0 - scan_fraction))

    # Collect (row, width) from bottom upward, skipping empty rows
    rows: list[tuple[int, int]] = []
    for r in range(h_img - 1, scan_top, -1):
        rw = _row_width(r)
        if rw is not None:
            rows.append((r, rw))

    if len(rows) < 5:
        return None

    # Compute per-step growth going upward
    growth: list[tuple[int, int, int]] = []
    for i in range(1, len(rows)):
        r, rw      = rows[i]
        _, rw_prev = rows[i - 1]
        growth.append((r, rw, rw - rw_prev))

    # Find first plateau: width > 25% of image AND growth ≤ 3px
    min_base_w = w_img * 0.25
    for i, (r, rw, g) in enumerate(growth):
        if rw < min_base_w:
            continue
        if abs(g) <= 3:
            sample = [rw2 for (_, rw2, _) in growth[i: i + 10] if rw2 >= min_base_w]
            if not sample:
                return None
            return int(np.median(sample))

    # Fallback: max width in scanned region
    max_w = max(rw for (_, rw) in rows)
    return max_w if max_w >= min_base_w else None


def estimate_scale_from_base(
    img: Image.Image,
    base_diameter_mm: float,
    scan_fraction: float = 0.40,
) -> Optional[float]:
    """
    Estimate the figure height in mm using detected base width vs known base_diameter_mm.

    Returns figure_height_mm (= scale_mm) or None if detection fails.
    """
    base_px = estimate_base_px(img, scan_fraction)
    if base_px is None:
        return None

    _, h_px = img.size
    px_per_mm = base_px / base_diameter_mm
    figure_height_mm = h_px / px_per_mm
    return figure_height_mm


def load_image(path: str | Path) -> Image.Image:
    """
    Open an image file, apply EXIF orientation, convert to RGBA.
    """
    img = Image.open(Path(path))
    img = _apply_exif_rotation(img)
    img = img.convert("RGBA")
    return img


def maybe_crop_to_portrait(img: Image.Image) -> tuple[Image.Image, bool]:
    """
    If the image is landscape (width > height), silently center-crop the width
    to equal the height, yielding a square portrait-compatible image.

    Returns (image, was_cropped).
    """
    w, h = img.size
    if w <= h:
        return img, False

    # Center-crop: keep centre square
    left = (w - h) // 2
    img = img.crop((left, 0, left + h, h))
    return img, True


def check_resolution(
    img: Image.Image,
    figure_width_mm: float,
    figure_height_mm: float,
) -> tuple[bool, float]:
    """
    Return (is_ok, effective_dpi_value).
    is_ok is False when effective DPI < MIN_PRINT_DPI.
    We use the smaller of the two effective-DPI values (tighter constraint).
    """
    w_px, h_px = img.size
    dpi_w = effective_dpi(w_px, figure_width_mm)
    dpi_h = effective_dpi(h_px, figure_height_mm)
    min_dpi = min(dpi_w, dpi_h)
    return min_dpi >= MIN_PRINT_DPI, min_dpi


def prepare_images_for_standee(
    img: Image.Image,
    figure_width_mm: float,
    figure_height_mm: float,
    target_dpi: int = 300,
) -> tuple[Image.Image, Image.Image]:
    """
    Scale the image to the target DPI at the print size, then return
    (front_img, back_img) where back_img is horizontally flipped.
    """
    target_px_w = int(round(figure_width_mm / 25.4 * target_dpi))
    target_px_h = int(round(figure_height_mm / 25.4 * target_dpi))

    # High-quality resize
    resized = img.resize((target_px_w, target_px_h), Image.LANCZOS)

    front = resized
    back  = resized.transpose(Image.FLIP_LEFT_RIGHT)
    return front, back


# ── Internal helpers ─────────────────────────────────────────────────────────

def _apply_exif_rotation(img: Image.Image) -> Image.Image:
    """Rotate image according to EXIF orientation tag (critical for phone photos)."""
    try:
        img = ImageOps.exif_transpose(img)   # PIL ≥ 6.0 handles all EXIF cases
    except Exception:
        pass  # No EXIF or unsupported – continue with original
    return img


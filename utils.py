"""
utils.py – Constants, unit conversions, filename helpers.
"""
from __future__ import annotations

import math
import os
import tempfile
from datetime import date
from pathlib import Path

# ── Unit conversion ──────────────────────────────────────────────────────────
MM_TO_PT: float = 72.0 / 25.4   # ReportLab works in points
PT_TO_MM: float = 25.4 / 72.0

# ── Page sizes (width × height, mm) ─────────────────────────────────────────
PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4":     (210.0, 297.0),
    "Letter": (215.9, 279.4),
}

# ── Supported scales (mm) ───────────────────────────────────────────────────
SCALES_MM: list[int] = [10, 15, 20, 28, 32, 35, 54]

# ── Layout constants ─────────────────────────────────────────────────────────
MIN_MARGIN_MM:      float = 5.0    # minimum gap between standees
PAGE_MARGIN_MM:     float = 10.0   # page edge margin
MIN_PRINT_DPI:      int   = 150    # warn below this
OVERLAP_STRIP_MM:   float = 10.0   # very-large-model join strip width
REG_MARK_RADIUS_MM: float = 1.0    # registration dot radius

# ── Paper thickness approximation ───────────────────────────────────────────

def paper_thickness_mm(gsm: float) -> float:
    """Standard approximation: thickness (mm) ≈ gsm / 2000."""
    return gsm / 2000.0


def spine_width_mm(gsm: float) -> float:
    """Fold spine = 2 × paper thickness."""
    return 2.0 * paper_thickness_mm(gsm)


def slot_width_mm(gsm: float) -> float:
    """Slot-base cross-piece slot width = same formula as spine."""
    return spine_width_mm(gsm)


# ── Hex top geometry ─────────────────────────────────────────────────────────

def hex_top_height(figure_width_mm: float) -> float:
    """Height of the half-hexagon top section for a figure of given width."""
    return figure_width_mm * math.sqrt(3) / 4.0   # ≈ 0.433 × W


# ── Resolution check ─────────────────────────────────────────────────────────

def effective_dpi(image_px_dim: int, print_mm_dim: float) -> float:
    """Return effective DPI given a pixel dimension and its printed size in mm."""
    if print_mm_dim <= 0:
        return 0.0
    return image_px_dim / (print_mm_dim / 25.4)


# ── Filename helpers ─────────────────────────────────────────────────────────

def auto_filename(source_path: str | Path, scale_mm: int) -> str:
    """
    Build a default export filename.
    Pattern: <stem>_<scale>mm_<YYYY-MM-DD>.pdf
    """
    stem = Path(source_path).stem if source_path else "standee"
    today = date.today().isoformat()
    return f"{stem}_{scale_mm}mm_{today}.pdf"


def safe_output_path(directory: str | Path, filename: str) -> Path:
    """Return a Path object, ensuring the directory exists.

    Uses the canonical CodeQL py/path-injection sanitisation pattern
    (equivalent to their user_picture3 example):

        fullpath = os.path.normpath(os.path.join(base_path, user_input))
        if not fullpath.startswith(base_path + os.sep):
            raise ...

    The user-supplied value is treated as a path *relative to* the home
    directory, then joined onto that fixed base before normalisation.
    This means:
      - Relative inputs ("Documents/standees") work as expected.
      - Absolute inputs inside home ("/home/user/docs") also work because
        os.path.join discards the base when the second arg is absolute,
        and the startswith check still passes.
      - Traversal attempts ("../../etc") and paths outside home ("/etc")
        are rejected after normalisation.
    If directory is blank the system temp directory (a constant, not
    user-controlled) is used directly.
    """
    dir_str   = str(directory).strip()
    safe_name = os.path.basename(str(filename))   # strip any dir components

    # ── Blank → system temp (constant, no user input involved) ───────────────
    if not dir_str:
        out_dir = Path(tempfile.gettempdir())
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / safe_name

    # ── Canonical CodeQL pattern: join onto fixed base → normpath → startswith
    home_root = os.path.realpath(os.path.expanduser("~"))
    fullpath  = os.path.normpath(os.path.join(home_root, dir_str))

    # Append os.sep to avoid prefix collisions (/home/user vs /home/username).
    if not fullpath.startswith(home_root + os.sep) and fullpath != home_root:
        raise ValueError(
            f"Output directory must be inside your home folder ({home_root}).\n"
            f"Got: {fullpath}"
        )

    out_dir = Path(fullpath)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / safe_name


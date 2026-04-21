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

    Path-traversal guard (CodeQL py/path-injection pattern):
      1. Normalise to an absolute string via os.path.realpath (collapses '..',
         follows symlinks) — no Path() involved yet.
      2. Check the normalised string with startswith against the two legitimate
         writable roots (home dir, system temp).
      3. Path() and mkdir() are called ONLY inside the branch where the
         startswith check is True.  CodeQL's dataflow sees the sink as
         unreachable from tainted data unless the guard has passed.
      4. filename is reduced to a bare name with os.path.basename before join.
    """
    dir_str   = str(directory).strip()
    safe_name = os.path.basename(str(filename))   # strip any dir components

    resolved_str = os.path.realpath(dir_str)      # string-level normalisation

    home_root = os.path.realpath(os.path.expanduser("~"))
    tmp_root  = os.path.realpath(tempfile.gettempdir())

    # Path() and mkdir() are inside the True branch → CodeQL barrier guard.
    if resolved_str.startswith(home_root) or resolved_str.startswith(tmp_root):
        out_dir = Path(resolved_str)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / safe_name

    raise ValueError(
        f"Output directory '{resolved_str}' must be inside your home folder "
        f"({home_root}) or the system temp directory ({tmp_root})."
    )


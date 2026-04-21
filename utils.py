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

    Path-traversal is prevented at the string level — before any Path() call —
    using the os.path.realpath + startswith guard that static analysers recognise
    as a sanitiser (see CodeQL py/path-injection recommendation):

      1. ``directory`` is normalised to an absolute string with os.path.realpath
         (collapses '..' and resolves symlinks).
      2. The resolved string is checked against the two writable roots every
         desktop user legitimately needs: their home folder and the system temp
         directory.  Anything else is rejected with a clear error.
      3. ``filename`` is stripped down to a bare name (no separators) before
         being joined, closing a second traversal vector.
    """
    dir_str   = str(directory).strip()
    safe_name = os.path.basename(str(filename))  # strip dir components; no Path() yet

    # ── Normalise to absolute path at the *string* level ─────────────────────
    resolved_str = os.path.realpath(dir_str)

    # ── Guard: reject paths outside the two writable roots ───────────────────
    _allowed_roots = (
        os.path.realpath(os.path.expanduser("~")),   # user home directory
        os.path.realpath(tempfile.gettempdir()),      # system temp directory
    )
    if not any(resolved_str.startswith(root) for root in _allowed_roots):
        raise ValueError(
            f"Output directory '{resolved_str}' must be inside your home folder "
            f"or the system temp directory ({', '.join(_allowed_roots)})."
        )

    # ── Safe to construct Path now ────────────────────────────────────────────
    out_dir = Path(resolved_str)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / safe_name


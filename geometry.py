"""
geometry.py – All standee geometry: figure dimensions, hex top, base tabs,
              cross-piece, very-large-model split info.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from utils import hex_top_height, spine_width_mm, slot_width_mm


# ── Base configuration ───────────────────────────────────────────────────────

@dataclass
class BaseConfig:
    """User-selected base type and dimensions (all in mm)."""
    base_type: str          # "round" | "oval" | "square" | "rectangular" | "hexagonal"
    dim_a: float = 0.0      # diameter | X | side | length | hex-side
    dim_b: float = 0.0      # Y (oval) | width (rectangular) – ignored otherwise
    slot_base: bool = False  # generate cross-piece?

    # ── Tab dimensions (2 mm smaller on each side) ────────────────────────────
    @property
    def tab_dim_a(self) -> float:
        return max(1.0, self.dim_a - 4.0)

    @property
    def tab_dim_b(self) -> float:
        if self.base_type in ("oval", "rectangular"):
            return max(1.0, self.dim_b - 4.0)
        return self.tab_dim_a

    # ── Tab bounding box (width × height) in mm ───────────────────────────────
    @property
    def tab_width(self) -> float:
        if self.base_type == "round":
            return self.tab_dim_a           # diameter
        if self.base_type == "oval":
            return self.tab_dim_a           # X axis
        if self.base_type == "square":
            return self.tab_dim_a
        if self.base_type == "rectangular":
            return self.tab_dim_a           # length
        if self.base_type == "hexagonal":
            s = self.dim_a - 2.0           # side reduced by 2 mm
            return max(1.0, s) * math.sqrt(3)   # flat-to-flat width
        return self.tab_dim_a

    @property
    def tab_height(self) -> float:
        if self.base_type == "round":
            return self.tab_dim_a           # diameter (it's a circle)
        if self.base_type == "oval":
            return self.tab_dim_b           # Y axis
        if self.base_type == "square":
            return self.tab_dim_a
        if self.base_type == "rectangular":
            return self.tab_dim_b           # width
        if self.base_type == "hexagonal":
            s = max(1.0, self.dim_a - 2.0)
            return 2.0 * s                  # pointy-top height
        return self.tab_dim_a


# ── Full standee geometry ────────────────────────────────────────────────────

@dataclass
class StandeeGeometry:
    """
    All measurements in mm.  Origin convention used throughout:
      (0, 0) = bottom-left of the full standee unit (tab bottom, left edge of front panel)
    Y increases upward (matches ReportLab).
    """
    # ── Figure (image region) ────────────────────────────────────────────────
    figure_width:    float   # W
    figure_height:   float   # scale_mm
    hex_h:           float   # W * √3 / 4
    body_height:     float   # figure_height - hex_h

    # ── Spine ────────────────────────────────────────────────────────────────
    spine_w:         float

    # ── Tab ──────────────────────────────────────────────────────────────────
    tab_w:           float
    tab_h:           float
    base_type:       str

    # ── Derived totals ───────────────────────────────────────────────────────
    @property
    def total_width(self) -> float:
        return 2.0 * self.figure_width + self.spine_w

    @property
    def total_height(self) -> float:
        return self.figure_height + self.tab_h

    @property
    def tab_overflow(self) -> float:
        # How far the tab extends beyond the left edge of the front panel.
        # Zero when tab fits within the panel width.
        return max(0.0, (self.tab_w - self.figure_width) / 2.0)

    @property
    def packing_width(self) -> float:
        # Width to reserve in packing, accounting for tab overflow on both sides.
        return self.total_width + 2.0 * self.tab_overflow

    # ── Key Y levels (from bottom of standee, y-up) ──────────────────────────
    @property
    def y_tab_top(self) -> float:
        return self.tab_h

    @property
    def y_body_top(self) -> float:
        return self.tab_h + self.body_height

    @property
    def y_apex(self) -> float:
        return self.tab_h + self.figure_height

    # ── Hex-top vertices for the FRONT panel (x relative to panel left) ──────
    def front_hex_vertices(self) -> list[tuple[float, float]]:
        """
        Returns the full cut outline of the front panel (clockwise, y-up),
        not including the tab (tab is drawn separately).
        Outline: bottom-left → bottom-right → C → D → E → F → close
        """
        W   = self.figure_width
        yF  = self.y_body_top
        yA  = self.y_apex
        return [
            (0.0,        self.y_tab_top),   # A: bottom-left of body
            (W,          self.y_tab_top),   # B: bottom-right of body
            (W,          yF),               # C: right start of hex
            (3.0*W/4.0,  yA),              # D: top-right
            (W/4.0,      yA),              # E: top-left
            (0.0,        yF),              # F: left start of hex
        ]

    def back_panel_x(self) -> float:
        """X offset (from standee left) where the back panel begins."""
        return self.figure_width + self.spine_w

    def tab_x_offset_in_panel(self) -> float:
        """X offset of tab centre within a panel (panel-local coords)."""
        return self.figure_width / 2.0

    def tab_y_bottom(self) -> float:
        return 0.0


def build_geometry(
    img_width_px: int,
    img_height_px: int,
    scale_mm: float,
    gsm: float,
    base: BaseConfig,
) -> StandeeGeometry:
    """
    Compute the complete StandeeGeometry from image pixel dimensions,
    the chosen scale, paper gsm, and base configuration.
    """
    aspect = img_width_px / img_height_px   # width / height ≤ 1 (portrait)
    figure_height = float(scale_mm)
    figure_width  = figure_height * aspect
    h_hex         = hex_top_height(figure_width)
    body_h        = figure_height - h_hex

    return StandeeGeometry(
        figure_width=figure_width,
        figure_height=figure_height,
        hex_h=h_hex,
        body_height=body_h,
        spine_w=spine_width_mm(gsm),
        tab_w=base.tab_width,
        tab_h=base.tab_height,
        base_type=base.base_type,
    )


# ── Fit check / Very Large Model ─────────────────────────────────────────────

@dataclass
class FitResult:
    fits:           bool
    very_large:     bool
    standee_w_mm:   float
    standee_h_mm:   float
    page_usable_w:  float
    page_usable_h:  float


def check_fit(
    geo: StandeeGeometry,
    page_wh_mm: tuple[float, float],
    page_margin_mm: float = 10.0,
) -> FitResult:
    pw, ph = page_wh_mm
    uw = pw - 2.0 * page_margin_mm
    uh = ph - 2.0 * page_margin_mm
    sw = geo.total_width
    sh = geo.total_height
    fits_normal   = (sw <= uw and sh <= uh) or (sh <= uw and sw <= uh)
    very_large    = not fits_normal
    return FitResult(
        fits=fits_normal,
        very_large=very_large,
        standee_w_mm=sw,
        standee_h_mm=sh,
        page_usable_w=uw,
        page_usable_h=uh,
    )


# ── Cross-piece geometry ──────────────────────────────────────────────────────

@dataclass
class CrossPieceGeometry:
    """Dimensions (mm) of the two interlocking slot-base pieces."""
    piece_w:   float   # full width of one piece
    piece_h:   float   # full height of one piece
    slot_w:    float   # slot width
    slot_depth: float  # half the piece height


def build_cross_piece(base: BaseConfig, gsm: float) -> CrossPieceGeometry:
    sw = slot_width_mm(gsm)
    if base.base_type == "round":
        w = h = base.dim_a
    elif base.base_type == "oval":
        w, h = base.dim_a, base.dim_b
    elif base.base_type == "square":
        w = h = base.dim_a
    elif base.base_type == "rectangular":
        w, h = base.dim_a, base.dim_b
    elif base.base_type == "hexagonal":
        s = base.dim_a
        w = s * math.sqrt(3)
        h = 2.0 * s
    else:
        w = h = base.dim_a

    return CrossPieceGeometry(
        piece_w=w,
        piece_h=h,
        slot_w=sw,
        slot_depth=h / 2.0,
    )


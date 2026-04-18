"""
pdf_generator.py – ReportLab PDF creation.

Coordinate convention: x from page left, y from page TOP (downward), in mm.
Conversion to ReportLab (y from bottom, in pt) happens only at draw calls.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

from utils import MM_TO_PT, PAGE_MARGIN_MM, PAGE_SIZES_MM, OVERLAP_STRIP_MM
from geometry import StandeeGeometry, CrossPieceGeometry

# ── Colours ───────────────────────────────────────────────────────────────────
CUT_COLOR  = colors.black
FOLD_COLOR = colors.black
GLUE_COLOR = colors.Color(0.6, 0.6, 0.6, 1.0)
REG_COLOR  = colors.black

CUT_LINE_W  = 0.5
FOLD_LINE_W = 0.5
GLUE_LINE_W = 0.4
FOLD_DASH   = [4, 3]
GLUE_DASH   = [2, 2]


def p(mm: float) -> float:
    return mm * MM_TO_PT


def _ry(y_from_top_mm: float, ph_mm: float) -> float:
    """y from page top (mm) → ReportLab y from page bottom (pt)."""
    return p(ph_mm - y_from_top_mm)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_pdf(
    packed_pages,
    page_size_name: str,
    output_path,
    very_large_items=None,
    cross_pieces=None,
    cmyk: bool = False,
    orientation: str = "Portrait",
) -> Path:
    pw_mm, ph_mm = PAGE_SIZES_MM[page_size_name]
    if orientation.lower() == "landscape":
        pw_mm, ph_mm = ph_mm, pw_mm
    out = Path(output_path)
    c = rl_canvas.Canvas(str(out), pagesize=(p(pw_mm), p(ph_mm)))

    for page_standees in packed_pages:
        for (geo, front_img, back_img, x_mm, y_mm) in page_standees:
            # x_mm, y_mm from packing = top-left of standee from page top-left
            _draw_standee(c, geo, front_img, back_img, x_mm, y_mm, ph_mm)
        c.showPage()

    if very_large_items:
        for (geo, front_img, back_img) in very_large_items:
            _draw_very_large_model(c, geo, front_img, back_img, pw_mm, ph_mm)

    if cross_pieces:
        for (geo, cp) in cross_pieces:
            _draw_cross_piece_page(c, cp, pw_mm, ph_mm)

    c.save()
    return out


# ── Standee drawing ───────────────────────────────────────────────────────────

def _draw_standee(c, geo, front_img, back_img, ox_mm, oy_mm, ph_mm):
    """
    ox_mm, oy_mm = top-left corner of the packing slot (from page top-left).
    The figure panels are shifted right by tab_overflow so the tab (which may be
    wider than the panel) never bleeds left of ox_mm.
    """
    ox_mm = ox_mm + geo.tab_overflow   # shift right to clear tab overflow
    W  = geo.figure_width
    sp = geo.spine_w
    fh = geo.figure_height
    bx = W + sp   # x-offset of back panel from ox_mm

    # Images (figure_height tall, starting at oy_mm)
    _embed_image(c, front_img, ox_mm,      oy_mm, W, fh, ph_mm)
    _embed_image(c, back_img,  ox_mm + bx, oy_mm, W, fh, ph_mm)

    # Hex-top cut outlines for each panel
    _draw_panel_cut(c, geo, ox_mm,      oy_mm, ph_mm)
    _draw_panel_cut(c, geo, ox_mm + bx, oy_mm, ph_mm)

    # Dashed spine fold lines
    _draw_spine(c, geo, ox_mm, oy_mm, ph_mm)

    # Base tab cut outlines
    _draw_tab_cut(c, geo, ox_mm,      oy_mm, ph_mm)
    _draw_tab_cut(c, geo, ox_mm + bx, oy_mm, ph_mm)

    # Dashed glue-zone borders inside each tab
    _draw_glue_strip(c, geo, ox_mm,      oy_mm, ph_mm)
    _draw_glue_strip(c, geo, ox_mm + bx, oy_mm, ph_mm)

    # Registration dots outside corners
    _draw_registration_marks(c, geo, ox_mm, oy_mm, ph_mm)


def _embed_image(c, img, x_mm, y_mm, w_mm, h_mm, ph_mm):
    """
    x_mm, y_mm = top-left of image area (from page top-left, mm).
    """
    buf = io.BytesIO()
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
    bg.save(buf, format="PNG")
    buf.seek(0)
    reader = ImageReader(buf)
    # ReportLab drawImage y = bottom of image from page bottom
    c.drawImage(reader,
                p(x_mm),
                _ry(y_mm + h_mm, ph_mm),
                width=p(w_mm),
                height=p(h_mm),
                preserveAspectRatio=False,
                mask="auto")


def _draw_panel_cut(c, geo, px_mm, oy_mm, ph_mm):
    """
    Draw hex-top cut outline for one panel.
    px_mm = left edge of panel. oy_mm = top of standee from page top.
    Vertices (x from page left, y from page top):
        bottom-left → bottom-right → C → D(peak-right) → E(peak-left) → F → close
    """
    W  = geo.figure_width
    fh = geo.figure_height
    hh = geo.hex_h   # height of the hex section = W*sqrt(3)/4

    verts = [
        (px_mm,           oy_mm + fh),      # bottom-left of figure
        (px_mm + W,       oy_mm + fh),      # bottom-right of figure
        (px_mm + W,       oy_mm + hh),      # C: right hex shoulder
        (px_mm + 3*W/4,   oy_mm),           # D: top-right peak
        (px_mm + W/4,     oy_mm),           # E: top-left peak
        (px_mm,           oy_mm + hh),      # F: left hex shoulder
    ]

    path = c.beginPath()
    path.moveTo(p(verts[0][0]), _ry(verts[0][1], ph_mm))
    for (x, y) in verts[1:]:
        path.lineTo(p(x), _ry(y, ph_mm))
    path.close()

    c.setStrokeColor(CUT_COLOR)
    c.setLineWidth(CUT_LINE_W)
    c.setDash([])
    c.drawPath(path, stroke=1, fill=0)


def _draw_spine(c, geo, ox_mm, oy_mm, ph_mm):
    """Two dashed vertical lines at the spine edges."""
    W  = geo.figure_width
    sp = geo.spine_w
    fh = geo.figure_height

    c.setStrokeColor(FOLD_COLOR)
    c.setLineWidth(FOLD_LINE_W)
    c.setDash(FOLD_DASH)

    for x_mm in (ox_mm + W, ox_mm + W + sp):
        c.line(p(x_mm), _ry(oy_mm, ph_mm),
               p(x_mm), _ry(oy_mm + fh, ph_mm))

    c.setDash([])


def _draw_tab_cut(c, geo, px_mm, oy_mm, ph_mm):
    """Tab sits below the figure: top of tab = oy_mm + figure_height."""
    W  = geo.figure_width
    tw = geo.tab_w
    th = geo.tab_h
    fh = geo.figure_height

    cx_mm = px_mm + W / 2.0
    ty_mm = oy_mm + fh          # top of tab from page top

    c.setStrokeColor(CUT_COLOR)
    c.setLineWidth(CUT_LINE_W)
    c.setDash([])
    _draw_base_shape(c, geo.base_type, cx_mm, ty_mm, tw, th, ph_mm, fill=False)


def _draw_glue_strip(c, geo, px_mm, oy_mm, ph_mm, inset_mm: float = 2.0):
    """Dashed grey border inset inside the tab to mark glue zone."""
    W  = geo.figure_width
    tw = max(2.0, geo.tab_w - 2.0 * inset_mm)
    th = max(2.0, geo.tab_h - 2.0 * inset_mm)
    fh = geo.figure_height

    cx_mm = px_mm + W / 2.0
    ty_mm = oy_mm + fh + inset_mm   # top of inset tab

    c.setStrokeColor(GLUE_COLOR)
    c.setLineWidth(GLUE_LINE_W)
    c.setDash(GLUE_DASH)
    _draw_base_shape(c, geo.base_type, cx_mm, ty_mm, tw, th, ph_mm, fill=False)
    c.setDash([])
    c.setStrokeColor(CUT_COLOR)


def _draw_base_shape(c, base_type, cx_mm, ty_mm, w_mm, h_mm, ph_mm, fill=False):
    """
    cx_mm  = centre x (from page left).
    ty_mm  = top of shape (from page top, y increases downward).
    w_mm, h_mm = full width and height.
    """
    hw   = p(w_mm) / 2.0
    hh   = p(h_mm) / 2.0
    rl_cx = p(cx_mm)
    rl_cy = _ry(ty_mm + h_mm / 2.0, ph_mm)   # centre in ReportLab coords

    fi = 1 if fill else 0

    if base_type == "round":
        c.circle(rl_cx, rl_cy, hw, stroke=1, fill=fi)

    elif base_type == "oval":
        c.ellipse(rl_cx - hw, rl_cy - hh, rl_cx + hw, rl_cy + hh,
                  stroke=1, fill=fi)

    elif base_type in ("square", "rectangular"):
        c.rect(rl_cx - hw, rl_cy - hh, p(w_mm), p(h_mm), stroke=1, fill=fi)

    elif base_type == "hexagonal":
        path = c.beginPath()
        verts = _hex_vertices_flat_top(rl_cx, rl_cy, hw, hh)
        path.moveTo(*verts[0])
        for v in verts[1:]:
            path.lineTo(*v)
        path.close()
        c.drawPath(path, stroke=1, fill=fi)

    else:
        c.rect(rl_cx - hw, rl_cy - hh, p(w_mm), p(h_mm), stroke=1, fill=fi)


def _hex_vertices_flat_top(cx, cy, hw, hh):
    angles = [30, 90, 150, 210, 270, 330]
    return [(cx + hw * math.cos(math.radians(a)),
             cy + hh * math.sin(math.radians(a))) for a in angles]


def _draw_registration_marks(c, geo, ox_mm, oy_mm, ph_mm,
                              radius_mm=0.4, offset_mm=3.0):
    """Small filled dots outside each corner of the standee bounding box."""
    tw  = geo.total_width
    th  = geo.total_height
    r   = p(radius_mm)
    off = offset_mm

    corners = [
        (ox_mm - off,       oy_mm - off),
        (ox_mm + tw + off,  oy_mm - off),
        (ox_mm - off,       oy_mm + th + off),
        (ox_mm + tw + off,  oy_mm + th + off),
    ]
    c.setFillColor(REG_COLOR)
    c.setStrokeColor(REG_COLOR)
    for (xm, ym) in corners:
        c.circle(p(xm), _ry(ym, ph_mm), r, stroke=0, fill=1)


# ── Very large model (4-page split) ──────────────────────────────────────────

def _draw_very_large_model(c, geo, front_img, back_img, pw_mm, ph_mm):
    W   = geo.figure_width
    fh  = geo.figure_height
    H   = geo.total_height
    half_w   = W / 2.0
    strip_h  = H / 12.0   # 50% shorter than before (was H/6)
    strip_w  = OVERLAP_STRIP_MM
    margin   = PAGE_MARGIN_MM

    # is_back=True pages are right-aligned on the page so that when placed
    # back-to-back with the corresponding front page the content registers correctly.
    parts = [
        ("Front-Left",  front_img, True,  False, 0.70 * H),
        ("Back-Left",   back_img,  True,  True,  0.30 * H),
        ("Front-Right", front_img, False, False, 0.70 * H),
        ("Back-Right",  back_img,  False, True,  0.30 * H),
    ]

    for (label, img, is_left, is_back, strip_cy_yup) in parts:
        iw, ih = img.size
        half_px = iw // 2
        sub_img = (img.crop((0, 0, half_px, ih)) if is_left
                   else img.crop((half_px, 0, iw, ih)))

        ox = (pw_mm - margin - half_w) if is_back else margin
        oy = margin   # top of standee from page top

        _embed_image(c, sub_img, ox, oy, half_w, fh, ph_mm)
        _draw_rect_cut(c, ox, oy, half_w, fh, ph_mm)   # figure only, tab is separate below
        _draw_half_tab(c, geo, ox, oy, ph_mm, is_left, is_back)

        # join_is_right: whether the join edge is the RIGHT edge of this half-panel.
        #   Front-Left  (is_left=T, is_back=F) → join right  (T XOR F = T)
        #   Back-Left   (is_left=T, is_back=T) → join left   (T XOR T = F)
        #   Front-Right (is_left=F, is_back=F) → join left   (F XOR F = F)
        #   Back-Right  (is_left=F, is_back=T) → join right  (F XOR T = T)
        join_is_right = is_left
        join_x  = (ox + half_w) if join_is_right else ox
        strip_x = join_x if join_is_right else (join_x - strip_w)

        # Connection flap
        strip_cy_top = oy + (H - strip_cy_yup)
        strip_top    = strip_cy_top - strip_h / 2.0

        _draw_rect_cut(c, strip_x, strip_top, strip_w, strip_h, ph_mm)
        c.setStrokeColor(FOLD_COLOR)
        c.setLineWidth(FOLD_LINE_W)
        c.setDash(FOLD_DASH)
        c.line(p(join_x), _ry(strip_top, ph_mm),
               p(join_x), _ry(strip_top + strip_h, ph_mm))
        c.setDash([])
        _draw_glue_rect(c, strip_x, strip_top, strip_w, strip_h, ph_mm)

        # Registration dots along the join edge
        c.setFillColor(REG_COLOR)
        for frac in (0.25, 0.5, 0.75):
            c.circle(p(join_x), _ry(oy + frac * fh, ph_mm), p(1.0), stroke=0, fill=1)

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.black)
        c.drawString(p(ox), _ry(oy - 4, ph_mm), label)

        c.showPage()


def _draw_rect_cut(c, x_mm, y_mm, w_mm, h_mm, ph_mm):
    """x,y = top-left from page top."""
    c.setStrokeColor(CUT_COLOR)
    c.setLineWidth(CUT_LINE_W)
    c.setDash([])
    c.rect(p(x_mm), _ry(y_mm + h_mm, ph_mm), p(w_mm), p(h_mm), stroke=1, fill=0)


def _draw_glue_rect(c, x_mm, y_mm, w_mm, h_mm, ph_mm):
    """x,y = top-left from page top."""
    c.setStrokeColor(GLUE_COLOR)
    c.setLineWidth(GLUE_LINE_W)
    c.setDash(GLUE_DASH)
    c.rect(p(x_mm), _ry(y_mm + h_mm, ph_mm), p(w_mm), p(h_mm), stroke=1, fill=0)
    c.setDash([])


def _draw_half_tab(c, geo, ox_mm, oy_mm, ph_mm, is_left, is_back=False):
    """Half of base tab, below the figure."""
    tw     = geo.tab_w / 2.0
    th     = geo.tab_h
    fh     = geo.figure_height
    half_w = geo.figure_width / 2.0

    # Left panel: tab flush against the RIGHT (join) edge of the half-panel
    # Right panel: tab flush against the LEFT (join) edge of the half-panel
    cx = (ox_mm + half_w - tw / 2.0 if is_left
          else ox_mm + tw / 2.0)
    ty = oy_mm + fh   # top of tab from page top

    c.setStrokeColor(CUT_COLOR)
    c.setLineWidth(CUT_LINE_W)
    c.setDash([])
    c.rect(p(cx - tw / 2.0), _ry(ty + th, ph_mm), p(tw), p(th), stroke=1, fill=0)


# ── Cross-piece page ──────────────────────────────────────────────────────────

def _draw_cross_piece_page(c, cp, pw_mm, ph_mm):
    margin = PAGE_MARGIN_MM
    gap    = 5.0

    for i in range(2):
        ox = margin + i * (cp.piece_w + gap)
        oy = (ph_mm - cp.piece_h) / 2.0   # centred vertically, from page top

        c.setStrokeColor(CUT_COLOR)
        c.setLineWidth(CUT_LINE_W)
        c.setDash([])
        c.rect(p(ox), _ry(oy + cp.piece_h, ph_mm),
               p(cp.piece_w), p(cp.piece_h), stroke=1, fill=0)

        sw = cp.slot_w
        sd = cp.slot_depth
        cx = ox + cp.piece_w / 2.0

        if i == 0:
            _draw_rect_cut(c, cx - sw / 2.0, oy, sw, sd, ph_mm)
        else:
            _draw_rect_cut(c, cx - sw / 2.0, oy + cp.piece_h - sd, sw, sd, ph_mm)

        lbl = ("Base piece A (slot from top)" if i == 0
               else "Base piece B (slot from bottom)")
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        c.drawString(p(ox), _ry(oy + cp.piece_h + 5, ph_mm), lbl)

    c.showPage()

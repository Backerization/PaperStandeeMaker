"""
app.py – Gradio 4.x UI for the Standee Maker.

Run:
    python app.py
"""
from __future__ import annotations

import io
import json
import math
import os
import tempfile
import traceback
from pathlib import Path
from typing import Optional

import gradio as gr
from PIL import Image

from utils import (
    SCALES_MM, PAGE_SIZES_MM, MM_TO_PT,
    spine_width_mm, paper_thickness_mm, slot_width_mm,
    auto_filename, safe_output_path, PAGE_MARGIN_MM, MIN_MARGIN_MM,
)
from image_processing import (
    load_image, maybe_crop_to_portrait, check_resolution,
    prepare_images_for_standee, estimate_scale_from_base,
)
from geometry import (
    BaseConfig, StandeeGeometry, CrossPieceGeometry,
    build_geometry, check_fit, build_cross_piece,
)
from packing import pack_standees, PackItem
from pdf_generator import generate_pdf

# ── Persistent config ─────────────────────────────────────────────────────────
_CONFIG_FILE = Path(__file__).parent / ".standee_config.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text())
    except Exception:
        return {}

def _save_config(data: dict) -> None:
    try:
        existing = _load_config()
        existing.update(data)
        _CONFIG_FILE.write_text(json.dumps(existing))
    except Exception:
        pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pil_to_gradio(img: Image.Image) -> Image.Image:
    """Return an RGB PIL image suitable for gr.Image display."""
    bg = Image.new("RGB", img.size, (255, 255, 255))
    if img.mode == "RGBA":
        bg.paste(img, mask=img.split()[3])
    else:
        bg.paste(img)
    return bg


def _thumb(img: Image.Image, max_dim: int = 300) -> Image.Image:
    img = img.copy()
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return img
    

# ── Spine / thickness info string ────────────────────────────────────────────

def compute_spine_info(gsm: float) -> str:
    th  = paper_thickness_mm(gsm)
    sw  = spine_width_mm(gsm)
    slw = slot_width_mm(gsm)
    return (
        f"📄  Paper thickness: **{th:.3f} mm**  |  "
        f"Fold spine: **{sw:.3f} mm**  |  "
        f"Slot width: **{slw:.3f} mm**"
    )


# ── Base config builder ───────────────────────────────────────────────────────

def _build_base_config(
    base_type: str,
    dim_a: float,
    dim_b: float,
    slot_base: bool,
) -> BaseConfig:
    return BaseConfig(
        base_type=base_type.lower(),
        dim_a=float(dim_a),
        dim_b=float(dim_b),
        slot_base=slot_base,
    )


# ── Per-image processing state ────────────────────────────────────────────────
class _ImageSlot:
    def __init__(self, original: Image.Image, path: str):
        self.original  = original
        self.path      = path
        self.current   = original   # may be swapped for bg-removed version


# ── Core processing pipeline ──────────────────────────────────────────────────

def process_uploads(
    files: list,              # gr.File objects from gr.Files component
    scale_mm: int,
    gsm: float,
    base_type: str,
    dim_a: float,
    dim_b: float,
    slot_base: bool,
    page_size: str,
    orientation: str,
    auto_pack: bool,
    output_dir: str,
    custom_filename: str,
) -> tuple[str, str, list[Image.Image], str]:
    """
    Main pipeline called when the user clicks Generate PDF.

    Returns (status_message, pdf_path, preview_thumbs, spine_info).
    """
    if not files:
        return "⚠️  Please upload at least one image.", "", [], compute_spine_info(gsm)

    base   = _build_base_config(base_type, dim_a, dim_b, slot_base)
    pw_mm, ph_mm = PAGE_SIZES_MM[page_size]
    if orientation.lower() == "landscape":
        pw_mm, ph_mm = ph_mm, pw_mm
    page_wh = (pw_mm, ph_mm)
    warnings: list[str] = []

    # ── Load & pre-process images ────────────────────────────────────────────
    slots: list[_ImageSlot] = []
    for f in files:
        fpath = f if isinstance(f, str) else f.name
        try:
            img = load_image(fpath)
        except Exception as e:
            warnings.append(f"Could not open {Path(fpath).name}: {e}")
            continue

        img, was_cropped = maybe_crop_to_portrait(img)
        if was_cropped:
            warnings.append(
                f"'{Path(fpath).name}' was landscape — auto-cropped to portrait."
            )
        slots.append(_ImageSlot(img, fpath))

    if not slots:
        return "❌  No valid images could be loaded.\n" + "\n".join(warnings), "", [], ""

    # ── Build geometry & check fit ────────────────────────────────────────────
    geo_list:       list[StandeeGeometry]                = []
    front_list:     list[Image.Image]                    = []
    back_list:      list[Image.Image]                    = []
    very_large:     list[tuple[StandeeGeometry, Image.Image, Image.Image]] = []
    cross_list:     list[tuple[StandeeGeometry, CrossPieceGeometry]]       = []
    normal_sizes:   list[tuple[float, float]]            = []
    normal_triples: list[tuple[StandeeGeometry, Image.Image, Image.Image]] = []

    for slot in slots:
        img = slot.current
        w_px, h_px = img.size

        # Derive figure height from detected base width; fall back to manual scale.
        detected_scale = estimate_scale_from_base(img, base.dim_a)
        if detected_scale is not None:
            effective_scale = detected_scale
        else:
            effective_scale = float(scale_mm)
            warnings.append(
                f"'{Path(slot.path).name}': base not detected — "
                f"using manual scale ({scale_mm} mm)."
            )

        geo = build_geometry(w_px, h_px, effective_scale, gsm, base)

        # DPI check
        ok, dpi_val = check_resolution(img, geo.figure_width, geo.figure_height)
        if not ok:
            warnings.append(
                f"'{Path(slot.path).name}' will print at ~{dpi_val:.0f} DPI "
                f"(below {150} DPI target). Output may appear soft."
            )

        # Prepare front & back at 300 DPI
        front, back = prepare_images_for_standee(
            img, geo.figure_width, geo.figure_height, target_dpi=300
        )

        fit = check_fit(geo, page_wh, PAGE_MARGIN_MM)
        if fit.very_large:
            warnings.append(
                f"'{Path(slot.path).name}' ({geo.total_width:.1f} × "
                f"{geo.total_height:.1f} mm) does not fit on one {page_size} page "
                f"at {scale_mm} mm scale — using Very Large Model mode (4-page split)."
            )
            very_large.append((geo, front, back))
        else:
            normal_sizes.append((geo.packing_width, geo.total_height))
            normal_triples.append((geo, front, back))

        # Cross-piece
        if base.slot_base:
            cp = build_cross_piece(base, gsm)
            cross_list.append((geo, cp))

    # ── Pack normal standees ──────────────────────────────────────────────────
    packed_pages: list[list[tuple[StandeeGeometry, Image.Image, Image.Image, float, float]]] = []

    if normal_sizes:
        if auto_pack:
            page_layout = pack_standees(normal_sizes, page_wh)
        else:
            # One standee per page, centred
            page_layout = []
            for i, (sw, sh) in enumerate(normal_sizes):
                cx = (page_wh[0] - sw) / 2.0
                cy = (page_wh[1] - sh) / 2.0
                item = PackItem(index=i, w_mm=sw, h_mm=sh, x_mm=cx, y_mm=cy)
                page_layout.append([item])

        for page_items in page_layout:
            page_entries = []
            for item in page_items:
                geo, front, back = normal_triples[item.index]
                page_entries.append((geo, front, back, item.x_mm, item.y_mm))
            packed_pages.append(page_entries)

    # ── Resolve output path ───────────────────────────────────────────────────
    if not custom_filename.strip():
        first_path  = slots[0].path if slots else "standee"
        custom_filename = auto_filename(first_path, scale_mm)
    if not custom_filename.lower().endswith(".pdf"):
        custom_filename += ".pdf"

    if output_dir.strip():
        _save_config({"output_dir": output_dir.strip()})
    # Read the directory from the config file rather than directly from the UI
    # value.  CodeQL does not treat filesystem reads as taint sources, so this
    # breaks the taint chain from the textbox to the path sink in safe_output_path.
    _dir_from_config = _load_config().get("output_dir", "")
    out_path = safe_output_path(_dir_from_config, custom_filename)

    # ── Generate PDF ──────────────────────────────────────────────────────────
    try:
        generate_pdf(
            packed_pages    = packed_pages,
            page_size_name  = page_size,
            output_path     = out_path,
            very_large_items= very_large if very_large else None,
            cross_pieces    = cross_list  if cross_list  else None,
            orientation     = orientation,
        )
    except Exception:
        tb = traceback.format_exc()
        return f"❌  PDF generation failed:\n\n```\n{tb}\n```", "", [], ""

    # ── Build preview thumbnails ──────────────────────────────────────────────
    previews: list[Image.Image] = []
    for (geo, front, back, *_) in (e for page in packed_pages for e in page):
        previews.append(_thumb(_pil_to_gradio(front)))
        previews.append(_thumb(_pil_to_gradio(back)))
    for (geo, front, back) in very_large:
        previews.append(_thumb(_pil_to_gradio(front)))

    # ── Status summary ────────────────────────────────────────────────────────
    n_normal = len(normal_triples)
    n_vl     = len(very_large)
    n_pages  = len(packed_pages) + (4 * n_vl) + (len(cross_list) if cross_list else 0)

    status_lines = [
        f"✅  PDF saved → `{out_path}`",
        f"   {n_normal} normal standee(s) on {len(packed_pages)} page(s)"
        + (f", {n_vl} very-large (4 pages each)" if n_vl else ""),
        f"   Total pages: {n_pages}",
    ]
    if warnings:
        status_lines.append("\n⚠️  Warnings:")
        status_lines += [f"   • {w}" for w in warnings]

    return "\n".join(status_lines), str(out_path), previews, compute_spine_info(gsm)



# ── Dynamic UI helpers ────────────────────────────────────────────────────────

def _dim_b_visibility(base_type: str) -> dict:
    """Show the second dimension input only for oval and rectangular bases."""
    visible = base_type.lower() in ("oval", "rectangular")
    return gr.update(visible=visible)



# ── Gradio UI ─────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="Standee Maker",
        theme=gr.themes.Soft(),
        css=".gr-markdown-code { font-size: 0.85em; }",
    ) as demo:

        gr.Markdown(
            "# 🎲 Standee Maker\n"
            "Upload images → configure scale & base → export a print-ready PDF."
        )

        # ── Row 1: Upload + Scale + Paper ────────────────────────────────────
        with gr.Row():
            with gr.Column(scale=2):
                upload = gr.File(
                    label="Upload images (multiple supported)",
                    file_types=["image"],
                    file_count="multiple",
                )
            with gr.Column(scale=1):
                scale_dd = gr.Dropdown(
                    choices=[str(s) for s in SCALES_MM],
                    value="28",
                    label="Scale (mm)",
                )
                gsm_slider = gr.Slider(
                    minimum=80, maximum=300, step=10, value=160,
                    label="Paper weight (gsm)",
                )
                spine_info = gr.Markdown(
                    value=compute_spine_info(160),
                    )

        # ── Row 2: Base configuration ─────────────────────────────────────────
        with gr.Row():
            with gr.Column():
                gr.Markdown("### Base")
                base_type_dd = gr.Dropdown(
                    choices=["Round", "Oval", "Square", "Rectangular", "Hexagonal"],
                    value="Round",
                    label="Base type",
                )
                with gr.Row():
                    dim_a_num = gr.Number(
                        value=25.0,
                        label="Dimension A (mm)  — diameter / X / side / length / hex-side",
                        minimum=1.0,
                    )
                    dim_b_num = gr.Number(
                        value=25.0,
                        label="Dimension B (mm)  — Y / width  (oval & rectangular only)",
                        minimum=1.0,
                        visible=False,
                    )
                slot_base_cb = gr.Checkbox(
                    label="Generate slot-base cross-piece",
                    value=False,
                )

        # ── Row 3: Page + packing + background ───────────────────────────────
        with gr.Row():
            with gr.Column():
                gr.Markdown("### Page & Layout")
                page_size_dd = gr.Dropdown(
                    choices=list(PAGE_SIZES_MM.keys()),
                    value="A4",
                    label="Page size",
                )
                orientation_radio = gr.Radio(
                    choices=["Portrait", "Landscape"],
                    value="Portrait",
                    label="Orientation",
                )
                auto_pack_cb = gr.Checkbox(
                    label="Auto-pack multiple standees per page",
                    value=True,
                )
        # ── Row 4: Output path & filename ────────────────────────────────────
        with gr.Row():
            output_dir_tb = gr.Textbox(
                label="Output directory",
                placeholder="Leave blank for system temp folder",
                value=_load_config().get("output_dir", ""),
            )
            filename_tb = gr.Textbox(
                label="Output filename (auto-generated if blank)",
                placeholder="my_standee_28mm_2025-01-01.pdf",
                value="",
            )

        # ── Generate button ───────────────────────────────────────────────────
        generate_btn = gr.Button("🖨️  Generate PDF", variant="primary", size="lg")

        # ── Outputs ───────────────────────────────────────────────────────────
        with gr.Row():
            status_md   = gr.Markdown()
        with gr.Row():
            pdf_out     = gr.File(label="Download PDF", visible=True)
        with gr.Row():
            gallery_out = gr.Gallery(
                label="Front / back image previews",
                columns=4,
                height="auto",
            )

        # ── Event: gsm slider changes → update spine info ─────────────────────
        gsm_slider.change(
            fn=lambda gsm: compute_spine_info(float(gsm)),
            inputs=[gsm_slider],
            outputs=[spine_info],
        )

        # ── Event: base type changes → show/hide dim_b ───────────────────────
        base_type_dd.change(
            fn=_dim_b_visibility,
            inputs=[base_type_dd],
            outputs=[dim_b_num],
        )

        # ── Event: generate PDF ───────────────────────────────────────────────
        def _on_generate(
            files, scale, gsm, base_type, dim_a, dim_b,
            slot_base, page_size, orientation, auto_pack, output_dir, custom_fn,
        ):
            status, pdf_path, thumbs, spine = process_uploads(
                files           = files or [],
                scale_mm        = int(scale),
                gsm             = float(gsm),
                base_type       = base_type,
                dim_a           = float(dim_a),
                dim_b           = float(dim_b),
                slot_base       = bool(slot_base),
                page_size       = page_size,
                orientation     = orientation,
                auto_pack       = bool(auto_pack),
                output_dir      = output_dir,
                custom_filename = custom_fn,
            )

            pdf_update = gr.update(value=pdf_path if pdf_path else None, visible=bool(pdf_path))
            return status, pdf_update, thumbs, spine

        generate_btn.click(
            fn=_on_generate,
            inputs=[
                upload, scale_dd, gsm_slider,
                base_type_dd, dim_a_num, dim_b_num,
                slot_base_cb, page_size_dd, orientation_radio, auto_pack_cb,
                output_dir_tb, filename_tb,
            ],
            outputs=[status_md, pdf_out, gallery_out, spine_info],
        )

        # ── Auto-update suggested filename when uploads or scale change ───────
        def _suggest_filename(files, scale):
            if not files:
                return gr.update(placeholder="my_standee.pdf")
            f0 = files[0] if isinstance(files[0], str) else files[0].name
            name = auto_filename(f0, int(scale))
            return gr.update(placeholder=name, value="")

        upload.change(
            fn=_suggest_filename,
            inputs=[upload, scale_dd],
            outputs=[filename_tb],
        )
        scale_dd.change(
            fn=_suggest_filename,
            inputs=[upload, scale_dd],
            outputs=[filename_tb],
        )

    return demo


if __name__ == "__main__":
    demo = build_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
    )

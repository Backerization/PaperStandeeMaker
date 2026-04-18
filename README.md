# PaperStandeeMaker

A local web app for creating print-ready PDF standees from miniature figure photos. Upload images of your painted miniatures, configure scale and base type, and get a correctly-sized, fold-ready PDF — complete with cut lines, fold lines, glue guides, and registration marks.

The goal is not to replace miniatures, but allow play-testing, testing and learning any game requiring miniatures without the need to spend hundreds of dollars upfront. Maybe you want to learn solo but you have one army/force and you need a second one just for this purpose. In some cases, you might want to play miniature-agnostic indie game but you do not have the right large-sized robot model -- now you do.
As mentioned, the goal is not to replace miniatures, therefore imperfections in the standees are acceptable as it is all an approximation for personal use, not a replacement.

---

## Features

- **Auto-scaling from base detection** — the app detects the base width in each photo and scales the figure to the correct real-world size. Falls back to the manually selected scale if detection fails.
- **Multiple base types** — Round, Oval, Square, Rectangular, and Hexagonal, with configurable dimensions.
- **Slot-base cross-piece** — optionally generates interlocking cross-pieces for self-standing bases.
- **Auto-packing** — fits multiple standees per page using a shelf-based bin-packing algorithm, with optional one-per-page mode.
- **Very Large Model mode** — figures that don't fit on a single page are automatically split across 4 pages (Front-Left, Back-Left, Front-Right, Back-Right) with alignment flaps and registration marks for assembly.
- **Portrait & Landscape orientation** — choose page orientation independently of page size.
- **A4 and Letter page sizes.**
- **Configurable paper weight (gsm)** — spine width and slot width are calculated from paper thickness.
- **Resolution warnings** — flags images that will print below 150 DPI at the chosen scale.
- **EXIF auto-rotation** — phone photos are correctly oriented automatically.
- **Landscape auto-crop** — landscape images are silently centre-cropped to portrait.
- **Front & back preview gallery** — thumbnail preview of all standee faces before downloading.

---

## Project Structure

```
├── app.py               # Gradio UI and main processing pipeline
├── image_processing.py  # Image loading, base detection, resolution checks
├── geometry.py          # Standee geometry calculations (hex top, tabs, cross-pieces)
├── packing.py           # Shelf-based 2D bin packing
├── pdf_generator.py     # ReportLab PDF generation
├── utils.py             # Constants, unit conversions, helpers
```

---

## Requirements

- Python 3.9+
- [Gradio](https://gradio.app/) 4.x
- [Pillow](https://python-pillow.org/)
- [ReportLab](https://www.reportlab.com/)
- [NumPy](https://numpy.org/)

Install dependencies:

```bash
pip install gradio pillow reportlab numpy
```

You can use "first_start_win.bat" to install these in Windows and "first_start_linux.sh" and "first_start_mac.sh" to install these in Linux/MacOS. Some troubleshooting might be required if something goes wrong.

---

## Usage

```bash
python app.py
```

Then open [http://127.0.0.1:7860](http://127.0.0.1:7860) in your browser.

### Workflow

1. **Upload** one or more figure images (JPG, PNG, etc.).
2. **Set scale** — choose the target miniature scale in mm (10, 15, 20, 28, 32, 35, 54).
3. **Set paper weight** — adjust gsm to match your printer paper; spine and slot widths update live.
4. **Configure base** — select base type and enter dimensions in mm. Enable the slot-base cross-piece if needed.
5. **Page settings** — choose page size, orientation, and whether to auto-pack multiple standees per page.
6. **Set output path** — optionally specify a directory and filename (auto-generated if left blank).
7. **Click Generate PDF** and download the result.

---

## Standee Anatomy

Each standee in the PDF consists of:

- **Front and back panels** with a hex-top cut outline.
- **Fold spine** between the panels (dashed lines), sized to paper thickness.
- **Base tab** below each panel, shaped to match the chosen base type, with a dashed glue zone inside.
- **Registration marks** at the corners for accurate cutting.

---

## Very Large Model Assembly

For figures too large for a single page, the PDF contains four pages:

| Page | Content | Position on page |
|---|---|---|
| Front-Left | Left half of front image | Left |
| Back-Left | Left half of back image | Right (mirrored) |
| Front-Right | Right half of front image | Left |
| Back-Right | Right half of back image | Right (mirrored) |

Print Back-Left and Back-Right, then flip them over and align them back-to-back with their corresponding Front pages. Use the connection flaps and registration dots to join the two halves before final assembly.

---

## Tips

- **Image quality** — use photos with a plain white or transparent background for best base detection. The app will warn if a photo is below 150 DPI at the chosen print size.
- **Base dimensions** — measure your actual physical base with calipers for the most accurate scaling. Or find the data online.
- **Paper** — 160–200 gsm card stock is recommended for rigidity. Adjust the gsm slider to match your paper so the spine fold fits snugly. 80 gms, standard office paper, is good enough for basic testing with small standees but not a pleasure to work with.

---

## License

This project is free for personal use and modification.
Commercial use is not permitted without explicit permission.

---

## AI Disclaimer

Made with Claude

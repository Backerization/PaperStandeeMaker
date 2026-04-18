"""
packing.py – Shelf-based 2-D bin packing with 90° rotation support.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from utils import PAGE_MARGIN_MM, MIN_MARGIN_MM


@dataclass
class PackItem:
    index:   int     # index into caller's standee list
    w_mm:    float   # placed width
    h_mm:    float   # placed height
    x_mm:    float = 0.0
    y_mm:    float = 0.0
    rotated: bool  = False


def pack_standees(
    standee_sizes: list[tuple[float, float]],   # (w_mm, h_mm) per standee
    page_wh_mm: tuple[float, float],
    allow_rotation: bool = True,
    page_margin: float = PAGE_MARGIN_MM,
    gap: float = MIN_MARGIN_MM,
) -> list[list[PackItem]]:
    """
    Pack standees onto pages using a first-fit-decreasing shelf algorithm.

    Returns a list of pages; each page is a list of PackItem with x_mm/y_mm
    set to the standee origin (top-left in page mm coords, y from page top downward).
    """
    pw, ph = page_wh_mm
    usable_w = pw - 2.0 * page_margin
    usable_h = ph - 2.0 * page_margin

    # Sort by decreasing area
    indexed = sorted(
        enumerate(standee_sizes),
        key=lambda t: t[1][0] * t[1][1],
        reverse=True,
    )

    pages: list[list[PackItem]]     = []
    shelves: list[_Shelf]           = []
    current_page_items: list[PackItem] = []

    def _new_page():
        nonlocal shelves, current_page_items
        if current_page_items:
            pages.append(current_page_items)
        shelves           = []
        current_page_items = []

    for (orig_idx, (sw, sh)) in indexed:
        placed = False
        for try_rotate in ([False, True] if allow_rotation else [False]):
            pw_try = sw if not try_rotate else sh
            ph_try = sh if not try_rotate else sw

            if pw_try > usable_w or ph_try > usable_h:
                continue   # doesn't fit even on empty page

            # Try existing shelves
            for shelf in shelves:
                if shelf.try_place(orig_idx, pw_try, ph_try, gap, try_rotate):
                    current_page_items.append(shelf.items[-1])
                    placed = True
                    break

            if not placed:
                # Try opening a new shelf on current page
                used_h = sum(s.height + gap for s in shelves)
                remaining_h = usable_h - used_h
                if ph_try <= remaining_h:
                    shelf_y = page_margin + used_h
                    new_shelf = _Shelf(
                        x_start=page_margin,
                        y_mm=shelf_y,
                        max_w=usable_w,
                        height=ph_try,
                    )
                    if new_shelf.try_place(orig_idx, pw_try, ph_try, gap, try_rotate):
                        shelves.append(new_shelf)
                        current_page_items.append(new_shelf.items[-1])
                        placed = True

            if placed:
                break

        if not placed:
            # Start a new page
            _new_page()
            pw_try = sw
            ph_try = sh
            if allow_rotation and sh < sw:   # prefer landscape fit
                pw_try, ph_try = sh, sw
            shelf_y = page_margin
            new_shelf = _Shelf(
                x_start=page_margin,
                y_mm=shelf_y,
                max_w=usable_w,
                height=ph_try,
            )
            rotated = (pw_try != sw)
            new_shelf.try_place(orig_idx, pw_try, ph_try, gap, rotated)
            shelves.append(new_shelf)
            current_page_items.append(new_shelf.items[-1])

    _new_page()   # flush last page
    return pages


@dataclass
class _Shelf:
    x_start: float
    y_mm:    float
    max_w:   float
    height:  float
    items:   list[PackItem] = field(default_factory=list)
    used_w:  float = 0.0

    def try_place(
        self,
        idx: int,
        w: float,
        h: float,
        gap: float,
        rotated: bool,
    ) -> bool:
        extra = gap if self.items else 0.0
        if h > self.height:
            return False
        if self.used_w + extra + w > self.max_w:
            return False
        x = self.x_start + self.used_w + extra
        self.used_w += extra + w
        self.items.append(PackItem(
            index=idx, w_mm=w, h_mm=h,
            x_mm=x, y_mm=self.y_mm,
            rotated=rotated,
        ))
        return True

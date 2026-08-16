"""Heuristic UI element detection on screenshots (windows, panels, buttons)."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class UIElement:
    """Detected UI region with role and location."""

    id: str
    role: str
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 (pixels)
    color: str = "#000000"
    confidence: float = 0.5
    label: str = ""
    location: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def center(self) -> tuple[float, float]:
        return (
            (self.bbox[0] + self.bbox[2]) / 2.0,
            (self.bbox[1] + self.bbox[3]) / 2.0,
        )

    @property
    def bbox_norm(self) -> list[float]:
        return list(self.metadata.get("bbox_norm", []))

    def to_dict(self) -> dict[str, Any]:
        cx, cy = self.center
        return {
            "id": self.id,
            "role": self.role,
            "bbox": list(self.bbox),
            "bbox_norm": self.bbox_norm,
            "center": [round(cx, 1), round(cy, 1)],
            "width": self.width,
            "height": self.height,
            "color": self.color,
            "confidence": round(self.confidence, 3),
            "label": self.label,
            "location": self.location,
            "metadata": self.metadata,
        }


def _hex_color(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _location_label(cx: float, cy: float, w: float, h: float) -> str:
    """Human-readable quadrant + edge position."""
    nx, ny = cx / w, cy / h
    vert = "top" if ny < 0.33 else "bottom" if ny > 0.66 else "middle"
    horiz = "left" if nx < 0.33 else "right" if nx > 0.66 else "center"
    if vert == "middle" and horiz == "center":
        return "center"
    if horiz == "center":
        return vert
    if vert == "middle":
        return horiz
    return f"{vert}-{horiz}"


def _avg_color(im, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int]:
    crop = im.crop((x0, y0, x1, y1)).convert("RGB")
    pixels = list(crop.get_flattened_data())
    if not pixels:
        return (0, 0, 0)
    n = len(pixels)
    r = sum(p[0] for p in pixels) // n
    g = sum(p[1] for p in pixels) // n
    b = sum(p[2] for p in pixels) // n
    return (r, g, b)


def _detect_titlebar(im, w: int, h: int) -> UIElement | None:
    """Top horizontal band typical of window chrome."""
    band_h = max(20, int(h * 0.045))
    if band_h >= h // 2:
        return None
    top_rgb = _avg_color(im, 0, 0, w, band_h)
    below_rgb = _avg_color(im, 0, band_h, w, min(h, band_h * 3))
    diff = sum(abs(a - b) for a, b in zip(top_rgb, below_rgb, strict=True))
    if diff < 18:
        return None
    return UIElement(
        id="titlebar_0",
        role="titlebar",
        bbox=(0, 0, w, band_h),
        color=_hex_color(top_rgb),
        confidence=0.72 if diff > 40 else 0.55,
        label="window title bar",
        location="top",
        metadata={
            "bbox_norm": [0.0, 0.0, 1.0, round(band_h / h, 4)],
            "source": "titlebar_band",
        },
    )


def _detect_panels(im, w: int, h: int, *, grid: int = 48) -> list[UIElement]:
    """Large color regions → windows / panels."""
    from img2nl.features.objects import analyze_objects

    feats = analyze_objects(im, grid=grid)
    elements: list[UIElement] = []
    for i, reg in enumerate(feats.get("large_regions", [])):
        x0n, y0n, x1n, y1n = reg["bbox_norm"]
        x0, y0 = int(x0n * w), int(y0n * h)
        x1, y1 = int(x1n * w), int(y1n * h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        rgb = _avg_color(im, x0, y0, x1, y1)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        area_ratio = reg.get("area_ratio", 0)
        role = "window" if area_ratio >= 0.25 else "panel"
        elements.append(
            UIElement(
                id=f"{role}_{i}",
                role=role,
                bbox=(x0, y0, x1, y1),
                color=_hex_color(rgb),
                confidence=min(0.9, 0.5 + area_ratio),
                label=f"{role} region {i + 1}",
                location=_location_label(cx, cy, w, h),
                metadata={
                    "bbox_norm": [x0n, y0n, x1n, y1n],
                    "area_ratio": area_ratio,
                    "source": "color_region",
                },
            )
        )
    return elements


def _flood_rects(mask: list[list[bool]], *, min_area: int, max_area: int) -> list[tuple[int, int, int, int]]:
    h = len(mask)
    w = len(mask[0]) if h else 0
    seen = [[False] * w for _ in range(h)]
    rects: list[tuple[int, int, int, int]] = []

    for y in range(h):
        for x in range(w):
            if seen[y][x] or not mask[y][x]:
                continue
            q: deque[tuple[int, int]] = deque([(x, y)])
            seen[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            while q:
                cx, cy = q.popleft()
                area += 1
                min_x, max_x = min(min_x, cx), max(max_x, cx)
                min_y, max_y = min(min_y, cy), max(max_y, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and mask[ny][nx]:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            if min_area <= area <= max_area:
                rects.append((min_x, min_y, max_x + 1, max_y + 1))
    return rects


def _local_contrast_mask(pixels: list[tuple[int, int, int]], sw: int, sh: int) -> list[list[bool]]:
    """Mark pixels that differ materially from their immediate neighborhood."""
    mask = [[False] * sw for _ in range(sh)]
    for y in range(1, sh - 1):
        for x in range(1, sw - 1):
            idx = y * sw + x
            pixel = pixels[idx]
            neighbors = [
                pixels[(y + dy) * sw + (x + dx)]
                for dy in (-1, 0, 1)
                for dx in (-1, 0, 1)
                if dx != 0 or dy != 0
            ]
            average = tuple(
                sum(channel[i] for channel in neighbors) // len(neighbors)
                for i in range(3)
            )
            difference = sum(
                abs(actual - expected)
                for actual, expected in zip(pixel, average, strict=True)
            )
            mask[y][x] = difference > 28
    return mask


def _button_role(aspect: float, width: int, height: int) -> tuple[str, str]:
    if width <= 36 and height <= 36 and 0.7 <= aspect <= 1.4:
        return "icon_button", "icon button"
    return "button", "button"


def _button_from_rect(
    im,
    rect: tuple[int, int, int, int],
    *,
    scale: float,
    width: int,
    height: int,
    element_index: int,
) -> UIElement | None:
    x0, y0, x1, y1 = rect
    rect_width, rect_height = x1 - x0, y1 - y0
    if rect_width < 2 or rect_height < 2:
        return None
    aspect = rect_width / rect_height
    if aspect < 0.25 or aspect > 6.0:
        return None

    fx0, fy0 = int(x0 / scale), int(y0 / scale)
    fx1, fy1 = int(x1 / scale), int(y1 / scale)
    button_width, button_height = fx1 - fx0, fy1 - fy0
    confidence = 0.45
    if (
        1.5 <= aspect <= 4.0
        and 18 <= button_width <= width * 0.25
        and 14 <= button_height <= height * 0.08
    ):
        confidence = 0.68
    role, label = _button_role(aspect, button_width, button_height)
    center_x, center_y = (fx0 + fx1) / 2, (fy0 + fy1) / 2
    return UIElement(
        id=f"{role}_{element_index}",
        role=role,
        bbox=(fx0, fy0, fx1, fy1),
        color=_hex_color(_avg_color(im, fx0, fy0, fx1, fy1)),
        confidence=confidence,
        label=label,
        location=_location_label(center_x, center_y, width, height),
        metadata={
            "bbox_norm": [
                round(fx0 / width, 4),
                round(fy0 / height, 4),
                round(fx1 / width, 4),
                round(fy1 / height, 4),
            ],
            "aspect": round(aspect, 2),
            "source": "contrast_blob",
        },
    )


def _detect_buttons(im, w: int, h: int, *, scan_w: int = 320) -> list[UIElement]:
    """
    Compact high-contrast rectangles → button-like controls.

    Works on a downsampled difference map (no ML).
    """
    from PIL import Image

    scale = min(1.0, scan_w / w)
    sw, sh = max(32, int(w * scale)), max(32, int(h * scale))
    small = im.resize((sw, sh)).convert("RGB")
    pixels = list(small.get_flattened_data())

    mask = _local_contrast_mask(pixels, sw, sh)
    total = sw * sh
    min_area = max(4, int(total * 0.00015))
    max_area = max(min_area + 1, int(total * 0.012))
    rects = _flood_rects(mask, min_area=min_area, max_area=max_area)

    elements: list[UIElement] = []
    seen_boxes: list[tuple[int, int, int, int]] = []
    for rect in rects:
        element = _button_from_rect(
            im,
            rect,
            scale=scale,
            width=w,
            height=h,
            element_index=len(elements),
        )
        if element is None or any(_iou(element.bbox, seen) > 0.6 for seen in seen_boxes):
            continue
        seen_boxes.append(element.bbox)
        elements.append(element)

    elements.sort(key=lambda e: (-e.confidence, -(e.width * e.height)))
    return elements[:24]


def _detect_toolbar(buttons: list[UIElement], w: int, h: int) -> UIElement | None:
    """Infer toolbar from a row of buttons at similar Y."""
    if len(buttons) < 3:
        return None
    by_row: dict[int, list[UIElement]] = {}
    for b in buttons:
        row_key = b.bbox[1] // max(8, int(h * 0.02))
        by_row.setdefault(row_key, []).append(b)
    best_row: list[UIElement] = []
    for row in by_row.values():
        if len(row) > len(best_row):
            best_row = row
    if len(best_row) < 3:
        return None
    xs = [b.bbox[0] for b in best_row] + [b.bbox[2] for b in best_row]
    ys = [b.bbox[1] for b in best_row] + [b.bbox[3] for b in best_row]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return UIElement(
        id="toolbar_0",
        role="toolbar",
        bbox=(x0, y0, x1, y1),
        color="#888888",
        confidence=0.6,
        label=f"toolbar ({len(best_row)} controls)",
        location=_location_label((x0 + x1) / 2, (y0 + y1) / 2, w, h),
        metadata={
            "bbox_norm": [round(x0 / w, 4), round(y0 / h, 4), round(x1 / w, 4), round(y1 / h, 4)],
            "button_count": len(best_row),
            "source": "button_row",
        },
    )


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    return inter / max(1, area_a + area_b - inter)


def _dedupe(elements: list[UIElement]) -> list[UIElement]:
    """Drop elements heavily overlapping a higher-confidence sibling."""
    elements = sorted(elements, key=lambda e: (-e.confidence, -(e.width * e.height)))
    kept: list[UIElement] = []
    for el in elements:
        if any(el.role != k.role and _iou(el.bbox, k.bbox) > 0.75 for k in kept):
            continue
        if any(el.role == k.role and _iou(el.bbox, k.bbox) > 0.85 for k in kept):
            continue
        kept.append(el)
    return kept


def detect_ui_elements(
    image_path: str | Path,
    *,
    detect_buttons: bool = True,
    detect_panels: bool = True,
    grid: int = 48,
) -> dict[str, Any]:
    """
    Detect windows, panels, titlebar, buttons on a screenshot.

    Returns elements with pixel bboxes, normalized coords, and location labels.
    """
    from PIL import Image

    path = Path(image_path).expanduser()
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "file not found"}

    im = Image.open(path)
    w, h = im.size
    elements: list[UIElement] = []

    titlebar = _detect_titlebar(im, w, h)
    if titlebar:
        elements.append(titlebar)

    if detect_panels:
        elements.extend(_detect_panels(im, w, h, grid=grid))

    buttons: list[UIElement] = []
    if detect_buttons:
        buttons = _detect_buttons(im, w, h)
        elements.extend(buttons)

    toolbar = _detect_toolbar(buttons, w, h)
    if toolbar:
        elements.append(toolbar)

    elements = _dedupe(elements)

    by_role: dict[str, int] = Counter(e.role for e in elements)
    return {
        "ok": True,
        "path": str(path),
        "width": w,
        "height": h,
        "element_count": len(elements),
        "by_role": dict(by_role),
        "elements": [e.to_dict() for e in elements],
    }

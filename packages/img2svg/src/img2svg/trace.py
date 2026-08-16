"""Region-based raster tracing (merged color grid)."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

GridColor = tuple[int, int, int]
ColorGrid = list[list[GridColor]]
VisitedGrid = list[list[bool]]


@dataclass
class TracedRegion:
    """A merged rectangular region from the image."""

    x: float
    y: float
    width: float
    height: float
    color: str
    grid: tuple[int, int] = (0, 0)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "color": self.color,
            "grid": list(self.grid),
            "metadata": self.metadata,
        }


def _hex_color(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _horizontal_span(
    colors: ColorGrid,
    visited: VisitedGrid,
    gx: int,
    gy: int,
    grid: int,
    base: GridColor,
) -> int:
    span = 1
    while gx + span < grid and not visited[gy][gx + span] and colors[gy][gx + span] == base:
        span += 1
    return span


def _row_matches(
    colors: ColorGrid,
    visited: VisitedGrid,
    gx: int,
    gy: int,
    width: int,
    base: GridColor,
) -> bool:
    return all(
        not visited[gy][gx + dx] and colors[gy][gx + dx] == base
        for dx in range(width)
    )


def _vertical_span(
    colors: ColorGrid,
    visited: VisitedGrid,
    gx: int,
    gy: int,
    grid: int,
    width: int,
    base: GridColor,
) -> int:
    span = 1
    while gy + span < grid and _row_matches(colors, visited, gx, gy + span, width, base):
        span += 1
    return span


def _mark_region(
    visited: VisitedGrid,
    gx: int,
    gy: int,
    width: int,
    height: int,
) -> None:
    for dy in range(height):
        for dx in range(width):
            visited[gy + dy][gx + dx] = True


def _merge_grid_cells(
    colors: ColorGrid,
    *,
    grid: int,
    cell_w: float,
    cell_h: float,
) -> list[TracedRegion]:
    """Merge adjacent same-color grid cells into rectangles (greedy row merge)."""
    visited = [[False] * grid for _ in range(grid)]
    regions: list[TracedRegion] = []

    for gy in range(grid):
        for gx in range(grid):
            if visited[gy][gx]:
                continue
            base = colors[gy][gx]
            w_span = _horizontal_span(colors, visited, gx, gy, grid, base)
            h_span = _vertical_span(colors, visited, gx, gy, grid, w_span, base)
            _mark_region(visited, gx, gy, w_span, h_span)
            regions.append(
                TracedRegion(
                    x=gx * cell_w,
                    y=gy * cell_h,
                    width=w_span * cell_w,
                    height=h_span * cell_h,
                    color=_hex_color(base),
                    grid=(gx, gy),
                    metadata={"span": [w_span, h_span]},
                )
            )
    return regions


def trace_image_regions(
    image_path: str | Path,
    *,
    grid: int = 24,
) -> dict[str, Any]:
    """
    Trace image into merged color rectangles (no external tracer required).

    Suitable for UI screenshots and flat-color graphics. For photo-realistic
    images use optional OpenCV contour mode or external vtracer/potrace.
    """
    from PIL import Image

    path = Path(image_path).expanduser()
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "file not found"}

    im = Image.open(path).convert("RGB")
    w, h = im.size
    small = im.resize((grid, grid))
    cell_w = w / grid
    cell_h = h / grid

    colors: list[list[tuple[int, int, int]]] = []
    for gy in range(grid):
        row: list[tuple[int, int, int]] = []
        for gx in range(grid):
            rgb = small.getpixel((gx, gy))
            if isinstance(rgb, int):
                rgb = (rgb, rgb, rgb)
            row.append(rgb)
        colors.append(row)

    regions = _merge_grid_cells(colors, grid=grid, cell_w=cell_w, cell_h=cell_h)
    return {
        "ok": True,
        "path": str(path),
        "width": w,
        "height": h,
        "grid": grid,
        "region_count": len(regions),
        "regions": [r.to_dict() for r in regions],
        "method": "color_grid_merge",
    }


def trace_contours_opencv(
    image_path: str | Path,
    *,
    simplify_epsilon: float = 2.0,
) -> dict[str, Any]:
    """Optional contour tracing via OpenCV (pip install img2svg[opencv])."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {"ok": False, "error": "opencv not installed: pip install img2svg[opencv]"}

    from PIL import Image

    path = Path(image_path).expanduser()
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "file not found"}

    im = Image.open(path).convert("RGB")
    w, h = im.size
    gray = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    paths: list[dict[str, Any]] = []
    for i, cnt in enumerate(contours[:200]):
        if cv2.contourArea(cnt) < 80:
            continue
        approx = cv2.approxPolyDP(cnt, simplify_epsilon, True)
        pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
        if len(pts) < 3:
            continue
        d_parts = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
        for x, y in pts[1:]:
            d_parts.append(f"L {x:.1f} {y:.1f}")
        d_parts.append("Z")
        paths.append({"id": f"path_{i}", "d": " ".join(d_parts), "point_count": len(pts)})

    return {
        "ok": True,
        "path": str(path),
        "width": w,
        "height": h,
        "path_count": len(paths),
        "paths": paths,
        "method": "opencv_contour",
    }


def _parse_translate(transform: str) -> tuple[float, float]:
    match = re.search(r"translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)", transform or "")
    if match:
        return float(match.group(1)), float(match.group(2))
    return 0.0, 0.0


def _parse_vtracer_svg(svg_path: Path) -> tuple[int, int, list[dict[str, Any]]]:
    root = ET.parse(svg_path).getroot()
    width = int(float(root.attrib.get("width", "0") or 0))
    height = int(float(root.attrib.get("height", "0") or 0))
    paths: list[dict[str, Any]] = []
    for i, elem in enumerate(root.findall(".//{*}path")):
        d = elem.attrib.get("d", "")
        if not d:
            continue
        fill = elem.attrib.get("fill", "none")
        tx, ty = _parse_translate(elem.attrib.get("transform", ""))
        paths.append(
            {
                "id": elem.attrib.get("id", f"vpath_{i}"),
                "d": d,
                "fill": fill,
                "tx": tx,
                "ty": ty,
            }
        )
    return width, height, paths


def trace_vtracer(
    image_path: str | Path,
    *,
    colormode: str = "color",
    filter_speckle: int = 4,
    color_precision: int = 6,
) -> dict[str, Any]:
    """High-quality color vectorization via vtracer (pip install img2svg[vtracer])."""
    try:
        import vtracer
    except ImportError:
        return {"ok": False, "error": "vtracer not installed: pip install img2svg[vtracer]"}

    from PIL import Image

    path = Path(image_path).expanduser()
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "file not found"}

    im = Image.open(path).convert("RGB")
    w, h = im.size

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        svg_out = Path(tmp.name)

    try:
        vtracer.convert_image_to_svg_py(
            str(path),
            str(svg_out),
            colormode=colormode,
            hierarchical="stacked",
            mode="spline",
            filter_speckle=filter_speckle,
            color_precision=color_precision,
        )
        svg_w, svg_h, paths = _parse_vtracer_svg(svg_out)
    except Exception as exc:  # pragma: no cover - depends on vtracer runtime
        return {"ok": False, "path": str(path), "error": str(exc)}
    finally:
        svg_out.unlink(missing_ok=True)

    return {
        "ok": True,
        "path": str(path),
        "width": svg_w or w,
        "height": svg_h or h,
        "path_count": len(paths),
        "paths": paths,
        "method": "vtracer",
    }

"""Convert screenshots into coarse-grid VQL programs."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from vql.adopt.capture_types import CaptureInfo, require_pillow
from vql.adopt.program_enrichment import enrich_program_metadata
from vql.schema.program import Layer, Object, Primitive, Scene, Style, VQLProgram

GridColor = tuple[int, int, int]
GridRegion = tuple[int, int, int, int, GridColor]


def hex_color(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _horizontal_span(
    colors: list[list[GridColor]],
    visited: list[list[bool]],
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
    colors: list[list[GridColor]],
    visited: list[list[bool]],
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
    colors: list[list[GridColor]],
    visited: list[list[bool]],
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


def _mark_region(visited: list[list[bool]], gx: int, gy: int, width: int, height: int) -> None:
    for dy in range(height):
        for dx in range(width):
            visited[gy + dy][gx + dx] = True


def merge_grid_colors(
    colors: list[list[GridColor]],
    *,
    grid: int,
) -> list[GridRegion]:
    """Return merged rectangles as (gx, gy, w_span, h_span, rgb)."""
    visited = [[False] * grid for _ in range(grid)]
    merged: list[GridRegion] = []

    for gy in range(grid):
        for gx in range(grid):
            if visited[gy][gx]:
                continue
            base = colors[gy][gx]
            w_span = _horizontal_span(colors, visited, gx, gy, grid, base)
            h_span = _vertical_span(colors, visited, gx, gy, grid, w_span, base)
            _mark_region(visited, gx, gy, w_span, h_span)
            merged.append((gx, gy, w_span, h_span, base))
    return merged


def screenshot_to_program(
    image_path: str | Path,
    *,
    grid: int = 12,
    min_region_px: int = 40,
    capture: CaptureInfo | None = None,
    merge_regions: bool = True,
) -> VQLProgram:
    """
    Adopt a screenshot into a VQL program.

    Uses a coarse color grid to emit rectangle primitives — a vector-ish summary
    of the window/screen layout (regions + dominant colors).
    Adjacent same-color cells are merged when ``merge_regions=True``.
    """
    require_pillow()
    from PIL import Image

    path = Path(image_path)
    im = Image.open(path).convert("RGB")
    w, h = im.size
    cell_w = max(1, w // grid)
    cell_h = max(1, h // grid)
    small = im.resize((grid, grid))

    colors: list[list[tuple[int, int, int]]] = []
    for gy in range(grid):
        row: list[tuple[int, int, int]] = []
        for gx in range(grid):
            rgb = small.getpixel((gx, gy))
            if isinstance(rgb, int):
                rgb = (rgb, rgb, rgb)
            row.append(rgb)
        colors.append(row)

    objects: list[Object] = []
    if merge_regions:
        regions = merge_grid_colors(colors, grid=grid)
        for idx, (gx, gy, w_span, h_span, rgb) in enumerate(regions):
            rw, rh = w_span * cell_w, h_span * cell_h
            if rw < min_region_px and rh < min_region_px:
                continue
            cx = (gx + w_span / 2) * cell_w
            cy = (gy + h_span / 2) * cell_h
            color = hex_color(rgb)
            objects.append(
                Object(
                    id=f"region_{idx:03d}",
                    primitives=[
                        Primitive(
                            shape_type="rectangle",
                            params={"width": float(rw), "height": float(rh)},
                        )
                    ],
                    style=Style(color=color, fill=True, stroke_width=0.0),
                    center_x=cx,
                    center_y=cy,
                    metadata={
                        "grid": [gx, gy],
                        "span": [w_span, h_span],
                        "rgb": list(rgb),
                        "source": "merged_region",
                    },
                )
            )
    else:
        idx = 0
        for gy in range(grid):
            for gx in range(grid):
                rgb = colors[gy][gx]
                cx = (gx + 0.5) * cell_w
                cy = (gy + 0.5) * cell_h
                color = hex_color(rgb)
                objects.append(
                    Object(
                        id=f"cell_{idx:03d}",
                        primitives=[
                            Primitive(
                                shape_type="rectangle",
                                params={"width": cell_w, "height": cell_h},
                            )
                        ],
                        style=Style(color=color, fill=True, stroke_width=0.0),
                        center_x=cx,
                        center_y=cy,
                        metadata={"grid": [gx, gy], "rgb": list(rgb)},
                    )
                )
                idx += 1

    palette = Counter(small.get_flattened_data()).most_common(8)
    dominant_colors = [hex_color(c) for c, _ in palette]

    meta = enrich_program_metadata(
        {
            "source": "screenshot_adopt",
            "grid": grid,
            "merge_regions": merge_regions,
            "region_count": len(objects),
            "dominant_colors": dominant_colors,
        },
        path,
    )
    if capture:
        meta["capture"] = capture.to_dict()

    return VQLProgram(
        scene=Scene(
            width=float(w),
            height=float(h),
            app="desktop",
            url=f"file://{path.resolve()}",
            layers=[Layer(id="screen_regions", objects=objects)],
        ),
        metadata=meta,
    )

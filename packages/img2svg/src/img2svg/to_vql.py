"""Convert traced image regions to VQLProgram."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from img2svg.trace import trace_contours_opencv, trace_image_regions, trace_vtracer
from vql.schema.program import Layer, Object, Primitive, Scene, Style, VQLProgram


def _background_from_regions(regions: list[dict[str, Any]]) -> str:
    """Pick canvas background as the color covering the most pixel area."""
    if not regions:
        return "#FFFFFF"
    area_by_color: dict[str, float] = {}
    for reg in regions:
        color = reg.get("color", "#FFFFFF")
        area = float(reg.get("width", 0)) * float(reg.get("height", 0))
        area_by_color[color] = area_by_color.get(color, 0.0) + area
    return max(area_by_color, key=area_by_color.get)  # type: ignore[arg-type]


def _path_object(path_data: dict[str, Any], index: int, method: str) -> Object:
    fill_color = path_data.get("fill", "#CCCCCC")
    filled = fill_color.lower() not in ("none", "transparent")
    return Object(
        id=path_data.get("id", f"path_{index}"),
        primitives=[
            Primitive(
                shape_type="path",
                params={
                    "d": path_data["d"],
                    "tx": path_data.get("tx", 0.0),
                    "ty": path_data.get("ty", 0.0),
                },
            )
        ],
        style=Style(
            color=fill_color if filled else "#CCCCCC",
            fill=filled,
            stroke_width=0.0 if filled else 1.0,
        ),
        center_x=0.0,
        center_y=0.0,
        metadata={
            "source": f"img2svg_{method}",
            "point_count": path_data.get("point_count", 0),
        },
    )


def _region_object(region: dict[str, Any], index: int) -> Object:
    width, height = region["width"], region["height"]
    return Object(
        id=f"region_{index:03d}",
        primitives=[
            Primitive(shape_type="rectangle", params={"width": width, "height": height})
        ],
        style=Style(color=region["color"], fill=True, stroke_width=0.0),
        center_x=region["x"] + width / 2,
        center_y=region["y"] + height / 2,
        metadata={"source": "img2svg_regions", "grid": region.get("grid", [])},
    )


def _trace_objects(trace: dict[str, Any]) -> list[Object]:
    method = str(trace.get("method", "path"))
    if method in ("opencv_contour", "vtracer"):
        return [
            _path_object(path_data, index, method)
            for index, path_data in enumerate(trace.get("paths", []))
        ]
    return [
        _region_object(region, index)
        for index, region in enumerate(trace.get("regions", []))
    ]


def _trace_background(trace: dict[str, Any]) -> str:
    regions = trace.get("regions", [])
    if regions:
        return _background_from_regions(regions)
    if trace.get("method") == "vtracer":
        fills = [path.get("fill", "") for path in trace.get("paths", []) if path.get("fill")]
        return fills[0] if fills else "#FFFFFF"
    return "#1A1A1A"


def trace_to_vql_program(trace: dict[str, Any], *, image_path: str | Path = "") -> VQLProgram:
    """Build VQL program from trace_image_regions() or trace_contours_opencv()."""
    if not trace.get("ok"):
        raise ValueError(trace.get("error", "trace failed"))

    w = float(trace.get("width", 1024))
    h = float(trace.get("height", 768))
    path = Path(image_path or trace.get("path", ""))
    objects = _trace_objects(trace)
    background = _trace_background(trace)

    return VQLProgram(
        scene=Scene(
            width=w,
            height=h,
            background=background,
            app="raster_trace",
            url=f"file://{path.resolve()}" if path.is_file() else "",
            layers=[Layer(id="traced_regions", objects=objects)],
        ),
        metadata={
            "source": "img2svg",
            "method": trace.get("method", "color_grid_merge"),
            "image": str(path) if path else "",
            "region_count": len(objects),
            "analyzed_at": datetime.now(UTC).isoformat(),
        },
    )


def image_to_vql(
    image_path: str | Path,
    *,
    out_program: str | Path | None = None,
    grid: int = 24,
    method: str = "regions",
) -> dict[str, Any]:
    """Trace image and write VQL JSON program."""
    path = Path(image_path).expanduser()
    if method == "contours":
        trace = trace_contours_opencv(path)
    elif method == "vtracer":
        trace = trace_vtracer(path)
    else:
        trace = trace_image_regions(path, grid=grid)
    if not trace.get("ok"):
        return trace

    program = trace_to_vql_program(trace, image_path=path)
    out = Path(out_program) if out_program else path.with_suffix(".vql.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(program.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "input": str(path),
        "program": str(out),
        "method": trace.get("method"),
        "object_count": program.object_count(),
        "scene": {"width": program.scene.width, "height": program.scene.height},
    }

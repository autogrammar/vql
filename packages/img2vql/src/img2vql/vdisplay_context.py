"""Build VQL programs from vdisplay ScreenContext payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from img2vql.metadata import merge_program_metadata
from vql.schema.program import VQLProgram


def _program_from_context(ctx: dict[str, Any], image_path: str) -> VQLProgram:
    program_dict = ctx.get("vql", {}).get("program")
    if isinstance(program_dict, dict):
        return VQLProgram.from_dict(program_dict)
    if image_path and Path(image_path).is_file():
        try:
            from imgl.vdisplay_context import from_vdisplay_context

            imgl_result = from_vdisplay_context(ctx, analyze=True)
            if imgl_result.get("ok") and imgl_result.get("scene"):
                from imgl.export.vql_adapter import scene_to_vql
                from imgl.types import Scene

                scene = Scene.from_dict(imgl_result["scene"])
                return VQLProgram.from_dict(scene_to_vql(scene))
        except ImportError:
            pass
    return _fallback_program(ctx, image_path)


def _context_metadata(
    ctx: dict[str, Any],
    program: VQLProgram,
    image_path: str,
) -> dict[str, Any]:
    metadata = dict(program.metadata or {})
    metadata["capture"] = _capture_block(ctx)
    metadata["environment"] = dict(ctx.get("environment") or {})
    if ctx.get("map_pack"):
        metadata["gui_map"] = ctx["map_pack"]
    if ctx.get("verify"):
        metadata["verify"] = ctx["verify"]
    if ctx.get("vision"):
        metadata["vision"] = ctx["vision"]
    if ctx.get("nl"):
        metadata["nl"] = ctx["nl"]
        describe = metadata.get("describe")
        if not isinstance(describe, dict):
            describe = {}
        describe["nl"] = ctx["nl"]
        metadata["describe"] = describe
    if image_path:
        metadata = merge_program_metadata(metadata, image_path)
    return metadata


def from_screen_context(ctx: dict[str, Any]) -> VQLProgram:
    """Convert vdisplay ScreenContext dict to VQLProgram."""
    image_path = _image_path(ctx)
    program = _program_from_context(ctx, image_path)
    metadata = _context_metadata(ctx, program, image_path)
    program.metadata = metadata
    metadata["render_intent"] = reverse_generate(program)
    program.metadata = metadata
    return program


def _program_payload(program: VQLProgram | dict[str, Any]) -> dict[str, Any]:
    return program.to_dict() if isinstance(program, VQLProgram) else dict(program)


def _natural_language(metadata: dict[str, Any]) -> str:
    direct = str(metadata.get("nl") or "")
    if direct:
        return direct
    describe = metadata.get("describe")
    return str(describe.get("nl") or "") if isinstance(describe, dict) else ""


def _reverse_layers(payload: dict[str, Any], scene: dict[str, Any]) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    for layer in payload.get("layers") or scene.get("layers") or []:
        for obj in layer.get("objects") or []:
            metadata = obj.get("metadata") or {}
            layers.append(
                {
                    "kind": metadata.get("role") or layer.get("id"),
                    "label": metadata.get("label"),
                    "center": [obj.get("center_x"), obj.get("center_y")],
                }
            )
    return layers


def _routing_hint(metadata: dict[str, Any]) -> dict[str, Any] | None:
    environment = metadata.get("environment")
    environment_routing = environment.get("routing") if isinstance(environment, dict) else None
    routing = metadata.get("routing") or environment_routing
    if not isinstance(routing, dict):
        return None
    return {
        "provider": routing.get("selected_provider"),
        "profile": routing.get("application_profile"),
    }


def reverse_generate(program: VQLProgram | dict[str, Any]) -> dict[str, Any]:
    """Build reverse-generation descriptor from VQL program metadata."""
    payload = _program_payload(program)
    metadata = dict(payload.get("metadata") or {})
    capture_value = metadata.get("capture")
    capture = capture_value if isinstance(capture_value, dict) else {}
    scene = payload.get("scene") or {}
    width = int(capture.get("width") or scene.get("width") or 0)
    height = int(capture.get("height") or scene.get("height") or 0)
    natural_language = _natural_language(metadata)
    descriptor: dict[str, Any] = {
        "mode": "layout_reconstruction",
        "canvas": {"width": width, "height": height},
        "nl": natural_language,
        "layers": _reverse_layers(payload, scene),
        "prompt_block": natural_language or f"UI screenshot {width}x{height}",
    }
    routing_hint = _routing_hint(metadata)
    if routing_hint is not None:
        descriptor["routing_hint"] = routing_hint
    return descriptor


def render_layout_svg(program: VQLProgram) -> str:
    from vql import render_to_svg

    return render_to_svg(program)


def _image_path(ctx: dict[str, Any]) -> str:
    return str(ctx.get("image_path") or (ctx.get("capture") or {}).get("path") or "")


def _capture_block(ctx: dict[str, Any]) -> dict[str, Any]:
    capture = dict(ctx.get("capture") or {})
    capture.setdefault("source", "vdisplay")
    capture.setdefault("fingerprint", ctx.get("fingerprint"))
    return capture


def _fallback_program(ctx: dict[str, Any], image_path: str) -> VQLProgram:
    capture = ctx.get("capture") or {}
    return VQLProgram.from_dict(
        {
            "version": "1.0",
            "scene": {
                "width": int(capture.get("width") or 0),
                "height": int(capture.get("height") or 0),
            },
            "layers": [],
            "relations": [],
            "metadata": {"source": "vdisplay", "image": image_path},
        }
    )

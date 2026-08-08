"""LLM prompt/response handling for VQLProgram extraction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from img2vql.contracts import validate_payload
from img2vql.pipeline.config import PipelineLLMConfig
from img2vql.pipeline.llm_client import (
    LLMClientError,
    build_vision_user_message,
    chat_completion,
)
from img2vql.pipeline.schema_prompt import build_vql_schema_prompt
from vql.schema.program import VQLProgram


def _compact_fast_context(
    l1: dict[str, Any], l2: dict[str, Any] | None, l4: dict[str, Any] | None
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "img2nl_text": l1.get("text", ""),
        "scene_class": (l1.get("metadata") or {}).get("scene_class", ""),
        "dominant_colors": (l1.get("features") or {})
        .get("colors", {})
        .get("dominant", []),
        "special_hits": (l1.get("metadata") or {}).get("special_hits", {}),
        "llm_hint": l1.get("llm_hint", {}),
        "dimensions": {"width": l1.get("width"), "height": l1.get("height")},
    }
    if l2 and l2.get("ok"):
        ctx["detected_elements"] = [
            {
                "id": el.get("id"),
                "role": el.get("role"),
                "label": el.get("label"),
                "bbox": el.get("bbox"),
                "confidence": el.get("confidence"),
            }
            for el in (l2.get("elements") or [])[:40]
        ]
        ctx["detect_by_role"] = l2.get("by_role", {})
    if l4:
        ctx["diagnose_recommendation"] = l4.get("recommendation", "")
        ctx["similarity"] = l4.get("similarity", {})
    return ctx


def _program_summary(program: dict[str, Any]) -> dict[str, Any]:
    scene = program.get("scene", {})
    layers = scene.get("layers", [])
    return {
        "width": scene.get("width"),
        "height": scene.get("height"),
        "layer_ids": [layer.get("id") for layer in layers],
        "object_count": sum(len(layer.get("objects", [])) for layer in layers),
        "metadata_keys": sorted((program.get("metadata") or {}).keys()),
    }


def build_llm_extraction_prompt(
    *,
    fast_context: dict[str, Any],
    partial_program: dict[str, Any],
    scene_width: int,
    scene_height: int,
    locale: str,
) -> str:
    schema_block = build_vql_schema_prompt(
        scene_width=scene_width, scene_height=scene_height
    )
    meta_json = json.dumps(fast_context, ensure_ascii=False, indent=2)
    partial_json = json.dumps(
        _program_summary(partial_program), ensure_ascii=False, indent=2
    )
    return (
        "You are a VQL (Visual Query Language) extractor.\n"
        f"Locale for labels: {locale}.\n\n"
        "FAST PRE-ANALYSIS (img2nl + heuristics) — use as ground truth hints:\n"
        f"{meta_json}\n\n"
        "PARTIAL VQL PROGRAM already adopted (geometry baseline):\n"
        f"{partial_json}\n\n"
        "TASK: produce a complete VQLProgram JSON with semantic UI objects "
        "(buttons, panels, inputs, text regions) aligned to the screenshot.\n"
        "Prefer refining detected bboxes; add missing interactive elements.\n"
        "Keep metadata.source=pipeline_llm and include metadata.llm_extract.confidence (0-1).\n\n"
        f"{schema_block}"
    )


def parse_vql_json_from_llm(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMClientError("LLM response must be a single JSON object") from exc
    if not isinstance(data, dict):
        raise LLMClientError("LLM JSON root must be an object")
    try:
        validate_payload(data)
    except ValueError as exc:
        raise LLMClientError(str(exc)) from exc
    return data


def validate_vql_program(data: dict[str, Any]) -> VQLProgram:
    program = VQLProgram.from_dict(data)
    errors = program.validate()
    if errors:
        raise LLMClientError(f"VQL validation failed: {'; '.join(errors[:5])}")
    return program


def level5_llm_extract(
    image_path: str | Path,
    *,
    l1: dict[str, Any],
    l2: dict[str, Any] | None,
    l4: dict[str, Any] | None,
    partial_program: dict[str, Any],
    config: PipelineLLMConfig,
    locale: str = "pl",
    force: bool = False,
) -> dict[str, Any]:
    if not config.configured:
        return {
            "level": "L5_llm",
            "ok": False,
            "skipped": True,
            "reason": "llm_not_configured",
        }

    recommendation = (l4 or {}).get("recommendation", "")
    if not force:
        if recommendation == "skip_llm_blank_capture":
            return {
                "level": "L5_llm",
                "ok": False,
                "skipped": True,
                "reason": recommendation,
            }
        if recommendation == "skip_unchanged_screen":
            return {
                "level": "L5_llm",
                "ok": False,
                "skipped": True,
                "reason": recommendation,
            }

    width = int(
        l1.get("width") or partial_program.get("scene", {}).get("width") or 1024
    )
    height = int(
        l1.get("height") or partial_program.get("scene", {}).get("height") or 768
    )
    fast_ctx = _compact_fast_context(l1, l2, l4)
    prompt = build_llm_extraction_prompt(
        fast_context=fast_ctx,
        partial_program=partial_program,
        scene_width=width,
        scene_height=height,
        locale=locale,
    )

    thumb = l1.get("thumbnail") or image_path
    messages = [
        {
            "role": "system",
            "content": "You output strict JSON only — a valid VQLProgram for UI screenshots.",
        },
        build_vision_user_message(
            text=prompt, image_path=thumb, use_vision=config.vision
        ),
    ]

    try:
        llm_resp = chat_completion(config, messages)
        program_data = parse_vql_json_from_llm(content=str(llm_resp.get("content", "")))
        program = validate_vql_program(program_data)
        meta = dict(program.metadata)
        meta.setdefault("llm_extract", {})
        meta["llm_extract"].update(
            {
                "model": llm_resp.get("model", config.model),
                "usage": llm_resp.get("usage", {}),
                "fast_context": fast_ctx,
            }
        )
        meta["pipeline"] = {"levels": ["L1_img2nl", "L3_adopt", "L5_llm"]}
        program.metadata = meta
        return {
            "level": "L5_llm",
            "ok": True,
            "program": program.to_dict(),
            "model": llm_resp.get("model"),
            "usage": llm_resp.get("usage", {}),
        }
    except (LLMClientError, json.JSONDecodeError, ValueError) as exc:
        return {"level": "L5_llm", "ok": False, "error": str(exc)}


def merge_programs(
    base: dict[str, Any],
    llm_program: dict[str, Any],
    *,
    img2nl_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Merge LLM layer into base program, preserving img2nl metadata."""
    merged = dict(base)
    llm_scene = llm_program.get("scene", {})
    base_scene = dict(merged.get("scene", {}))
    base_layers = list(base_scene.get("layers", []))
    llm_layers = llm_scene.get("layers") or []

    llm_layer_ids = {layer.get("id") for layer in llm_layers}
    kept = [layer for layer in base_layers if layer.get("id") not in llm_layer_ids]
    merged_layers = kept + llm_layers
    if not merged_layers:
        merged_layers = base_layers

    base_scene.update(
        {
            "width": llm_scene.get("width") or base_scene.get("width"),
            "height": llm_scene.get("height") or base_scene.get("height"),
            "layers": merged_layers,
        }
    )
    merged["scene"] = base_scene

    meta = dict(merged.get("metadata", {}))
    meta.update(img2nl_metadata)
    meta.update(llm_program.get("metadata") or {})
    meta["pipeline_merged"] = True
    merged["metadata"] = meta
    return merged

"""VQL JSON schema excerpt for LLM extraction prompts."""

from __future__ import annotations

import json

from img2vql.contracts import load_schema


def build_vql_schema_prompt(*, scene_width: int, scene_height: int) -> str:
    schema = json.dumps(load_schema(), ensure_ascii=False, indent=2)
    return (
        "Return ONE JSON object matching this VQLProgram schema (no markdown prose):\n"
        f"{schema}\n\n"
        f"Canvas size MUST be width={scene_width}, height={scene_height}.\n"
        "Use layers[].objects[] with center_x/center_y and rectangle primitives for UI regions.\n"
        "Put readable text in object.metadata.label. Preserve semantic roles in metadata.role.\n"
        "Do not wrap the JSON in code fences."
    )

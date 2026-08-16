from __future__ import annotations

import json
from pathlib import Path

import pytest

from uri2vql.query import query_uri
from uri2vql.uri import uri_for_object, uri_for_objects, uri_for_scene
from uri2vql.window_utils import diagnose_fallback
from vql.schema.program import Layer, Object, Primitive, Scene, VQLProgram


def _program_file(tmp_path: Path) -> Path:
    program = VQLProgram(
        scene=Scene(
            width=320,
            height=200,
            layers=[
                Layer(
                    id="main",
                    objects=[
                        Object(
                            id="button",
                            primitives=[Primitive(shape_type="rectangle")],
                        )
                    ],
                )
            ],
        )
    )
    path = tmp_path / "app.vql.json"
    path.write_text(json.dumps(program.to_dict()), encoding="utf-8")
    return path


def test_query_uri_selects_scene_objects_and_one_object(tmp_path: Path) -> None:
    path = _program_file(tmp_path)

    scene = query_uri(uri_for_scene(str(path)))
    objects = query_uri(uri_for_objects(str(path)))
    selected = query_uri(uri_for_object("button", file=str(path)))

    assert scene.ok and scene.data["width"] == 320
    assert objects.ok and [item["id"] for item in objects.data] == ["button"]
    assert selected.ok and selected.data["id"] == "button"


def test_query_uri_preserves_selector_context_for_missing_object(tmp_path: Path) -> None:
    path = _program_file(tmp_path)
    result = query_uri(uri_for_object("missing", file=str(path)))

    assert not result.ok
    assert result.selector == "object/missing"
    assert result.file == str(path)
    assert result.error == "object not found: missing"


def test_diagnose_fallback_reports_blank_image_and_program_summary(tmp_path: Path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image = tmp_path / "blank.png"
    image_module.new("RGB", (32, 24), (0, 0, 0)).save(image)

    result = diagnose_fallback(image, vql_program=_program_file(tmp_path), locale="en")

    assert result["ok"]
    assert result["recommendation"] == "skip_llm_blank_capture"
    assert result["llm_hint"]["send_to_llm"] is False
    assert result["vql_object_count"] == 1

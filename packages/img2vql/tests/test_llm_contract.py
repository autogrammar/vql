"""Offline contract tests for the image-to-VQL LLM boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from img2vql.contracts import (
    CONTRACT_VERSION,
    VQL_VERSION,
    load_schema,
    validate_payload,
)
from img2vql.pipeline.config import PipelineLLMConfig
from img2vql.pipeline.llm_client import LLMClientError, chat_completion
from img2vql.pipeline.llm_vql import parse_vql_json_from_llm, validate_vql_program
from img2vql.pipeline.schema_prompt import build_vql_schema_prompt

FIXTURES = Path(__file__).parent / "fixtures" / "contracts" / "v1"
CONTRACTS = Path(__file__).parents[1] / "src" / "img2vql" / "contracts" / "v1"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_fixture_passes_schema_parser_and_semantic_model() -> None:
    payload = _fixture("valid-vql-program.json")
    validate_payload(payload)
    assert parse_vql_json_from_llm(json.dumps(payload)) == payload
    assert validate_vql_program(payload).is_valid()


@pytest.mark.parametrize(
    "payload",
    [
        _fixture("invalid-vql-program.json"),
        {"version": "1.0", "render_target": "svg", "scene": {}, "metadata": {}},
        {
            "version": "1.0",
            "render_target": "pdf",
            "scene": {"width": 1, "height": 1, "layers": []},
            "metadata": {},
        },
    ],
)
def test_invalid_payloads_fail_closed(payload: dict) -> None:
    with pytest.raises(ValueError, match="violates VQLProgram v1"):
        validate_payload(payload)


def test_parser_rejects_fences_and_surrounding_prose() -> None:
    with pytest.raises(LLMClientError, match="single JSON object"):
        parse_vql_json_from_llm('```json\n{"version":"1.0"}\n```')
    with pytest.raises(LLMClientError, match="single JSON object"):
        parse_vql_json_from_llm('Result: {"version":"1.0"}')


def test_prompt_embeds_the_runtime_schema_not_an_informal_excerpt() -> None:
    prompt = build_vql_schema_prompt(scene_width=800, scene_height=600)
    assert load_schema()["$id"] in prompt
    assert '"additionalProperties": false' in prompt
    assert "width=800, height=600" in prompt


def test_openrouter_request_uses_schema_and_project_app_name(
    monkeypatch, tmp_path: Path
) -> None:
    project = tmp_path / "visual-project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv("OPENROUTER_APP_URL", "https://example.test/vql")
    monkeypatch.delenv("OPENROUTER_APP_NAME", raising=False)
    captured: dict = {}
    response_content = json.dumps(_fixture("valid-vql-program.json"))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": response_content}}],
                    "model": "vision-model",
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    config = PipelineLLMConfig(
        enabled=True,
        api_key="test-key",
        model="vision-model",
        base_url="https://openrouter.ai/api/v1",
        vision=True,
        temperature=0,
        max_tokens=1000,
        timeout_s=30,
    )
    result = chat_completion(config, [{"role": "user", "content": "extract"}])
    assert result["model"] == "vision-model"
    assert captured["headers"]["X-openrouter-title"] == "visual-project"
    assert captured["headers"]["Http-referer"] == "https://example.test/vql"
    assert (
        captured["payload"]["response_format"]["json_schema"]["schema"] == load_schema()
    )


def test_image_messages_use_central_subllm_vision(monkeypatch) -> None:
    captured: dict = {}

    def fake_complete(application, function, messages, **kwargs):
        captured.update(application=application, function=function, kwargs=kwargs)
        return type("Response", (), {"content": '{"ok":true}', "model": "z-ai/glm-4.5v", "usage": {}})()

    monkeypatch.setattr("img2vql.pipeline.llm_client.subllm_complete", fake_complete)
    config = PipelineLLMConfig(
        enabled=True,
        api_key="test-key",
        model="ignored-by-policy",
        base_url="https://openrouter.ai/api/v1",
        vision=True,
        temperature=0,
        max_tokens=1000,
        timeout_s=30,
    )
    result = chat_completion(
        config,
        [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,aaa"}},
                    {"type": "text", "text": "extract"},
                ],
            }
        ],
    )
    assert result["content"] == '{"ok":true}'
    assert captured["application"] == "autogrammar-vql"
    assert captured["function"] == "vision"
    assert captured["kwargs"]["credentials"] == {"openrouter": "test-key"}


def test_manifest_and_models_share_versions_and_artifacts() -> None:
    manifest = json.loads((CONTRACTS / "manifest.json").read_text(encoding="utf-8"))
    proto = (CONTRACTS / "vql-program.proto").read_text(encoding="utf-8")
    grammar = (CONTRACTS / "vql-program.gbnf").read_text(encoding="utf-8")
    assert manifest["version"] == CONTRACT_VERSION
    assert manifest["payloadVersion"] == VQL_VERSION
    assert manifest["boundary"] == "img2vql.pipeline.llm_vql.level5_llm_extract"
    for artifact in manifest["artifacts"].values():
        assert (CONTRACTS / artifact).is_file()
    assert "message VQLProgram" in proto
    assert "google.protobuf.Struct metadata = 5;" in proto
    assert f'\\"{VQL_VERSION}\\"' in grammar

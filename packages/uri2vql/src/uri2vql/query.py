"""Query VQL programs via vql:// URIs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uri2vql.uri import parse_vql_uri


@dataclass
class QueryResult:
    ok: bool
    uri: str
    selector: str
    file: str
    data: Any = None
    rendered: str = ""
    format: str = "json"
    error: str | None = None
    keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "uri": self.uri,
            "selector": self.selector,
            "file": self.file,
            "data": self.data,
            "rendered": self.rendered,
            "format": self.format,
            "keys": self.keys,
            "error": self.error,
        }


def _load_program(path: str):
    from vql.schema.program import VQLProgram

    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return VQLProgram.from_dict(data)


def _selected_payload(program, data: dict[str, Any], selector: str) -> tuple[Any, str | None]:
    if selector in {"program", ""}:
        return data, None
    if selector == "scene":
        return data.get("scene", {}), None
    if selector == "objects":
        return [
            obj.to_dict()
            for layer in program.scene.layers
            for obj in layer.objects
        ], None
    if selector.startswith("object/"):
        object_id = selector.split("/", 1)[1]
        payload = next(
            (obj.to_dict() for obj in program.scene.iter_objects() if obj.id == object_id),
            None,
        )
        return payload, None if payload is not None else f"object not found: {object_id}"
    return data, None


def query_uri(uri: str, *, file: str | None = None, fmt: str = "json") -> QueryResult:
    if uri.startswith("vql://window/"):
        from uri2vql.window import query_window

        return query_window(uri, file=file, fmt=fmt)
    try:
        parsed = parse_vql_uri(uri, default_file=file or "app.vql.json")
        program = _load_program(parsed.file)
        data = program.to_dict()
        payload, error = _selected_payload(program, data, parsed.selector)
        if error:
            return QueryResult(
                ok=False,
                uri=uri,
                selector=parsed.selector,
                file=parsed.file,
                error=error,
            )

        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        return QueryResult(
            ok=True,
            uri=uri,
            selector=parsed.selector,
            file=parsed.file,
            data=payload,
            rendered=rendered,
            format=fmt,
            keys=list(payload.keys()) if isinstance(payload, dict) else [],
        )
    except Exception as exc:
        return QueryResult(ok=False, uri=uri, selector="", file=file or "", error=str(exc))

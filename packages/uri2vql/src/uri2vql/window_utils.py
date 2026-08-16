"""Shared helpers for vql://window/* handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_image_param(image: str | None) -> tuple[str | None, str | None]:
    if not image:
        return None, "image= query param required"
    path = Path(image).expanduser()
    if path.is_file():
        return str(path.resolve()), None
    candidates = [path]
    if not path.is_absolute():
        candidates.append(Path.cwd() / path)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve()), None
    return (
        None,
        f"image file not found: {image} (cwd={Path.cwd()}). "
        "Capture first: imgl capture -o screen.png",
    )


def normalize_locale(locale: str) -> str:
    try:
        from img2nl.i18n import normalize_locale as nl_normalize

        return nl_normalize(locale)
    except ImportError:
        loc = (locale or "pl").strip().lower()
        return "en" if loc.startswith("en") else "pl"


def _fallback_recommendation(
    stats: dict[str, Any],
    locale: str,
    translator: Any,
) -> tuple[str, bool, str]:
    width, height = stats.get("width"), stats.get("height")
    unique = int(stats.get("unique_colors_sampled", 0))
    brightness = int(stats.get("brightness_avg", 0))
    if stats.get("is_blank"):
        text = (
            translator("diag_blank", locale, w=width, h=height)
            if translator
            else f"Image {width}×{height} px looks blank/black."
        )
        return "skip_llm_blank_capture", False, text
    if unique >= 8 and brightness >= 20:
        text = (
            translator(
                "diag_send_llm",
                locale,
                w=width,
                h=height,
                unique=unique,
                b_min=stats.get("brightness_min"),
                b_max=stats.get("brightness_max"),
            )
            if translator
            else f"Image {width}×{height} px, ~{unique} colors."
        )
        return "send_thumbnail_to_llm", True, text
    text = (
        translator("diag_grid_only", locale, w=width, h=height, unique=unique)
        if translator
        else f"Image {width}×{height} px, ~{unique} colors."
    )
    return "use_vql_grid_only", False, text


def _attach_program_summary(out: dict[str, Any], vql_program: str | Path | None) -> None:
    if not vql_program or not Path(vql_program).is_file():
        return
    try:
        from vql.schema.program import VQLProgram

        data = json.loads(Path(vql_program).read_text(encoding="utf-8"))
        program = VQLProgram.from_dict(data)
        out["vql_object_count"] = program.object_count()
        out["vql_dominant_colors"] = program.metadata.get("dominant_colors", [])
    except Exception as exc:
        out["vql_error"] = str(exc)


def diagnose_fallback(
    image: str | Path,
    *,
    vql_program: str | Path | None = None,
    locale: str = "pl",
) -> dict[str, Any]:
    """Lightweight diagnose when img2vql/img2nl is not installed."""
    from vql.adopt.window import image_stats

    stats = image_stats(image)
    if not stats.get("ok"):
        return {"ok": False, "path": str(image), "error": stats.get("error", "image_stats failed")}

    loc = normalize_locale(locale)

    try:
        from img2nl.i18n import t as i18n_t
    except ImportError:
        i18n_t = None

    recommendation, send, text = _fallback_recommendation(stats, loc, i18n_t)

    out: dict[str, Any] = {
        "ok": True,
        "path": str(image),
        "text": text,
        "locale": loc,
        "recommendation": recommendation,
        "llm_hint": {
            "send_to_llm": send,
            "confidence": 0.6 if send else 0.4,
            "reasons": ["vql_image_stats_fallback"],
            "recommendation": "send" if send else "skip_or_use_thumbnail_only",
        },
        "image_stats": stats,
        "source": "vql-fallback",
        "vql_program": str(vql_program) if vql_program else "",
    }
    _attach_program_summary(out, vql_program)
    return out


def resolve_window_image(out_file: str, image: str | None) -> str | None:
    if image and Path(str(image)).is_file():
        return str(image)
    prog_path = Path(out_file)
    if prog_path.is_file():
        try:
            prog = json.loads(prog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        candidate = prog.get("metadata", {}).get("image") or prog.get("metadata", {}).get("capture", {}).get("path")
        if candidate and Path(str(candidate)).is_file():
            return str(candidate)
    return None


def query_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes"}


def payload_result(
    *,
    ok: bool,
    uri: str,
    selector: str,
    out_file: str,
    payload: dict[str, Any],
    fmt: str,
) -> "QueryResult":
    from uri2vql.query import QueryResult

    return QueryResult(
        ok=ok,
        uri=uri,
        selector=selector,
        file=out_file,
        data=payload,
        rendered=json.dumps(payload, ensure_ascii=False, indent=2),
        format=fmt,
        error=None if ok else payload.get("error"),
    )

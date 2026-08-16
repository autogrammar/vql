"""Multi-level image→VQL pipeline orchestrator."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from img2vql.fingerprint import load_program_fingerprint
from img2vql.metadata import merge_program_metadata, _json_safe
from img2vql.pipeline.config import PipelineConfig
from img2vql.pipeline.fast_analysis import (
    level0_image_stats,
    level1_img2nl_fast,
    level2_ui_detect,
    level3_adopt_program,
    level4_diagnose,
)
from img2vql.pipeline.llm_vql import level5_llm_extract, merge_programs
from img2vql.pipeline.roundtrip import vql_to_image
from vql.schema.program import VQLProgram


def _run_llm_level(
    path: Path,
    *,
    cfg: PipelineConfig,
    run_llm: bool | None,
    levels: dict[str, Any],
    program_dict: dict[str, Any],
) -> dict[str, Any]:
    do_llm = cfg.llm.enabled if run_llm is None else run_llm
    if not do_llm or not cfg.llm.configured:
        levels["L5"] = {
            "level": "L5_llm",
            "ok": False,
            "skipped": True,
            "reason": "disabled" if run_llm is False else "llm_not_configured",
        }
        return program_dict

    l5 = level5_llm_extract(
        path,
        l1=levels["L1"],
        l2=levels["L2"] if levels["L2"].get("ok") else None,
        l4=levels["L4"] if levels["L4"].get("ok") else None,
        partial_program=program_dict,
        config=cfg.llm,
        locale=cfg.locale,
        force=run_llm is True,
    )
    levels["L5"] = l5
    if not l5.get("ok") or not l5.get("program"):
        return program_dict
    if cfg.merge_llm_layers:
        return merge_programs(
            program_dict,
            l5["program"],
            img2nl_metadata=levels["L1"].get("metadata") or {},
        )
    return l5["program"]


def _add_pipeline_metadata(
    program_dict: dict[str, Any],
    levels: dict[str, Any],
) -> None:
    program_dict.setdefault("metadata", {})
    program_dict["metadata"]["pipeline"] = {
        "analyzed_at": datetime.now(UTC).isoformat(),
        "levels_run": list(levels.keys()),
        "adopt_method": levels["L3"].get("method"),
        "recommendation": levels["L4"].get("recommendation"),
    }


def _render_if_requested(
    program: VQLProgram,
    *,
    out: Path,
    render_out: str | Path | None,
    save_render: bool,
    levels: dict[str, Any],
) -> str:
    if not save_render and not render_out:
        return ""
    png_out = Path(render_out or out.with_suffix(".render.png"))
    try:
        render_path = vql_to_image(program, png_out)
    except Exception as exc:
        levels["render"] = {"ok": False, "error": str(exc)}
        return ""
    levels["render"] = {"ok": True, "path": render_path}
    return render_path


def analyze_image_to_vql(
    image_path: str | Path,
    *,
    out_program: str | Path = "app.vql.json",
    config: PipelineConfig | None = None,
    render_out: str | Path | None = None,
    run_llm: bool | None = None,
) -> dict[str, Any]:
    """
    Multi-level pipeline: img2nl fast → detect → adopt → diagnose → optional LLM → save.

    Levels:
      L0 stats, L1 img2nl, L2 detect, L3 adopt, L4 diagnose, L5 LLM (when configured).
    """
    path = Path(image_path).expanduser()
    if not path.is_file():
        return {"ok": False, "error": f"image not found: {path}"}

    cfg = config or PipelineConfig.from_env()
    out = Path(out_program).expanduser()
    levels: dict[str, Any] = {}

    l0 = level0_image_stats(path)
    levels["L0"] = l0
    if not l0.get("ok"):
        return {"ok": False, "levels": levels, "error": l0.get("error", "L0 failed")}

    ref_fp = load_program_fingerprint(out) if out.is_file() else None
    l1 = level1_img2nl_fast(path, locale=cfg.locale, reference_fingerprint=ref_fp)
    levels["L1"] = l1
    if not l1.get("ok"):
        return {"ok": False, "levels": levels, "error": l1.get("error", "L1 img2nl failed")}

    l2 = level2_ui_detect(path)
    levels["L2"] = l2

    l3 = level3_adopt_program(
        path,
        method=cfg.adopt_method,  # type: ignore[arg-type]
        locale=cfg.locale,
        grid=cfg.grid,
        include_grid=cfg.adopt_method in {"auto", "detect", "imgl"},
    )
    levels["L3"] = l3
    if not l3.get("ok"):
        return {"ok": False, "levels": levels, "error": l3.get("error", "L3 adopt failed")}

    program_dict = dict(l3["program"])
    program_dict["metadata"] = merge_program_metadata(
        program_dict.get("metadata", {}),
        path,
        locale=cfg.locale,
        reference_fingerprint=ref_fp,
    )

    tmp_prog = out.with_suffix(".pipeline.tmp.vql.json")
    tmp_prog.write_text(json.dumps(program_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    l4 = level4_diagnose(path, vql_program=tmp_prog, locale=cfg.locale)
    levels["L4"] = l4

    program_dict = _run_llm_level(
        path,
        cfg=cfg,
        run_llm=run_llm,
        levels=levels,
        program_dict=program_dict,
    )
    _add_pipeline_metadata(program_dict, levels)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(program_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_prog.unlink(missing_ok=True)

    program = VQLProgram.from_dict(program_dict)
    render_path = _render_if_requested(
        program,
        out=out,
        render_out=render_out,
        save_render=cfg.save_render,
        levels=levels,
    )

    return _json_safe(
        {
            "ok": True,
            "image": str(path),
            "program": str(out),
            "object_count": program.object_count(),
            "scene_class": program_dict.get("metadata", {}).get("scene_class", ""),
            "recommendation": l4.get("recommendation"),
            "render": render_path,
            "levels": levels,
        }
    )

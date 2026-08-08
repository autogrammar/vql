# img2vql

Screenshot UI detection + img2nl diagnose adapter for VQL.

**Docs:** [../../docs/window-pipeline.md](../../docs/window-pipeline.md) · [../../docs/window-uri.md](../../docs/window-uri.md) · [../../TODO.md](../../TODO.md)

## Capabilities

| Command | What it does |
|---------|--------------|
| `diagnose` | img2nl heuristics — send to LLM or grid-only? |
| `detect` | Windows, panels, titlebar, buttons with pixel bboxes |
| `adopt` | Detect UI → write `ui.vql.json` with `ui_elements` layer |

Detection is **heuristic** (color regions + contrast blobs), not ML. For OCR and labeled controls use [imgl](https://github.com/semcod/imgl) via `uri2vql adopt-imgl`.

## Install

```bash
pip install -e ~/github/wronai/img2nl[analyze]
pip install -e packages/img2vql
```

## CLI

```bash
# Detect UI elements + NL description
img2vql detect /tmp/screen.png --describe --locale pl

# Detect + VQL program
img2vql adopt /tmp/screen.png --out /tmp/ui.vql.json --locale pl

# With background color grid layer
img2vql adopt /tmp/screen.png --with-grid --grid 12

# LLM routing
img2vql diagnose /tmp/screen.png --locale pl --translate-mode auto
```

## uri2vql integration

```bash
uri2vql detect-window --image /tmp/screen.png --locale pl
uri2vql adopt-ui --image /tmp/screen.png --out ui.vql.json
uri2vql compare-window --image /tmp/screen.png --vql-program app.vql.json
uri2vql refresh-window --vql-program app.vql.json --image /tmp/screen.png
uri2vql diagnose-window --image /tmp/screen.png --vql-program app.vql.json --save

uri2vql query "vql://window/detect?image=/tmp/screen.png&locale=pl"
uri2vql query "vql://window/compare?file=app.vql.json&image=/tmp/screen.png"
```

## Python

```python
from img2vql import detect_ui_elements, adopt_screenshot, describe_ui_layout
from img2vql import compare_with_program, fingerprint_for_image

det = detect_ui_elements("/tmp/screen.png")
print(describe_ui_layout(det, locale="pl"))
adopt_screenshot("/tmp/screen.png", out_program="/tmp/ui.vql.json")
```

## VQL output

`adopt` writes objects in layer `ui_elements` with metadata:

- `role`: `window`, `panel`, `titlebar`, `toolbar`, `button`, `icon_button`
- `bbox`, `bbox_norm`, `location`, `confidence`, `color`

Combine with [img2svg](../img2svg/README.md) for vector sidecar or [img2nl](https://github.com/wronai/img2nl) for full feature analysis.

## LLM output contract

Level L5 accepts only `VQLProgram` payload version `1.0` under contract bundle
`1.0.0`. The packaged `img2vql/contracts/v1` directory contains its GBNF,
Protobuf model, JSON Schema and boundary manifest. The same JSON Schema is
embedded in the extraction prompt, sent to OpenRouter as `response_format`,
and applied locally before constructing `VQLProgram`. Fenced or prose-wrapped
JSON, unknown fields, invalid geometry and version drift fail closed.

Set `OPENROUTER_APP_NAME` to control the OpenRouter App column; without it the
current project folder name is used. The screenshot pipeline deliberately
keeps a vision-capable `VQL_LLM_MODEL` rather than inheriting a text-only model.

## Related

- [img2svg](../img2svg/README.md) — PNG → SVG
- [examples/img2nl-vql-flow.sh](../../examples/img2nl-vql-flow.sh)

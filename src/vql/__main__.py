"""VQL CLI entry point."""

from __future__ import annotations

import sys
from . import VQLFacade


def main(argv: list[str] | None = None) -> int:
    """Run the VQL CLI."""
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: python -m vql [command] [options]")
        print()
        print("Commands:")
        print("  validate <file>    Validate a VQL program file")
        print("  render <file>      Render a VQL program to SVG")
        print("  version             Show version")
        return 0
    if args[0] in ("-v", "--version", "version"):
        print(f"vql {getattr(__import__('vql'), '__version__', '0.1.7')}")
        return 0
    if args[0] == "validate" and len(args) > 1:
        import json
        from pathlib import Path
        program = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        report = VQLFacade.validate(program)
        print(json.dumps(report.to_dict() if hasattr(report, "to_dict") else str(report), indent=2))
        return 0 if getattr(report, "valid", True) else 1
    if args[0] == "render" and len(args) > 1:
        import json
        from pathlib import Path
        program = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        result = VQLFacade.render(program)
        print(result.svg if hasattr(result, "svg") else str(result))
        return 0
    print(f"Unknown command: {args[0]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

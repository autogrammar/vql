from __future__ import annotations

import re
from dataclasses import dataclass, field

PointGroup = list[tuple[float, float]]

_PATH_TOKEN_RE = re.compile(
    r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
)
_CMD_CHARS = "MmLlHhVvCcSsQqTtAaZz"
_BEZIER_STEPS = (0.25, 0.5, 0.75, 1.0)
_QUAD_STEPS = (0.33, 0.66, 1.0)
_SKIP_PARAM_COUNTS = {"S": 4, "s": 4, "T": 2, "t": 2, "A": 7, "a": 7}


@dataclass
class _PathState:
    groups: list[PointGroup] = field(default_factory=list)
    current: PointGroup = field(default_factory=list)
    cx: float = 0.0
    cy: float = 0.0
    sx: float = 0.0
    sy: float = 0.0
    cmd: str = "M"
    tokens: list[str] = field(default_factory=list)
    index: int = 0

    def next_num(self) -> float:
        while self.index < len(self.tokens) and self.tokens[self.index] in _CMD_CHARS:
            self.index += 1
        if self.index < len(self.tokens):
            val = float(self.tokens[self.index])
            self.index += 1
            return val
        return 0.0

    def close_subpath(self) -> None:
        if self.current:
            self.current.append((self.sx, self.sy))
            self.groups.append(self.current)
            self.current = []
        self.cx, self.cy = self.sx, self.sy

    def start_subpath(self, x: float, y: float) -> None:
        if self.current:
            self.groups.append(self.current)
            self.current = []
        self.cx, self.cy = x, y
        self.sx, self.sy = x, y
        self.current.append((x, y))

    def line_to(self, x: float, y: float) -> None:
        self.cx, self.cy = x, y
        self.current.append((x, y))

    def append_cubic(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
    ) -> None:
        for t in _BEZIER_STEPS:
            bx = (1 - t) ** 3 * self.cx + 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t**2 * x2 + t**3 * x3
            by = (1 - t) ** 3 * self.cy + 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t**2 * y2 + t**3 * y3
            self.current.append((bx, by))
        self.cx, self.cy = x3, y3

    def append_quadratic(self, x1: float, y1: float, x2: float, y2: float) -> None:
        for t in _QUAD_STEPS:
            bx = (1 - t) ** 2 * self.cx + 2 * (1 - t) * t * x1 + t**2 * x2
            by = (1 - t) ** 2 * self.cy + 2 * (1 - t) * t * y1 + t**2 * y2
            self.current.append((bx, by))
        self.cx, self.cy = x2, y2


def _dispatch_linear_command(state: _PathState, cmd: str) -> bool:
    if cmd == "M":
        state.start_subpath(state.next_num(), state.next_num())
        state.cmd = "L"
    elif cmd == "m":
        state.start_subpath(state.cx + state.next_num(), state.cy + state.next_num())
        state.cmd = "l"
    elif cmd == "L":
        state.line_to(state.next_num(), state.next_num())
    elif cmd == "l":
        state.line_to(state.cx + state.next_num(), state.cy + state.next_num())
    elif cmd == "H":
        state.line_to(state.next_num(), state.cy)
    elif cmd == "h":
        state.line_to(state.cx + state.next_num(), state.cy)
    elif cmd == "V":
        state.line_to(state.cx, state.next_num())
    elif cmd == "v":
        state.line_to(state.cx, state.cy + state.next_num())
    else:
        return False
    return True


def _dispatch_curve_command(state: _PathState, cmd: str) -> bool:
    if cmd == "C":
        state.append_cubic(
            state.next_num(),
            state.next_num(),
            state.next_num(),
            state.next_num(),
            state.next_num(),
            state.next_num(),
        )
    elif cmd == "c":
        state.append_cubic(
            state.cx + state.next_num(),
            state.cy + state.next_num(),
            state.cx + state.next_num(),
            state.cy + state.next_num(),
            state.cx + state.next_num(),
            state.cy + state.next_num(),
        )
    elif cmd == "Q":
        state.append_quadratic(state.next_num(), state.next_num(), state.next_num(), state.next_num())
    elif cmd == "q":
        state.append_quadratic(
            state.cx + state.next_num(),
            state.cy + state.next_num(),
            state.cx + state.next_num(),
            state.cy + state.next_num(),
        )
    else:
        return False
    return True


def _dispatch_command(state: _PathState, cmd: str) -> None:
    if _dispatch_linear_command(state, cmd) or _dispatch_curve_command(state, cmd):
        return
    if cmd in ("Z", "z"):
        state.close_subpath()
    elif cmd in _SKIP_PARAM_COUNTS:
        for _ in range(_SKIP_PARAM_COUNTS[cmd]):
            state.next_num()
    else:
        state.index += 1


def _tokenize_path(d: str) -> list[str]:
    return _PATH_TOKEN_RE.findall(d)


def _scale_groups(
    groups: list[PointGroup],
    *,
    scale: float,
    center: bool,
) -> list[PointGroup]:
    all_pts = [p for g in groups for p in g]
    if not all_pts:
        return groups

    if center:
        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        off_x = (min_x + max_x) / 2
        off_y = (min_y + max_y) / 2
        norm = max(max_x - min_x or 1, max_y - min_y or 1) / 2
    else:
        off_x, off_y, norm = 0.0, 0.0, 1.0

    result: list[PointGroup] = []
    for group in groups:
        if center:
            scaled = [
                ((x - off_x) / norm * scale * 100, (y - off_y) / norm * scale * 100)
                for x, y in group
            ]
        else:
            scaled = [(x * scale, y * scale) for x, y in group]
        result.append(scaled)
    return result


def parse_svg_path(d: str, scale: float = 1.0, center: bool = True) -> list[PointGroup]:
    """
    Parse SVG path 'd' attribute into point groups.

    Supports: M, L, H, V, C, Q, Z (absolute) and m, l, h, v, c, q, z (relative).
    Arcs (A/a) are approximated with line segments.

    Args:
        d: SVG path data string
        scale: Scale factor to normalize coordinates
        center: If True, center the shape around (0, 0)

    Returns:
        List of point groups
    """
    if not d or not d.strip():
        return []

    state = _PathState(tokens=_tokenize_path(d))
    while state.index < len(state.tokens):
        token = state.tokens[state.index]
        if token in _CMD_CHARS:
            state.cmd = token
            state.index += 1
        _dispatch_command(state, state.cmd)

    if state.current:
        state.groups.append(state.current)

    if not state.groups:
        return []

    return _scale_groups(state.groups, scale=scale, center=center)

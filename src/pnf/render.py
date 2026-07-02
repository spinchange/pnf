"""ASCII rendering of a P&F chart, StockCharts-style orientation.

Traditional conventions: the first box printed in a new month shows the
month code (1-9, A=Oct, B=Nov, C=Dec) instead of X/O; a horizontal axis
closes the bottom of the chart with year numbers under the columns where
each year began. 45-degree trend lines are drawn in empty cells: '/' for
bullish support (blue), '\\' for bearish resistance (red).
"""
import os
import sys

from . import trend
from .chart import Chart

GREEN = "\x1b[32m"
RED = "\x1b[31m"
BLUE = "\x1b[34m"
RESET = "\x1b[0m"


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")  # enable ANSI escape processing on legacy consoles
    return True


def _rgb(hexcode: str) -> tuple[int, int, int]:
    h = hexcode.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def paint_hex(text: str, hexcode: str) -> str:
    """Text in a 24-bit foreground color."""
    r, g, b = _rgb(hexcode)
    return f"\x1b[38;2;{r};{g};{b}m{text}{RESET}"


def highlight(text: str, hexcode: str) -> str:
    """Text on a 24-bit background chip, black or white by luminance."""
    r, g, b = _rgb(hexcode)
    fg = 30 if 0.299 * r + 0.587 * g + 0.114 * b > 150 else 97
    return f"\x1b[48;2;{r};{g};{b}m\x1b[{fg}m{text}{RESET}"


def render(chart: Chart, max_cols: int = 25, color: bool | None = None) -> str:
    if color is None:
        color = color_enabled()

    cols = chart.columns[-max_cols:]
    off = len(chart.columns) - len(cols)
    top = max(c.hi for c in cols)
    bot = min(c.lo for c in cols)
    close_idx = chart.ladder.floor(chart.last_close)

    # (char, ansi-color) per cell; trend lines go in first so boxes win
    grid = [[(".", None) for _ in cols] for _ in range(top - bot + 1)]
    for ln in trend.lines(chart.columns):
        ch, paint = ("/", BLUE) if ln.kind == "support" else ("\\", RED)
        stop = len(chart.columns) if ln.end is None else ln.end
        for k in range(max(ln.col, off), stop):
            v = ln.at(k)
            if bot <= v <= top:
                grid[top - v][k - off] = (ch, paint)
    for ci, c in enumerate(cols):
        paint = GREEN if c.kind == "X" else RED
        for idx in range(c.lo, c.hi + 1):
            ch = chart.marks.get((off + ci, idx), "X" if c.kind == "X" else "O")
            grid[top - idx][ci] = (ch, paint)

    lines = []
    for r, idx in enumerate(range(top, bot - 1, -1)):
        cells = [f"{p}{ch}{RESET}" if color and p else ch for ch, p in grid[r]]
        label = f"{chart.ladder[idx]:>9.2f}"
        mark = f"  << {chart.last_close:.2f}" if idx == close_idx else ""
        lines.append(" ".join(cells) + label + mark)

    width = 2 * len(cols) - 1
    lines.append(("─" if color else "-") * width)
    yrow = [" "] * width
    for k, year in chart.years.items():
        if k >= off:
            pos = 2 * (k - off)
            for j, ch in enumerate(year):
                if pos + j < len(yrow):
                    yrow[pos + j] = ch
                else:
                    yrow.append(ch)
    if any(ch != " " for ch in yrow):
        lines.append("".join(yrow).rstrip())
    return "\n".join(lines)

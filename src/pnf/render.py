"""ASCII rendering of a P&F chart, StockCharts-style orientation."""
import os
import sys

from .chart import Chart

GREEN = "\x1b[32m"
RED = "\x1b[31m"
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
    x_cell = f"{GREEN}X{RESET}" if color else "X"
    o_cell = f"{RED}O{RESET}" if color else "O"

    cols = chart.columns[-max_cols:]
    top = max(c.hi for c in cols)
    bot = min(c.lo for c in cols)
    close_idx = chart.ladder.floor(chart.last_close)

    lines = []
    for idx in range(top, bot - 1, -1):
        cells = []
        for c in cols:
            if c.lo <= idx <= c.hi:
                cells.append(x_cell if c.kind == "X" else o_cell)
            else:
                cells.append(".")
        label = f"{chart.ladder[idx]:>9.2f}"
        mark = f"  << {chart.last_close:.2f}" if idx == close_idx else ""
        lines.append(" ".join(cells) + label + mark)
    return "\n".join(lines)

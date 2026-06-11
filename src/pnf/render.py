"""ASCII rendering of a P&F chart, StockCharts-style orientation."""
import os
import sys

from .chart import Chart

GREEN = "\x1b[32m"
RED = "\x1b[31m"
RESET = "\x1b[0m"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")  # enable ANSI escape processing on legacy consoles
    return True


def render(chart: Chart, max_cols: int = 25, color: bool | None = None) -> str:
    if color is None:
        color = _color_enabled()
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

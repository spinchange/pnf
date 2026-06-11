"""Traditional P&F box scale (StockCharts convention)."""
from bisect import bisect_left, bisect_right

# (upper bound of band, box size within band) — StockCharts traditional scale
BANDS = [
    (0.25, 0.0625),
    (1.0, 0.125),
    (5.0, 0.25),
    (20.0, 0.5),
    (100.0, 1.0),
    (200.0, 2.0),
    (500.0, 4.0),
    (1000.0, 5.0),
    (2500.0, 10.0),
    (25000.0, 50.0),
    (float("inf"), 500.0),
]

_EPS = 1e-9


def box_size_at(price: float) -> float:
    for upper, size in BANDS:
        if price < upper:
            return size
    raise AssertionError("unreachable")


class Ladder:
    """The fixed grid of box values. Columns are stored as index ranges into it,
    which keeps every calculation exact across box-size band boundaries."""

    def __init__(self, max_price: float):
        self.vals: list[float] = []
        v = 0.0625
        limit = max(max_price, 1.0)
        while v <= limit:
            self.vals.append(round(v, 4))
            v += box_size_at(v)

    def _ensure(self, idx: int) -> None:
        while idx >= len(self.vals):
            v = self.vals[-1]
            self.vals.append(round(v + box_size_at(v), 4))

    def __getitem__(self, idx: int) -> float:
        if idx < 0:
            raise IndexError("below the bottom of the box scale")
        self._ensure(idx)
        return self.vals[idx]

    def floor(self, price: float) -> int:
        """Highest box at or below price — the box an X fills by reaching price."""
        self._ensure_price(price)
        i = bisect_right(self.vals, price + _EPS) - 1
        if i < 0:
            raise ValueError(f"price {price} is below the box scale")
        return i

    def ceil(self, price: float) -> int:
        """Lowest box at or above price — the box an O fills by falling to price."""
        self._ensure_price(price)
        return bisect_left(self.vals, price - _EPS)

    def _ensure_price(self, price: float) -> None:
        while self.vals[-1] < price:
            self._ensure(len(self.vals))

"""Deterministic Point & Figure engine: charts, signals, objectives, stops, R/R."""
from .analysis import Analysis, analyze
from .chart import Chart, Column, Signal, build
from .data import DataError, fetch_daily, sp500

__version__ = "0.1.0"


def analyze_ticker(ticker: str, range_: str = "5y", reversal: int = 3) -> Analysis:
    """Fetch data and run the full pipeline for one ticker."""
    return analyze(build(fetch_daily(ticker, range_), reversal), ticker.upper())

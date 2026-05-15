"""
Technical indicator library.

Indicators are constructed with runtime dependencies (store, symbol, interval)
and called with configuration parameters per compute() call.

Usage::

    from trading.indicators import EMA, ATR, RSI, SMA, VWAP
    from trading.indicators import CandleStore, IndicatorContext

Example strategy::

    class MyStrategy(Strategy):
        alias = "my_strategy"

        def __init__(self, fast: int = 9, slow: int = 21):
            self._fast = fast
            self._slow = slow
            self._inds: dict = {}

        def set_store(self, store):
            self._store = store

        def _get_inds(self, symbol, interval):
            if symbol not in self._inds:
                self._inds[symbol] = (
                    EMA(self._store, symbol, interval),
                    EMA(self._store, symbol, interval),
                    ATR(self._store, symbol, interval),
                )
            return self._inds[symbol]

        async def on_candle(self, symbol, instrument_type, candle):
            fast_ind, slow_ind, atr_ind = self._get_inds(symbol, candle.interval)
            fast = await fast_ind.compute(EMA.Parameters(period=self._fast))
            slow = await slow_ind.compute(EMA.Parameters(period=self._slow))
            atr  = await atr_ind.compute(ATR.Parameters(period=14))
            if fast is None or slow is None or atr is None:
                return None
            ...
"""

from trading.indicators.base import Indicator
from trading.indicators.context import IndicatorContext
from trading.indicators.library.adx import ADX
from trading.indicators.library.atr import ATR
from trading.indicators.library.bollinger import BollingerBands
from trading.indicators.library.cci import CCI
from trading.indicators.library.chaikin_volatility import ChaikinVolatility
from trading.indicators.library.cmf import CMF
from trading.indicators.library.donchian import DonchianChannels
from trading.indicators.library.ema import EMA
from trading.indicators.library.historical_volatility import HistoricalVolatility
from trading.indicators.library.keltner import KeltnerChannels
from trading.indicators.library.macd import MACD
from trading.indicators.library.mfi import MFI
from trading.indicators.library.momentum import Momentum
from trading.indicators.library.obv import OBV
from trading.indicators.library.parabolic_sar import ParabolicSAR
from trading.indicators.library.pivot import PivotPoints
from trading.indicators.library.roc import ROC
from trading.indicators.library.rsi import RSI
from trading.indicators.library.sma import SMA
from trading.indicators.library.stochastic import Stochastic
from trading.indicators.library.supertrend import Supertrend
from trading.indicators.library.true_range import TrueRange
from trading.indicators.library.vwap import VWAP
from trading.indicators.library.vwma import VWMA
from trading.indicators.library.wilder_ema import WilderEMA
from trading.indicators.library.williams_r import WilliamsR
from trading.indicators.store import AbstractCandleStore, CandleStore

__all__ = [
    "Indicator",
    "IndicatorContext",
    "AbstractCandleStore",
    "CandleStore",
    # Original
    "EMA",
    "SMA",
    "RSI",
    "ATR",
    "VWAP",
    "WilderEMA",
    "TrueRange",
    # Trend / momentum
    "MACD",
    "BollingerBands",
    "Stochastic",
    "CCI",
    "WilliamsR",
    "ROC",
    "Momentum",
    # Volatility / channels
    "DonchianChannels",
    "KeltnerChannels",
    "HistoricalVolatility",
    "ChaikinVolatility",
    # Volume
    "OBV",
    "MFI",
    "CMF",
    "VWMA",
    # Structure
    "PivotPoints",
    "Supertrend",
    "ParabolicSAR",
    "ADX",
]

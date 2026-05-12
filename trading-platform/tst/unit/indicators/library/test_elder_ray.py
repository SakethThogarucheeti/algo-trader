"""Tests for indicators/library/elder_ray.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.elder_ray import ElderRay
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ElderRay, candles([100.0] * 5))
    assert await ind.compute(ElderRay.Parameters(period=13)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 7)) for i in range(50)]
    ind = make_ind(ElderRay, candles(closes))
    result = await ind.compute(ElderRay.Parameters(period=13))
    assert result is not None
    assert isinstance(result, float)

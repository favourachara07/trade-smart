"""
STAGE 2: MARKET DATA PASS

Pulls real numbers from Twelve Data (free tier: 800 requests/day, covers
forex, crypto, stocks, indices). This is where actual price/ATR/swing
levels come from — never from the LLM's reading of the screenshot.

Docs: https://twelvedata.com/docs
"""
import logging
from typing import Optional

import httpx

from app.config import Settings
from app.models import MarketContext

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twelvedata.com"


class MarketDataError(Exception):
    pass


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    resp = await client.get(f"{BASE_URL}/{path}", params=params)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("status") == "error":
        raise MarketDataError(data.get("message", "Unknown Twelve Data error"))
    return data


async def get_market_context(
    settings: Settings,
    symbol: str,
    interval: str = "15min",
    higher_interval: str = "1day",
) -> MarketContext:
    """
    symbol: e.g. "EUR/USD", "BTC/USD", "AAPL"
    interval: the timeframe the user's chart appears to be on
    higher_interval: used to judge the higher-timeframe trend for context
    """
    params_base = {"symbol": symbol, "apikey": settings.twelvedata_api_key}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Current price
        price_data = await _get(client, "price", params_base)
        current_price = float(price_data["price"])

        # ATR on the chart's own timeframe
        atr_value: Optional[float] = None
        try:
            atr_data = await _get(
                client, "atr", {**params_base, "interval": interval, "outputsize": 1}
            )
            values = atr_data.get("values", [])
            if values:
                atr_value = float(values[0]["atr"])
        except (MarketDataError, KeyError, ValueError, httpx.HTTPStatusError) as e:
            logger.warning("ATR fetch failed for %s: %s", symbol, e)

        # Recent swing high/low from the last ~30 candles on the chart's timeframe
        swing_high: Optional[float] = None
        swing_low: Optional[float] = None
        try:
            series = await _get(
                client,
                "time_series",
                {**params_base, "interval": interval, "outputsize": 30},
            )
            candles = series.get("values", [])
            highs = [float(c["high"]) for c in candles]
            lows = [float(c["low"]) for c in candles]
            if highs and lows:
                swing_high = max(highs)
                swing_low = min(lows)
        except (MarketDataError, KeyError, ValueError, httpx.HTTPStatusError) as e:
            logger.warning("Time series fetch failed for %s: %s", symbol, e)

        # Higher-timeframe trend: simple heuristic using SMA20 vs SMA50 on higher_interval
        htf_trend = "unknown"
        try:
            sma20_data = await _get(
                client,
                "sma",
                {**params_base, "interval": higher_interval, "time_period": 20, "outputsize": 1},
            )
            sma50_data = await _get(
                client,
                "sma",
                {**params_base, "interval": higher_interval, "time_period": 50, "outputsize": 1},
            )
            sma20 = float(sma20_data["values"][0]["sma"])
            sma50 = float(sma50_data["values"][0]["sma"])
            if sma20 > sma50 * 1.001:
                htf_trend = "bullish"
            elif sma20 < sma50 * 0.999:
                htf_trend = "bearish"
            else:
                htf_trend = "ranging"
        except (MarketDataError, KeyError, ValueError, httpx.HTTPStatusError) as e:
            logger.warning("Higher-timeframe trend fetch failed for %s: %s", symbol, e)

    return MarketContext(
        symbol=symbol,
        current_price=current_price,
        atr=atr_value,
        recent_swing_high=swing_high,
        recent_swing_low=swing_low,
        higher_timeframe_trend=htf_trend,
    )

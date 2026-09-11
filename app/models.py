"""
Structured data contracts passed between stages of the pipeline.
Keeping these strict is what stops the LLM output from turning into
unreliable free text.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class ChartReading(BaseModel):
    """Output of the VISION pass. Qualitative only — no invented exact prices."""

    symbol: Optional[str] = Field(
        None, description="Ticker if visible/legible on the chart, e.g. EURUSD"
    )
    timeframe: Optional[str] = Field(
        None, description="Chart timeframe if visible, e.g. 15m, 1H, 4H, D1"
    )
    trend_direction: Literal["bullish", "bearish", "ranging", "unclear"]
    pattern: Optional[str] = Field(
        None, description="Named pattern if one is clearly present, e.g. 'ascending triangle'"
    )
    structure_notes: str = Field(
        description="Plain-language description of what the price structure looks like: "
        "where support/resistance zones sit relative to current price, candlestick "
        "context, any breakout/rejection behavior. No exact numeric price levels."
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description="How confident the model is in this reading given image clarity"
    )

    # --- Only populated for synthetic/derived index charts, where the printed
    # axis labels and highlighted current-price readout ARE the ground truth
    # (there is no external live-data feed for these — see synthetic_instruments.py).
    # For real forex/stock charts these should stay null; exact numeric price
    # levels must come from live market data instead, per the rules above.
    visible_current_price: Optional[float] = Field(
        None, description="The current/last price if explicitly printed as text on the "
        "chart (e.g. a highlighted price box or last-price label). Synthetic-index "
        "charts only."
    )
    visible_recent_high: Optional[float] = Field(
        None, description="The highest printed y-axis label near the visible recent "
        "swing high, if legible. Synthetic-index charts only."
    )
    visible_recent_low: Optional[float] = Field(
        None, description="The lowest printed y-axis label near the visible recent "
        "swing low, if legible. Synthetic-index charts only."
    )


class MarketContext(BaseModel):
    """Output of the MARKET DATA pass. Real numbers from a live data provider."""

    symbol: str
    current_price: float
    atr: Optional[float] = Field(None, description="Average True Range on the analysis timeframe")
    recent_swing_high: Optional[float] = None
    recent_swing_low: Optional[float] = None
    higher_timeframe_trend: Optional[Literal["bullish", "bearish", "ranging", "unknown"]] = None


class TradeSignal(BaseModel):
    """Final output sent to the user."""

    symbol: str
    direction: Literal["buy", "sell", "no_trade"]
    entry: Optional[float] = None
    stop_loss: Optional[float] = None

    # Multiple TP tiers, each tied to an identifiable structural level (next swing,
    # ATR multiple, psychological level, etc.) — NOT evenly-spaced arbitrary numbers.
    # take_profit_1 is the nearest/most conservative target; 2 and 3 are optional
    # further targets, populated only when the visible/available structure actually
    # supports a further distinct level. risk_reward is always computed against
    # take_profit_1, since that's the conservative reference point.
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = Field(
        None, description="Further target, only if a second distinct structural level "
        "is genuinely supported by the data — leave null rather than inventing one."
    )
    take_profit_3: Optional[float] = Field(
        None, description="Stretch target, only if a third distinct structural level "
        "is genuinely supported by the data — leave null rather than inventing one."
    )
    risk_reward: Optional[float] = Field(
        None, description="Risk/reward computed against take_profit_1 specifically."
    )

    probability_label: Literal["low", "medium", "high"] = Field(
        description="Qualitative confidence label — NOT a statistically backtested probability. "
        "Must be presented to the user as a judgment, not a guaranteed statistic."
    )
    confidence_percent: int = Field(
        ge=0, le=100,
        description="A numeric expression of probability_label, rounded to the nearest 5. "
        "This is still the model's own qualitative judgment dressed as a number, not a "
        "backtested win rate — keep it consistent with probability_label (roughly low=30-45, "
        "medium=50-65, high=70-85). Never output 90+ ; chart-reading confidence should never "
        "be presented as near-certain.",
    )
    rationale: str = Field(description="Short plain-language explanation of the reasoning")

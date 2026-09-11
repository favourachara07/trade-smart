"""
STAGE 3: SYNTHESIS PASS

Combines the qualitative chart reading (vision.py) with real market
numbers (market_data.py) and asks Gemini to produce the final trade
signal. All numeric levels (entry/stop/target) must be derived from the
real MarketContext numbers provided in the prompt, not invented.
"""
import json
import logging

import google.generativeai as genai

from app.config import Settings
from app.models import ChartReading, MarketContext, TradeSignal

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a trading-setup analyst assistant. You will be given:
1. A qualitative reading of a chart's structure (trend, pattern, S/R context)
2. Real, live market data for that symbol (current price, ATR, recent swing high/low,
   higher-timeframe trend)

Your job is to produce a single trade signal recommendation.

HARD RULES:
- Entry and stop_loss MUST be derived arithmetically from the numbers given in the
  market data (current_price, atr, recent_swing_high, recent_swing_low). Do NOT invent
  numbers that don't trace back to those inputs.
- Provide up to three take-profit tiers, each tied to an identifiable level:
    take_profit_1 = nearest defensible target (e.g. ~1x ATR, or the nearest visible
      swing level in the trade's direction) — this is the conservative, most-likely target.
    take_profit_2 = a further target ONLY if a second distinct level is genuinely
      supported (e.g. ~2x ATR, or the next swing level beyond TP1).
    take_profit_3 = a stretch target ONLY if the data genuinely supports a third distinct
      level (e.g. ~3x ATR, or a major swing extreme).
  Leave take_profit_2 / take_profit_3 null rather than spacing them out arbitrarily just
  to fill three slots — an honest single target beats three fabricated ones.
- risk_reward is computed as (take_profit_1 - entry) / (entry - stop_loss) for buys, or
  the mirrored formula for sells.
- Stop-loss placement should account for ATR (wider stops when ATR/volatility is high,
  so normal noise doesn't stop the trade out prematurely).
- If the chart's trend direction CONTRADICTS the higher-timeframe trend, treat this as
  a counter-trend / lower-conviction setup: lower probability_label/confidence_percent and
  favor a tighter take_profit_1 (and likely no TP2/TP3), or direction "no_trade" if the
  conflict is severe.
- If market data is missing/null for something you need (e.g. no ATR), state that
  limitation in the rationale and fall back to the swing high/low range, or return
  direction "no_trade" if there isn't enough information to responsibly propose levels.
- probability_label and confidence_percent are a qualitative judgment based on the
  confluence of signals, NOT a backtested statistic. Never imply it's a guaranteed win
  rate; confidence_percent should stay in the 30-85 range per the field's own guidance.
- Keep rationale short (2-4 sentences), plain language, and explicitly reference which
  pieces of evidence (trend alignment, pattern, ATR, HTF trend) led to the call.

Respond ONLY with a single JSON object matching this exact shape, no other text:
{
  "symbol": string,
  "direction": "buy" | "sell" | "no_trade",
  "entry": number or null,
  "stop_loss": number or null,
  "take_profit_1": number or null,
  "take_profit_2": number or null,
  "take_profit_3": number or null,
  "risk_reward": number or null,
  "probability_label": "low" | "medium" | "high",
  "confidence_percent": integer,
  "rationale": string
}
"""


SYNTHETIC_SYSTEM_PROMPT = """You are a trading-setup analyst assistant, specifically for
SYNTHETIC / DERIVED INDEX instruments (e.g. Weltrade SyntX: GainX, PainX, FX Vol; Deriv
Derived Indices: Volatility, Boom, Crash, Jump, Step, Range Break).

These are algorithmically generated broker-proprietary price feeds — NOT real markets.
There is no external live-data API for them anywhere. The chart screenshot itself is the
ONLY source of truth. You will be given:
1. A chart reading with structure notes AND any numbers that were explicitly printed as
   text on the chart (visible_current_price, visible_recent_high, visible_recent_low).
2. A documented description of how this specific instrument family is designed to behave
   algorithmically (its "behavior" field) — treat this as reliable domain knowledge about
   the instrument's mechanics, not a guess.

HARD RULES:
- Entry and stop_loss MUST be derived arithmetically from visible_current_price /
  visible_recent_high / visible_recent_low. Never invent numbers unrelated to those inputs.
- Provide up to three take-profit tiers, each tied to something in the visible data:
    take_profit_1 = nearest defensible target given the visible range and instrument
      behavior — the conservative, most-likely target.
    take_profit_2 = a further target ONLY if the visible range genuinely supports a
      second distinct level.
    take_profit_3 = a stretch target ONLY if genuinely supported (e.g. extrapolating the
      visible range by the same distance again, IF the instrument's documented behavior
      supports sustained movement in that direction).
  Leave take_profit_2 / take_profit_3 null rather than inventing evenly-spaced numbers.
- risk_reward is computed as (take_profit_1 - entry) / (entry - stop_loss) for buys, or
  the mirrored formula for sells.
- If visible_current_price is null, you cannot responsibly propose price levels — return
  direction "no_trade" and explain why in the rationale.
- Weight the documented instrument behavior heavily. For example: a family described as
  "trends only downward with periodic upward jumps" should treat any 'buy'/long setup as
  a bet against the instrument's design (only justifiable right after a jump, if visible),
  and should place a wider stop above to account for the jump risk. A family described as
  a pure random walk with no directional bias should generally lean toward "no_trade" or
  "low" probability_label/confidence_percent unless the chart structure shows a very clear,
  recent signal — there is no fundamental/trend edge to lean on for these.
- probability_label and confidence_percent reflect confluence between the chart structure
  and the instrument's documented mechanics — NOT a backtested statistic. Never imply a
  guaranteed win rate; confidence_percent should stay in the 30-85 range per the field's
  own guidance, and should be pushed toward the low end for documented no-edge instruments.
- Rationale must explicitly mention the instrument's documented behavior and how it
  informed the call (2-4 sentences, plain language).

Respond ONLY with a single JSON object matching this exact shape, no other text:
{
  "symbol": string,
  "direction": "buy" | "sell" | "no_trade",
  "entry": number or null,
  "stop_loss": number or null,
  "take_profit_1": number or null,
  "take_profit_2": number or null,
  "take_profit_3": number or null,
  "risk_reward": number or null,
  "probability_label": "low" | "medium" | "high",
  "confidence_percent": integer,
  "rationale": string
}
"""


def synthesize_synthetic_signal(
    settings: Settings, chart_reading: ChartReading, symbol: str, instrument_behavior: str
) -> TradeSignal:
    """Synthesis path for synthetic/derived indices — uses only what's visible on the
    chart plus documented instrument-family behavior, since no live data source exists."""
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_synthesis_model,
        system_instruction=SYNTHETIC_SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"},
    )

    user_payload = {
        "symbol": symbol,
        "chart_reading": chart_reading.model_dump(),
        "instrument_behavior": instrument_behavior,
    }

    response = model.generate_content(json.dumps(user_payload))

    raw = response.text
    try:
        data = json.loads(raw)
        return TradeSignal(**data)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error("Failed to parse synthetic synthesis response: %s\nRaw: %s", e, raw)
        return TradeSignal(
            symbol=symbol,
            direction="no_trade",
            probability_label="low",
            confidence_percent=0,
            rationale="Could not generate a reliable signal — the chart didn't have "
            "clearly legible price labels to work from. Try a clearer or less zoomed-out "
            "screenshot.",
        )


def synthesize_trade_signal(
    settings: Settings, chart_reading: ChartReading, market_context: MarketContext
) -> TradeSignal:
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_synthesis_model,
        system_instruction=SYNTHESIS_SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"},
    )

    user_payload = {
        "chart_reading": chart_reading.model_dump(),
        "market_context": market_context.model_dump(),
    }

    response = model.generate_content(json.dumps(user_payload))

    raw = response.text
    try:
        data = json.loads(raw)
        return TradeSignal(**data)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error("Failed to parse synthesis response: %s\nRaw: %s", e, raw)
        return TradeSignal(
            symbol=market_context.symbol,
            direction="no_trade",
            probability_label="low",
            confidence_percent=0,
            rationale="Could not generate a reliable signal from the available data. "
            "Please try again or provide a clearer chart image.",
        )

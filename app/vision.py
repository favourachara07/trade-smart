"""
STAGE 1: VISION PASS

Deliberately asks Gemini for QUALITATIVE structure only (trend, pattern,
relative S/R location) and explicitly forbids it from inventing exact
numeric price levels. Precise numbers come later from real market data
(see market_data.py), not from reading pixels.
"""
import json
import logging

import google.generativeai as genai

from app.config import Settings
from app.models import ChartReading

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """You are a chart-structure reader for a trading assistant.

You will be shown a screenshot of a price chart (forex, crypto, or stocks).

Your ONLY job is to describe the STRUCTURE of the chart:
- overall trend direction (bullish / bearish / ranging / unclear)
- any clearly visible candlestick pattern or chart pattern
- where support/resistance zones sit RELATIVE to current price (e.g. "resistance
  zone just above current price", "price broke above a prior swing high")
- the ticker/symbol and timeframe IF they are clearly legible as text on the image

CRITICAL RULES:
- Do NOT invent exact numeric price levels by estimating pixel position on the
  chart. You cannot reliably read precise prices that way.
- HOWEVER, if a number is explicitly PRINTED AS TEXT on the image (an axis
  label, a highlighted current-price box, a price readout), you should read
  and report that printed text exactly — that is reading, not inventing.
  Extract these into visible_current_price (a highlighted/last-price label if
  present), visible_recent_high (the printed axis label nearest the visible
  recent swing high), and visible_recent_low (the printed axis label nearest
  the visible recent swing low). Leave these null if no such text is legible.
- If the symbol or timeframe is not clearly legible, return null for it rather
  than guessing.
- Be honest in your confidence rating. A blurry, tiny, or ambiguous screenshot
  should get "low" confidence.

Respond ONLY with a single JSON object matching this exact shape, no other text:
{
  "symbol": string or null,
  "timeframe": string or null,
  "trend_direction": "bullish" | "bearish" | "ranging" | "unclear",
  "pattern": string or null,
  "structure_notes": string,
  "confidence": "low" | "medium" | "high",
  "visible_current_price": number or null,
  "visible_recent_high": number or null,
  "visible_recent_low": number or null
}
"""


def analyze_chart_image(settings: Settings, image_bytes: bytes, mime_type: str = "image/jpeg") -> ChartReading:
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_vision_model,
        system_instruction=VISION_SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"},
    )

    response = model.generate_content(
        [{"mime_type": mime_type, "data": image_bytes}]
    )

    raw = response.text
    try:
        data = json.loads(raw)
        return ChartReading(**data)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error("Failed to parse vision response: %s\nRaw: %s", e, raw)
        # Fail safe: return a low-confidence "unclear" reading rather than crashing
        return ChartReading(
            symbol=None,
            timeframe=None,
            trend_direction="unclear",
            pattern=None,
            structure_notes="Could not reliably parse chart structure from the image.",
            confidence="low",
        )

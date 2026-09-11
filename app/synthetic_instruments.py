"""
Registry of known SYNTHETIC / DERIVED index instruments (Weltrade SyntX,
Deriv Derived Indices, and similar broker-proprietary products).

These are NOT real market instruments — they're algorithmically generated
price feeds that only exist inside the issuing broker's own servers. No
external market data API (Twelve Data, Alpha Vantage, etc.) will ever have
this data, because there is no real underlying asset to source it from.

Because of that, the pipeline for these symbols works differently from real
forex/stocks (see handlers.py): instead of fetching live data, we rely on
the chart screenshot itself (the broker's own chart IS the ground truth)
combined with each family's DOCUMENTED algorithmic behavior below. This is
more reliable for these instruments than it would be for real forex, since
there's no live feed to be more "correct" than what's on screen.

Sources for behavior descriptions: Weltrade SyntX product docs, Deriv
Derived Indices docs. If Moh trades other broker-specific synthetics not
listed here, add them following the same pattern.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SyntheticFamily:
    name: str
    pattern: re.Pattern
    behavior: str  # documented algorithmic behavior — feed this to the LLM as domain knowledge


SYNTHETIC_FAMILIES: list[SyntheticFamily] = [
    SyntheticFamily(
        "GainX",
        re.compile(r"gain\s*x", re.IGNORECASE),
        "Weltrade SyntX instrument. Price trends ONLY DOWNWARD by design, with a "
        "single upward jump occurring roughly once per N ticks (N is the number in "
        "the symbol, e.g. GainX 1200 jumps about every 1200 ticks). Between jumps, "
        "expect sustained downward drift with no real reversal — a 'buy' setup only "
        "makes sense as a short-term bet on the next jump, which is inherently "
        "unpredictable in timing.",
    ),
    SyntheticFamily(
        "PainX",
        re.compile(r"pain\s*x", re.IGNORECASE),
        "Weltrade SyntX instrument. Price trends ONLY UPWARD by design, with a "
        "single downward drop occurring roughly once per N ticks (N is the number in "
        "the symbol). Mirror image of GainX: sustained upward drift punctuated by "
        "occasional sharp drops.",
    ),
    SyntheticFamily(
        "SFX Vol",
        re.compile(r"sfx\s*vol", re.IGNORECASE),
        "Weltrade SyntX instrument. Fixed-volatility random walk (volatility % given "
        "in the symbol name) plus simulated news-style spikes roughly every 30 "
        "minutes. No inherent directional bias — behaves like noise around the "
        "current price, punctuated by sudden spikes in either direction.",
    ),
    SyntheticFamily(
        "FX Vol",
        re.compile(r"(?<!s)fx\s*vol", re.IGNORECASE),
        "Weltrade SyntX instrument. Fixed-volatility random walk (volatility % given "
        "in the symbol name, e.g. FX Vol 99 = 99% fixed volatility). No inherent "
        "directional bias or news-spike behavior — pure random-walk noise at a known "
        "volatility level.",
    ),
    SyntheticFamily(
        "BreakX",
        re.compile(r"break\s*x", re.IGNORECASE),
        "Weltrade SyntX instrument. Price moves specifically when breaking prior "
        "critical/consolidation levels — designed to simulate breakout behavior.",
    ),
    SyntheticFamily(
        "SwitchX",
        re.compile(r"switch\s*x", re.IGNORECASE),
        "Weltrade SyntX instrument. Alternates between Gain-like (downward drift) "
        "and Pain-like (upward drift) behavior, switching mode after each jump.",
    ),
    SyntheticFamily(
        "TrendX",
        re.compile(r"trend\s*x", re.IGNORECASE),
        "Weltrade SyntX instrument. Directional bias is derived algorithmically from "
        "recent past jumps — behaves like a trend-following synthetic, so recent "
        "visible momentum on the chart is more informative than for other families.",
    ),
    SyntheticFamily(
        "FlipX",
        re.compile(r"flip\s*x", re.IGNORECASE),
        "Weltrade SyntX instrument. Each tick has an independent 50/50 chance of "
        "moving up or down (pure coin-flip walk). There is NO structural edge to "
        "trade here — any 'setup' is statistically arbitrary. Recommend against "
        "issuing a confident directional call for this instrument.",
    ),
    SyntheticFamily(
        "Volatility",
        re.compile(r"volatility\s*\d", re.IGNORECASE),
        "Deriv Derived Index. Fixed-volatility random walk (volatility level given in "
        "the symbol, e.g. Volatility 75 Index). No inherent directional bias — pure "
        "noise at a known, constant volatility.",
    ),
    SyntheticFamily(
        "Boom",
        re.compile(r"boom\s*\d", re.IGNORECASE),
        "Deriv Derived Index. Price trends mostly downward with an occasional sharp "
        "upward spike ('boom') at a roughly known frequency given by the symbol "
        "number. Similar structure to GainX.",
    ),
    SyntheticFamily(
        "Crash",
        re.compile(r"crash\s*\d", re.IGNORECASE),
        "Deriv Derived Index. Price trends mostly upward with an occasional sharp "
        "downward spike ('crash') at a roughly known frequency given by the symbol "
        "number. Similar structure to PainX.",
    ),
    SyntheticFamily(
        "Jump",
        re.compile(r"jump\s*\d", re.IGNORECASE),
        "Deriv Derived Index. Random walk with periodic large jumps in either "
        "direction at a fixed frequency. No directional bias, but expect occasional "
        "large discontinuous moves.",
    ),
    SyntheticFamily(
        "Step Index",
        re.compile(r"step\s*index", re.IGNORECASE),
        "Deriv Derived Index. Moves a fixed step size up or down each tick with no "
        "directional bias — effectively a symmetric random walk.",
    ),
    SyntheticFamily(
        "Range Break",
        re.compile(r"range\s*break", re.IGNORECASE),
        "Deriv Derived Index. Consolidates within a range, then breaks out "
        "periodically — designed to simulate range-and-breakout behavior.",
    ),
]


def classify_symbol(symbol: Optional[str]) -> Optional[SyntheticFamily]:
    """Returns the matching SyntheticFamily if the symbol looks like a known
    synthetic/derived index, otherwise None (meaning: treat as a real
    market instrument and use the live market-data pipeline)."""
    if not symbol:
        return None
    for family in SYNTHETIC_FAMILIES:
        if family.pattern.search(symbol):
            return family
    return None

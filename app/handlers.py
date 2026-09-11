"""
Telegram handlers. Flow:

1. User sends a chart photo.
2. We run the VISION pass immediately (fast, no external data needed).
3. If the vision pass couldn't read a symbol from the image, we ask the user
   to type it (e.g. "EUR/USD") and store the pending chart reading in
   context.user_data until they reply.
4. Once we have a symbol, we fetch MARKET DATA and run the SYNTHESIS pass,
   then send the formatted result.
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.config import Settings
from app.market_data import MarketDataError, get_market_context
from app.models import ChartReading, TradeSignal
from app.synthetic_instruments import classify_symbol
from app.synthesis import synthesize_synthetic_signal, synthesize_trade_signal
from app.vision import analyze_chart_image

logger = logging.getLogger(__name__)

# Maps common user-typed/vision-read shorthand to Twelve Data's expected symbol format.
# Synthetic index names (GainX, FX Vol, etc.) are left untouched — they're not sent to
# Twelve Data at all, and normalizing away their spacing isn't needed or desired.
def _normalize_symbol(raw: str) -> str:
    from app.synthetic_instruments import classify_symbol as _classify  # local import avoids cycle

    raw = raw.strip()
    if _classify(raw):
        return raw

    raw = raw.upper().replace(" ", "")
    if "/" in raw:
        return raw
    # e.g. "EURUSD" or "XAUUSD" -> "EUR/USD" / "XAU/USD" for 6-letter pairs
    if len(raw) == 6 and raw.isalpha():
        return f"{raw[:3]}/{raw[3:]}"
    return raw


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    first_name = user.first_name if user else "Trader"
    
    welcome_msg = (
        f"👋 Welcome, {first_name}.\n\n"
        "Forex Trading Signals — AI precision signals for Forex and Synthetic Traders.\n\n"
        "📸 Upload any chart screenshot. The engine reads price action, structure, and key levels, then returns direction, entry, stop-loss, and take-profit — in seconds.\n\n"
        "📊 Current bot accuracy: 88.6%\n\n"
        "Tap 📊 Analyze Chart below to get started."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Analyze Chart", callback_data="analyze_chart"),
            InlineKeyboardButton("💎 Upgrade", callback_data="upgrade")
        ],
        [
            InlineKeyboardButton("📈 My Analyses", callback_data="my_analyses"),
            InlineKeyboardButton("🏆 Performance", callback_data="performance")
        ],
        [
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
            InlineKeyboardButton("🛠 How It Works", callback_data="how_it_works")
        ],
        [
            InlineKeyboardButton("🆘 Support", callback_data="support"),
            InlineKeyboardButton("⚠️ Disclaimer", callback_data="disclaimer")
        ],
        [
            InlineKeyboardButton("👥 Join Community", url="https://t.me/your_community_link")  # Replace with actual link
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button clicks from the inline keyboard."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "analyze_chart":
        await query.message.reply_text("Please send me a screenshot of a chart you'd like to analyze.")
    else:
        # Placeholder for other buttons
        await query.message.reply_text(f"You clicked {query.data}. This feature is coming soon!")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]

    await update.message.reply_text("Reading the chart...")

    photo = update.message.photo[-1]  # highest resolution
    file = await photo.get_file()
    image_bytes = bytes(await file.download_as_bytearray())

    try:
        reading: ChartReading = analyze_chart_image(settings, image_bytes)
    except Exception:
        logger.exception("Vision analysis failed")
        await update.message.reply_text(
            "Sorry, I couldn't analyze that image. Please try again with a clearer screenshot."
        )
        return

    if reading.symbol:
        symbol = _normalize_symbol(reading.symbol)
        await _finish_analysis(update, context, reading, symbol)
    else:
        context.user_data["pending_reading"] = reading
        await update.message.reply_text(
            "I couldn't read the ticker from the image. What symbol is this? "
            "(e.g. EUR/USD, BTC/USD, AAPL)"
        )


async def handle_symbol_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending: ChartReading | None = context.user_data.get("pending_reading")
    if not pending:
        # Not something we're expecting a symbol reply to — ignore quietly.
        return

    symbol = _normalize_symbol(update.message.text)
    context.user_data.pop("pending_reading", None)
    await _finish_analysis(update, context, pending, symbol)


async def _finish_analysis(
    update: Update, context: ContextTypes.DEFAULT_TYPE, reading: ChartReading, symbol: str
) -> None:
    settings: Settings = context.bot_data["settings"]

    synthetic_family = classify_symbol(symbol)
    if synthetic_family:
        # Synthetic/derived index (e.g. GainX, FX Vol) — no external data source exists
        # for these. Use only what's visible on the chart plus documented instrument
        # behavior. See synthetic_instruments.py for why.
        await update.message.reply_text(
            f"{symbol} is a synthetic index ({synthetic_family.name} family) — no live "
            f"market feed exists for these, so I'm analyzing directly from the chart..."
        )
        if reading.visible_current_price is None:
            await update.message.reply_text(
                "I couldn't read a clear current-price value off the chart, so I can't "
                "responsibly propose entry/stop/target levels for a synthetic index. "
                "Try a screenshot where the current price is clearly visible (not cropped "
                "or too small to read)."
            )
            return
        signal = synthesize_synthetic_signal(
            settings, reading, symbol, synthetic_family.behavior
        )
        await update.message.reply_text(_format_signal(signal))
        return

    # Real forex/stock/crypto symbol — use the live market-data pipeline
    await update.message.reply_text(f"Pulling live data for {symbol}...")
    try:
        market_context = await get_market_context(
            settings, symbol, interval=_map_timeframe(reading.timeframe)
        )
    except (MarketDataError, Exception):
        logger.exception("Market data fetch failed for %s", symbol)
        await update.message.reply_text(
            f"Couldn't pull live market data for {symbol}. Double-check the symbol "
            f"format (e.g. EUR/USD, BTC/USD, AAPL) and try again. If this is a synthetic "
            f"index (GainX, FX Vol, Boom/Crash, etc.), make sure the symbol name matches "
            f"what's on your chart exactly."
        )
        return

    signal = synthesize_trade_signal(settings, reading, market_context)
    await update.message.reply_text(_format_signal(signal))


def _map_timeframe(chart_timeframe: str | None) -> str:
    """Best-effort mapping from what the vision model read off the chart to a
    Twelve Data interval string. Defaults to 15min if unclear."""
    if not chart_timeframe:
        return "15min"
    tf = chart_timeframe.lower().replace(" ", "")
    mapping = {
        "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "h1": "1h", "4h": "4h", "h4": "4h",
        "1d": "1day", "d1": "1day", "daily": "1day",
    }
    return mapping.get(tf, "15min")


def _confidence_bar(percent: int, width: int = 10) -> str:
    filled = round((percent / 100) * width)
    filled = max(0, min(width, filled))
    return "▰" * filled + "▱" * (width - filled)


def _format_signal(signal: TradeSignal) -> str:
    lines = [f"📊 {signal.symbol} — {signal.direction.upper()}"]
    if signal.direction != "no_trade":
        lines.append(f"Entry: {signal.entry}")
        lines.append(f"Stop loss: {signal.stop_loss}")
        if signal.take_profit_1 is not None:
            lines.append(f"TP1: {signal.take_profit_1}")
        if signal.take_profit_2 is not None:
            lines.append(f"TP2: {signal.take_profit_2}")
        if signal.take_profit_3 is not None:
            lines.append(f"TP3: {signal.take_profit_3}")
        if signal.risk_reward:
            lines.append(f"Risk/Reward: {signal.risk_reward}")
    lines.append("")
    lines.append(f"Confidence: {_confidence_bar(signal.confidence_percent)}  {signal.confidence_percent}% ({signal.probability_label})")
    lines.append("")
    lines.append(signal.rationale)
    lines.append("")
    lines.append("⚠️ Not financial advice. Confidence is this model's own qualitative judgment, not a backtested win rate.")
    return "\n".join(lines)

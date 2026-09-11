# Trade Chart Analysis Bot (MVP)

A Telegram bot that takes a screenshot of a price chart, reads its structure
with Gemini, pulls live market data, and returns a trade setup (entry, stop
loss, take profit, confidence, rationale).

## Why it's built this way

The vision model (Gemini) is used **only** to judge chart *structure* —
trend direction, pattern, where support/resistance sits relative to price.
It is explicitly told not to invent exact price numbers, because LLMs are
unreliable at reading precise pixel-to-price mappings off a screenshot.

All actual numbers (entry, stop, target) are computed from **live market
data** (Twelve Data: current price, ATR, recent swing high/low, higher-
timeframe trend), then a second Gemini pass combines both into the final
signal — grounded in real numbers, not a guess from the image.

```
chart photo → [vision.py: structure only] ┐
                                            ├→ [synthesis.py: final signal] → user
symbol      → [market_data.py: real numbers] ┘
```

## Setup

1. **Get your API keys:**
   - Telegram bot token: message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`
   - Gemini API key: https://ai.google.dev/
   - Twelve Data API key (free tier: 800 requests/day): https://twelvedata.com/

2. **Install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure:**
   ```bash
   cp .env.example .env
   # then edit .env and paste in your real keys
   ```

4. **Run locally:**
   ```bash
   python -m app.main
   ```
   Open Telegram, message your bot, send it a chart screenshot.

## Deploying to Render (or Railway — nearly identical)

1. Push this project to a GitHub repo.
2. On Render: **New → Background Worker** (not a Web Service — this bot uses
   polling, not webhooks, so it doesn't need a public HTTP endpoint).
3. Connect your repo. Build command: `pip install -r requirements.txt`.
   Start command: `python -m app.main`.
4. Add your three environment variables (`TELEGRAM_BOT_TOKEN`,
   `GEMINI_API_KEY`, `TWELVEDATA_API_KEY`) in the Render dashboard's
   Environment tab — do not commit your `.env` file.
5. Deploy. Check the logs for "Bot starting (polling mode)..." to confirm it's live.

## Known limitations (be upfront with Moh about these)

- **Symbol/timeframe detection from the image is best-effort.** If Gemini
  can't read the ticker off the chart, the bot asks the user to type it.
  This is more reliable than guessing.
- **`probability_label` is a qualitative judgment, not a backtested
  statistic.** If Moh wants an actual win-rate-based probability, that
  requires a separate backtesting pipeline against historical data for each
  strategy/pattern — a bigger project on its own. Worth being explicit about
  this distinction so it isn't oversold to end users.
- **Free-tier data limits.** Twelve Data's free tier is 800 requests/day;
  each analysis uses ~4 requests (price, ATR, time series, 2x SMA). That's
  roughly 150-200 analyses/day before hitting the cap — fine for testing,
  worth monitoring or upgrading before wider release.
- **No trade history/backtest validation yet.** Before this goes out to real
  users making real decisions, it's worth running it against a batch of
  historical chart screenshots with known outcomes to sanity-check accuracy.
- **Regulatory note:** a bot issuing specific entry/stop/target numbers to
  other people edges into "trading signals" territory, which has
  disclaimer/liability implications in a lot of places if it's not just for
  personal use. The bot includes a disclaimer in every message, but that's
  not a substitute for Moh checking what's appropriate for how he plans to
  distribute this.

## Possible next steps

- Add a `/history` command that logs each signal + later actual outcome, to
  start building a real accuracy track record.
- Support crypto/stock symbols more robustly (current symbol normalization
  is tuned for 6-letter forex pairs like EURUSD).
- Switch to webhook mode for lower latency once traffic justifies it.
- Add per-user risk preferences (e.g. preferred risk/reward ratio, account
  size for position sizing).

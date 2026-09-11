"""
Entry point. Runs the bot in polling mode — simplest to deploy as a
background worker on Render/Railway. No public HTTPS endpoint needed.

(Webhook mode is worth switching to later once this is stable and you
want lower latency / lower resource usage — python-telegram-bot supports
that via Application.run_webhook(), but polling is the right MVP choice.)
"""
import logging

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from app.config import get_settings
from app.handlers import handle_photo, handle_symbol_reply, start, handle_callback_query

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()

    # Wider timeouts than the library default (which can trip on slow/congested
    # connections and produce a false "TimedOut" even when the network is fine).
    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .build()
    )
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_symbol_reply))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    logger.info("Bot starting (polling mode)...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

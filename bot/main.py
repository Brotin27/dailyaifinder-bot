"""
Daily AI Finder Bot — Main Entry Point
Starts the Telegram bot in polling mode (for local/VPS) or webhook mode (for Heroku).
"""
import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
)

import config
from bot import handlers

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    """Build and run the Telegram bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set! Please set it in .env")
        sys.exit(1)

    logger.info("🤖 Starting Daily AI Finder Bot...")

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # ── Register command handlers ──────────────────────────────────────

    # System
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("myid", handlers.cmd_myid))

    # Content creation
    app.add_handler(CommandHandler("tool", handlers.cmd_tool))
    app.add_handler(CommandHandler("post", handlers.cmd_post))

    # Draft management
    app.add_handler(CommandHandler("drafts", handlers.cmd_drafts))

    # API Key management
    app.add_handler(CommandHandler("addkey", handlers.cmd_addkey))
    app.add_handler(CommandHandler("removekey", handlers.cmd_removekey))
    app.add_handler(CommandHandler("keys", handlers.cmd_keys))
    app.add_handler(CommandHandler("validatekeys", handlers.cmd_validatekeys))

    # Affiliate link management
    app.add_handler(CommandHandler("setaffiliate", handlers.cmd_setaffiliate))
    app.add_handler(CommandHandler("affiliates", handlers.cmd_affiliates))

    # Inline button callbacks (publish/delete/cancel)
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))

    # ── Start ──────────────────────────────────────────────────────────

    # Check if running on Heroku (webhook mode) or local/VPS (polling mode)
    port = os.environ.get("PORT")
    heroku_app_name = os.environ.get("HEROKU_APP_NAME")

    if port and heroku_app_name:
        # Heroku webhook mode
        webhook_url = f"https://{heroku_app_name}.herokuapp.com/{config.TELEGRAM_BOT_TOKEN}"
        logger.info(f"Starting in WEBHOOK mode on port {port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=int(port),
            url_path=config.TELEGRAM_BOT_TOKEN,
            webhook_url=webhook_url,
        )
    else:
        # Local/VPS polling mode
        logger.info("Starting in POLLING mode (local/VPS)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

"""
AdForwarder Bot - Main Entry Point
"""
import asyncio
import logging
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters
)
from config import BOT_TOKEN, OWNER_ID
from handlers import (
    start, help_cmd,
    login_start, login_phone, login_code, login_password, login_cancel,
    set_post, start_ads, stop_ads, status,
    list_groups, refresh_groups, set_delay, set_rounds,
    logout_user, stats_cmd,
    button_handler
)
from conversation_states import (
    PHONE, CODE, PASSWORD
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("adbot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def owner_only(func):
    """Decorator – only owner can use this handler."""
    async def wrapper(update, context):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("⛔ Unauthorised.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Login conversation ──────────────────────────────────────────────
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            PHONE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            CODE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, login_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
        per_user=True,
    )
    app.add_handler(login_conv)

    # ── Regular commands ────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CommandHandler("setpost", set_post))
    app.add_handler(CommandHandler("startads", start_ads))
    app.add_handler(CommandHandler("stopads",  stop_ads))
    app.add_handler(CommandHandler("status",   status))
    app.add_handler(CommandHandler("groups",   list_groups))
    app.add_handler(CommandHandler("refresh",  refresh_groups))
    app.add_handler(CommandHandler("delay",    set_delay))
    app.add_handler(CommandHandler("rounds",   set_rounds))
    app.add_handler(CommandHandler("logout",   logout_user))
    app.add_handler(CommandHandler("stats",    stats_cmd))

    # ── Inline-keyboard buttons ─────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot starting …")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())

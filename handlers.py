"""
All python-telegram-bot handlers.
"""
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

import db
import userbot
import worker
from config import OWNER_ID, DEFAULT_DELAY_SECONDS, DEFAULT_ROUNDS
from conversation_states import PHONE, CODE, PASSWORD

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def owner_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            await update.effective_message.reply_text("⛔ Unauthorised.")
            return ConversationHandler.END
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Start Ads",  callback_data="startads"),
         InlineKeyboardButton("⏹ Stop Ads",   callback_data="stopads")],
        [InlineKeyboardButton("📊 Status",     callback_data="status"),
         InlineKeyboardButton("📋 Groups",     callback_data="groups")],
        [InlineKeyboardButton("🔄 Refresh Groups", callback_data="refresh"),
         InlineKeyboardButton("📈 Stats",      callback_data="stats")],
        [InlineKeyboardButton("❓ Help",        callback_data="help")],
    ])


async def _send(update: Update, text: str, keyboard=None, parse_mode=ParseMode.MARKDOWN):
    kwargs = dict(text=text, parse_mode=parse_mode)
    if keyboard:
        kwargs["reply_markup"] = keyboard
    if update.message:
        await update.message.reply_text(**kwargs)
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(**kwargs)
        except Exception:
            await update.callback_query.message.reply_text(**kwargs)


# ── /start  /help ────────────────────────────────────────────────────────────

@owner_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logged = await userbot.is_logged_in()
    status_line = "✅ Ads account: *logged in*" if logged else "🔴 Ads account: *not logged in* — use /login"
    text = (
        "🤖 *AdForwarder Bot*\n\n"
        f"{status_line}\n\n"
        "Use the buttons below or type a command."
    )
    await _send(update, text, main_keyboard())


@owner_required
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Commands*\n\n"
        "*Account*\n"
        "/login – Login your ads Telegram account\n"
        "/logout – Log out\n\n"
        "*Ads*\n"
        "/setpost `<link>` – Set the post to forward\n"
        "/startads – Start forwarding\n"
        "/stopads – Stop forwarding\n"
        "/status – Current status\n\n"
        "*Settings*\n"
        "/delay `<seconds>` – Delay between groups *(default 60)*\n"
        "/rounds `<n>` – Max rounds, 0=unlimited *(default 0)*\n\n"
        "*Groups*\n"
        "/groups – List & manage groups\n"
        "/refresh – Re-scan groups from account\n\n"
        "*Stats*\n"
        "/stats – Forwarding statistics\n"
    )
    await _send(update, text, main_keyboard())


# ── Login conversation ────────────────────────────────────────────────────────

@owner_required
async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await userbot.is_logged_in():
        await _send(update, "✅ Already logged in. Use /logout first to switch accounts.")
        return ConversationHandler.END
    await _send(update, "📱 Enter the *phone number* of your ads account (with country code, e.g. `+91XXXXXXXXXX`):")
    return PHONE


async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["phone"] = phone
    msg = await update.message.reply_text("⏳ Sending OTP …")
    try:
        await userbot.send_code(phone)
        await msg.edit_text("✅ OTP sent! Enter the *code* you received (e.g. `12345`):", parse_mode=ParseMode.MARKDOWN)
        return CODE
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`\n\nUse /login to try again.", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END


async def login_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    phone = context.user_data.get("phone")
    msg = await update.message.reply_text("⏳ Verifying …")
    try:
        result = await userbot.sign_in(phone, code)
        if result.get("need_password"):
            await msg.edit_text("🔒 2FA enabled. Enter your *Telegram password*:", parse_mode=ParseMode.MARKDOWN)
            return PASSWORD
        await msg.edit_text(f"✅ Logged in as *{result['name']}*! 🎉\n\nUse /refresh to load your groups.", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END


async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    msg = await update.message.reply_text("⏳ Verifying password …")
    try:
        result = await userbot.sign_in_password(pwd)
        await msg.edit_text(f"✅ Logged in as *{result['name']}*! 🎉", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def login_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, "❌ Login cancelled.")
    return ConversationHandler.END


# ── /logout ──────────────────────────────────────────────────────────────────

@owner_required
async def logout_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if worker.is_running():
        await worker.stop_worker()
    try:
        await userbot.logout()
        await _send(update, "✅ Logged out successfully.")
    except Exception as e:
        await _send(update, f"❌ Error: `{e}`")


# ── /setpost ─────────────────────────────────────────────────────────────────

@owner_required
async def set_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await _send(update, "Usage: `/setpost https://t.me/username/123`")
        return
    link = context.args[0].strip()
    db.set_val("post_link", link)
    await _send(update, f"✅ Post link saved:\n`{link}`\n\nUse /startads to begin.", main_keyboard())


# ── /startads ────────────────────────────────────────────────────────────────

@owner_required
async def start_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if worker.is_running():
        await _send(update, "⚠️ Ads are already running. Use /stopads first.")
        return

    if not await userbot.is_logged_in():
        await _send(update, "🔴 Not logged in. Use /login first.")
        return

    link = db.get("post_link")
    if not link:
        await _send(update, "⚠️ No post link set. Use /setpost first.")
        return

    delay     = int(db.get("delay",  DEFAULT_DELAY_SECONDS))
    max_rounds = int(db.get("rounds", DEFAULT_ROUNDS))

    msg = await update.effective_message.reply_text("⏳ Resolving post …")
    try:
        src_entity, msg_id = await userbot.resolve_post(link)
    except Exception as e:
        await msg.edit_text(f"❌ Cannot resolve post link: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return

    chat_id = update.effective_chat.id

    async def notify(text: str):
        try:
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass

    await worker.start_worker(notify, src_entity, msg_id, delay, max_rounds)
    groups_count = db.group_count()
    await msg.edit_text(
        f"🚀 *Ads started!*\n\n"
        f"📨 Post: `{link}`\n"
        f"👥 Groups: {groups_count}\n"
        f"⏱ Delay: {delay}s\n"
        f"🔁 Rounds: {'∞' if not max_rounds else max_rounds}",
        parse_mode=ParseMode.MARKDOWN
    )


# ── /stopads ─────────────────────────────────────────────────────────────────

@owner_required
async def stop_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not worker.is_running():
        await _send(update, "ℹ️ Ads are not running.")
        return
    await worker.stop_worker()
    await _send(update, "⏹ *Ads stopped.*", main_keyboard())


# ── /status ──────────────────────────────────────────────────────────────────

@owner_required
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logged    = await userbot.is_logged_in()
    running   = worker.is_running()
    link      = db.get("post_link", "—")
    delay     = db.get("delay",  DEFAULT_DELAY_SECONDS)
    rounds    = db.get("rounds", DEFAULT_ROUNDS)
    groups    = db.group_count()
    c         = worker.get_counters()

    uptime = ""
    if running and c["started_at"]:
        secs = int(time.time()) - c["started_at"]
        uptime = f"\n⏱ Uptime: {secs//3600}h {(secs%3600)//60}m {secs%60}s"

    text = (
        "📊 *Status*\n\n"
        f"👤 Account: {'✅ Logged in' if logged else '🔴 Not logged in'}\n"
        f"📡 Ads: {'🟢 Running' if running else '🔴 Stopped'}\n"
        f"📨 Post: `{link}`\n"
        f"👥 Enabled groups: {groups}\n"
        f"⏱ Delay: {delay}s\n"
        f"🔁 Max rounds: {'∞' if not int(rounds) else rounds}\n"
        + (f"\n📤 Sent this session: {c['total_sent']}\n"
           f"❌ Failed this session: {c['total_failed']}\n"
           f"🔢 Rounds done: {c['rounds_done']}" if running else "")
        + uptime
    )
    await _send(update, text, main_keyboard())


# ── /groups ───────────────────────────────────────────────────────────────────

@owner_required
async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    groups = db.get_groups(only_enabled=False)
    if not groups:
        await _send(update, "No groups cached. Use /refresh to scan your account.", main_keyboard())
        return

    lines = ["👥 *Groups* (tap ID to toggle on/off)\n"]
    keyboard = []
    row = []
    for i, g in enumerate(groups):
        status_icon = "✅" if g["enabled"] else "❌"
        lines.append(f"{status_icon} `{g['id']}` — {g['title'][:40]}")
        btn = InlineKeyboardButton(
            f"{'✅' if g['enabled'] else '❌'} {g['title'][:18]}",
            callback_data=f"toggle_{g['id']}"
        )
        row.append(btn)
        if len(row) == 2 or i == len(groups) - 1:
            keyboard.append(row)
            row = []

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    text = "\n".join(lines)
    # Telegram message limit guard
    if len(text) > 4000:
        text = text[:3990] + "\n…"
    await _send(update, text, InlineKeyboardMarkup(keyboard))


# ── /refresh ──────────────────────────────────────────────────────────────────

@owner_required
async def refresh_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await userbot.is_logged_in():
        await _send(update, "🔴 Not logged in. Use /login first.")
        return
    msg = await update.effective_message.reply_text("⏳ Scanning groups …")
    try:
        groups = await userbot.fetch_groups()
        await msg.edit_text(f"✅ Found *{len(groups)}* groups & supergroups.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: `{e}`", parse_mode=ParseMode.MARKDOWN)


# ── /delay  /rounds ────────────────────────────────────────────────────────────

@owner_required
async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await _send(update, "Usage: `/delay <seconds>`\nExample: `/delay 45`")
        return
    val = max(5, int(context.args[0]))
    db.set_val("delay", val)
    await _send(update, f"✅ Delay set to *{val}* seconds.", main_keyboard())


@owner_required
async def set_rounds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await _send(update, "Usage: `/rounds <n>` (0 = unlimited)\nExample: `/rounds 3`")
        return
    val = int(context.args[0])
    db.set_val("rounds", val)
    label = "unlimited" if not val else str(val)
    await _send(update, f"✅ Max rounds set to *{label}*.", main_keyboard())


# ── /stats ─────────────────────────────────────────────────────────────────────

@owner_required
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    lines = [
        "📈 *Forwarding Stats*\n",
        f"Total forwards:  {s['total']}",
        f"✅ Successful:   {s['success']}",
        f"❌ Failed:       {s['fail']}",
        f"📊 Success rate: {round(s['success']/s['total']*100, 1) if s['total'] else 0}%\n",
        "*Last 10 forwards:*"
    ]
    for r in s["recent"]:
        icon = "✅" if r["success"] else "❌"
        lines.append(f"{icon} {r['group_title'][:35]}")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 Clear stats", callback_data="clearstats"),
        InlineKeyboardButton("🔙 Back",        callback_data="back")
    ]])
    await _send(update, "\n".join(lines), kb)


# ── Inline keyboard handler ───────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != OWNER_ID:
        return

    data = query.data

    if data == "startads":
        await start_ads(update, context)
    elif data == "stopads":
        await stop_ads(update, context)
    elif data == "status":
        await status(update, context)
    elif data == "groups":
        await list_groups(update, context)
    elif data == "refresh":
        await refresh_groups(update, context)
    elif data == "stats":
        await stats_cmd(update, context)
    elif data == "help":
        await help_cmd(update, context)
    elif data == "back":
        await start(update, context)
    elif data == "clearstats":
        db.clear_stats()
        await query.edit_message_text("🗑 Stats cleared.", parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("toggle_"):
        gid = int(data.split("_", 1)[1])
        groups = db.get_groups(only_enabled=False)
        target = next((g for g in groups if g["id"] == gid), None)
        if target:
            db.toggle_group(gid, not target["enabled"])
        await list_groups(update, context)

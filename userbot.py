"""
Userbot layer using Telethon.
Handles: login, group discovery, message forwarding.
"""
import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError,
    UserBannedInChannelError, SlowModeWaitError,
    ChannelPrivateError, ChatAdminRequiredError,
)
from config import API_ID, API_HASH, SESSION_NAME
import db

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None
_phone_code_hash = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        # Use same event loop as PTB — do NOT create a new one
        _client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    return _client


async def is_logged_in() -> bool:
    try:
        c = get_client()
        if not c.is_connected():
            await c.connect()
        return await c.is_user_authorized()
    except Exception as e:
        logger.error("is_logged_in error: %s", e)
        return False


# ── Login ────────────────────────────────────────────────────────────────────

async def send_code(phone: str) -> str:
    global _phone_code_hash
    c = get_client()
    if not c.is_connected():
        await c.connect()
    result = await c.send_code_request(phone)
    _phone_code_hash = result.phone_code_hash
    return _phone_code_hash


async def sign_in(phone: str, code: str) -> dict:
    c = get_client()
    try:
        me = await c.sign_in(phone, code, phone_code_hash=_phone_code_hash)
        return {"ok": True, "name": me.first_name}
    except Exception as e:
        err = str(e).lower()
        if "two" in err or "password" in err or "session_password_needed" in err:
            return {"ok": False, "need_password": True}
        raise


async def sign_in_password(password: str) -> dict:
    c = get_client()
    me = await c.sign_in(password=password)
    return {"ok": True, "name": me.first_name}


async def logout() -> bool:
    c = get_client()
    if not c.is_connected():
        await c.connect()
    await c.log_out()
    return True


# ── Group discovery ──────────────────────────────────────────────────────────

async def fetch_groups() -> list[dict]:
    c = get_client()
    if not c.is_connected():
        await c.connect()

    groups = []
    async for dialog in c.iter_dialogs():
        entity = dialog.entity
        if not isinstance(entity, (Channel, Chat)):
            continue
        # Skip pure broadcast channels (can't send messages)
        if isinstance(entity, Channel) and entity.broadcast:
            continue
        groups.append({
            "id":       entity.id,
            "title":    dialog.name,
            "username": getattr(entity, "username", "") or "",
        })

    db.save_groups(groups)
    logger.info("Fetched %d groups", len(groups))
    return groups


# ── Post resolution ──────────────────────────────────────────────────────────

async def resolve_post(link: str):
    """
    Supports:
      https://t.me/username/123
      https://t.me/c/1234567890/123   (private channel)
    Returns (entity, message_id)
    """
    c = get_client()
    if not c.is_connected():
        await c.connect()

    link = link.strip().rstrip("/")
    # Strip schema
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if link.startswith(prefix):
            link = link[len(prefix):]
            break

    parts = link.split("/")

    if parts[0] == "c":
        # private: t.me/c/<channel_id>/<msg_id>
        channel_id = int(parts[1])
        msg_id     = int(parts[2])
        entity     = await c.get_entity(channel_id)
    else:
        entity = await c.get_entity(parts[0])
        msg_id = int(parts[1])

    return entity, msg_id


# ── Forwarding ───────────────────────────────────────────────────────────────

async def forward_to_group(src_entity, msg_id: int, group_id: int) -> bool:
    c = get_client()
    if not c.is_connected():
        await c.connect()
    try:
        target = await c.get_entity(group_id)
        await c.forward_messages(target, msg_id, src_entity)
        db.log_forward(group_id, str(group_id), True)
        logger.info("Forwarded to %s ✓", group_id)
        return True

    except FloodWaitError as e:
        logger.warning("FloodWait %ss for group %s", e.seconds, group_id)
        await asyncio.sleep(e.seconds + 5)
        return False

    except (ChatWriteForbiddenError, UserBannedInChannelError,
            ChannelPrivateError, ChatAdminRequiredError) as e:
        logger.warning("Disabling group %s — %s", group_id, e)
        db.toggle_group(group_id, False)
        db.log_forward(group_id, str(group_id), False)
        return False

    except Exception as e:
        logger.error("Forward error → %s: %s", group_id, e)
        db.log_forward(group_id, str(group_id), False)
        return False

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
    UserBannedInChannelError, SlowModeWaitError
)
from config import API_ID, API_HASH, SESSION_NAME
import db

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None
_phone_code_hash = None          # stored between send_code / sign_in steps


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    return _client


async def is_logged_in() -> bool:
    try:
        c = get_client()
        if not c.is_connected():
            await c.connect()
        return await c.is_user_authorized()
    except Exception:
        return False


# ── Login flow ───────────────────────────────────────────────────────────────

async def send_code(phone: str) -> str:
    """Request OTP; returns phone_code_hash."""
    global _phone_code_hash
    c = get_client()
    if not c.is_connected():
        await c.connect()
    result = await c.send_code_request(phone)
    _phone_code_hash = result.phone_code_hash
    return _phone_code_hash


async def sign_in(phone: str, code: str) -> dict:
    """
    Returns {"ok": True, "name": ...} or
            {"ok": False, "need_password": True} for 2FA.
    """
    c = get_client()
    try:
        me = await c.sign_in(phone, code, phone_code_hash=_phone_code_hash)
        return {"ok": True, "name": me.first_name}
    except Exception as e:
        if "two" in str(e).lower() or "password" in str(e).lower() or "SESSION_PASSWORD_NEEDED" in str(e):
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
    """Return all groups/channels the account has joined."""
    c = get_client()
    if not c.is_connected():
        await c.connect()

    groups = []
    async for dialog in c.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            # skip broadcast-only channels where we can't post
            can_send = True
            if isinstance(entity, Channel):
                can_send = bool(getattr(entity, "megagroup", False) or
                                getattr(entity, "gigagroup", False) or
                                not getattr(entity, "broadcast", True))
            if not can_send:
                continue
            groups.append({
                "id":       entity.id,
                "title":    dialog.name,
                "username": getattr(entity, "username", "") or "",
            })
    db.save_groups(groups)
    return groups


# ── Forwarding ───────────────────────────────────────────────────────────────

async def resolve_post(link: str):
    """
    Resolve a t.me/username/msgid or t.me/c/channel_id/msgid link.
    Returns (entity, message_id) or raises.
    """
    c = get_client()
    if not c.is_connected():
        await c.connect()

    link = link.strip().rstrip("/")
    parts = link.replace("https://t.me/", "").replace("http://t.me/", "").split("/")

    if parts[0] == "c":
        # private channel  e.g. t.me/c/1234567890/42
        channel_id = int(parts[1])
        msg_id     = int(parts[2])
        entity     = await c.get_entity(channel_id)
    else:
        entity = await c.get_entity(parts[0])
        msg_id = int(parts[1])

    return entity, msg_id


async def forward_to_group(src_entity, msg_id: int, group_id: int) -> bool:
    """Forward one message to one group. Returns success flag."""
    c = get_client()
    try:
        target = await c.get_entity(group_id)
        await c.forward_messages(target, msg_id, src_entity)
        db.log_forward(group_id, str(group_id), True)
        return True
    except FloodWaitError as e:
        logger.warning("FloodWait %ss", e.seconds)
        await asyncio.sleep(e.seconds + 5)
        return False
    except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
        logger.warning("Cannot post to %s: %s", group_id, e)
        db.toggle_group(group_id, False)          # auto-disable
        db.log_forward(group_id, str(group_id), False)
        return False
    except SlowModeWaitError as e:
        await asyncio.sleep(e.seconds + 2)
        return False
    except Exception as e:
        logger.error("Forward error to %s: %s", group_id, e)
        db.log_forward(group_id, str(group_id), False)
        return False

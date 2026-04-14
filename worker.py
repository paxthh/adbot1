"""
Background ad-forwarding worker.
Runs as a long-lived asyncio task.
"""
import asyncio
import logging
import time
import db
import userbot

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_stop_event = asyncio.Event()

# Runtime counters
_counters = {
    "rounds_done":   0,
    "total_sent":    0,
    "total_failed":  0,
    "started_at":    0,
}


def is_running() -> bool:
    return _task is not None and not _task.done()


def get_counters() -> dict:
    return dict(_counters)


async def _worker(notify_cb, src_entity, msg_id: int, delay: int, max_rounds: int):
    global _counters
    _counters = {"rounds_done": 0, "total_sent": 0,
                 "total_failed": 0, "started_at": int(time.time())}
    _stop_event.clear()

    try:
        while not _stop_event.is_set():
            groups = db.get_groups(only_enabled=True)
            if not groups:
                await notify_cb("⚠️ No enabled groups found. Use /groups to manage.")
                break

            round_num = _counters["rounds_done"] + 1
            await notify_cb(f"📢 *Round {round_num}* — forwarding to {len(groups)} groups …")

            sent = failed = 0
            for g in groups:
                if _stop_event.is_set():
                    break
                ok = await userbot.forward_to_group(src_entity, msg_id, g["id"])
                if ok:
                    sent += 1
                    _counters["total_sent"] += 1
                else:
                    failed += 1
                    _counters["total_failed"] += 1

                # Inter-group delay to avoid flood
                await asyncio.sleep(delay)

            _counters["rounds_done"] += 1
            await notify_cb(
                f"✅ Round {round_num} done — "
                f"Sent: {sent} | Failed: {failed}"
            )

            if max_rounds and _counters["rounds_done"] >= max_rounds:
                await notify_cb("🏁 Reached max rounds. Ads stopped.")
                break

            if not _stop_event.is_set():
                await notify_cb(f"⏳ Next round in {delay}s …")
                await asyncio.sleep(delay)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception("Worker crashed: %s", e)
        await notify_cb(f"❌ Worker crashed: {e}")
    finally:
        await notify_cb("🛑 Ad worker stopped.")


async def start_worker(notify_cb, src_entity, msg_id: int, delay: int, max_rounds: int):
    global _task
    if is_running():
        return False
    _stop_event.clear()
    _task = asyncio.create_task(
        _worker(notify_cb, src_entity, msg_id, delay, max_rounds)
    )
    return True


async def stop_worker():
    global _task
    _stop_event.set()
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None

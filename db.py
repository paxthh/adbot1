"""
SQLite persistence layer.
Tables:
  settings  – key/value store (post_link, delay, rounds, etc.)
  groups    – cached list of groups joined by the ads account
  stats     – per-run forwarding statistics
"""
import sqlite3
import time
from config import DB_PATH


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS groups (
            id        INTEGER PRIMARY KEY,
            title     TEXT,
            username  TEXT,
            enabled   INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER,
            group_id    INTEGER,
            group_title TEXT,
            success     INTEGER
        );
        """)


# ── Settings ────────────────────────────────────────────────────────────────

def get(key, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_val(key, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))


# ── Groups ──────────────────────────────────────────────────────────────────

def save_groups(groups: list[dict]):
    """Replace the cached groups list."""
    with _conn() as c:
        c.execute("DELETE FROM groups")
        c.executemany(
            "INSERT OR IGNORE INTO groups(id,title,username,enabled) VALUES(:id,:title,:username,1)",
            groups
        )


def get_groups(only_enabled=True):
    q = "SELECT * FROM groups"
    if only_enabled:
        q += " WHERE enabled=1"
    q += " ORDER BY title"
    with _conn() as c:
        return [dict(r) for r in c.execute(q).fetchall()]


def toggle_group(group_id: int, enabled: bool):
    with _conn() as c:
        c.execute("UPDATE groups SET enabled=? WHERE id=?", (1 if enabled else 0, group_id))


def group_count():
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM groups WHERE enabled=1").fetchone()[0]


# ── Stats ───────────────────────────────────────────────────────────────────

def log_forward(group_id: int, group_title: str, success: bool):
    with _conn() as c:
        c.execute(
            "INSERT INTO stats(ts,group_id,group_title,success) VALUES(?,?,?,?)",
            (int(time.time()), group_id, group_title, 1 if success else 0)
        )


def get_stats():
    with _conn() as c:
        total   = c.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
        success = c.execute("SELECT COUNT(*) FROM stats WHERE success=1").fetchone()[0]
        fail    = total - success
        recent  = c.execute(
            "SELECT group_title, success, ts FROM stats ORDER BY ts DESC LIMIT 10"
        ).fetchall()
    return {"total": total, "success": success, "fail": fail, "recent": [dict(r) for r in recent]}


def clear_stats():
    with _conn() as c:
        c.execute("DELETE FROM stats")


init_db()

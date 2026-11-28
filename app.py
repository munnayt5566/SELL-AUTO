# ============================================================
# FILE: app.py  — FORCE JOIN + EMOJI CAPTCHA + COLORED BUTTONS
# Requirements: flask, gunicorn, telethon, psycopg2-binary, python-telegram-bot>=22.7
# ============================================================

import os
import re
import io
import json
import zipfile
import asyncio
import random
import string
import time
import datetime
import threading
import html
import hmac
import hashlib
import psycopg2
import requests as _requests
from flask import Flask, request, jsonify
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import telegram
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

app = Flask(__name__)

DATABASE_URL    = os.environ.get("DATABASE_URL")
BOT             = "@Taskl1_bot"
COOKIE_SELL_BOT = "@QuickTaskPay1bot"

# ── LICENSE BOT CONFIG ──
LICENSE_BOT_TOKEN  = os.environ.get("LICENSE_BOT_TOKEN")
ADMIN_IDS          = list(map(int, os.environ.get("ADMIN_IDS", "8301781046").split(",")))
DEVELOPER_USERNAME = os.environ.get("DEVELOPER_USERNAME", "@NEXEX_99")
APP_NAME           = os.environ.get("APP_NAME", "SuperToolsX")
TG_BOT_LINK        = os.environ.get("TG_BOT_LINK", "https://t.me/SUPER_WORKER_KEY_99_bot")

# ── PANEL & BOT API KEYS (Render Environment Variables এ দিন অথবা "" এ সরাসরি দিন) ──
ZENEX_API_KEY      = os.environ.get("ZENEX_API_KEY", "")
PANEL2_BASE_URL    = os.environ.get("PANEL2_BASE_URL", "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api")
PANEL2_API_KEY     = os.environ.get("PANEL2_API_KEY", "")
PANEL3_BASE_URL    = os.environ.get("PANEL3_BASE_URL", "https://slvirtualnumber.com")
PANEL3_API_KEY     = os.environ.get("PANEL3_API_KEY", "")
LAMIX_BASE_URL     = os.environ.get("LAMIX_BASE_URL", "https://panel.lamix.org")
LAMIX_API_KEY      = os.environ.get("LAMIX_API_KEY", "")
DEFAULT_BOT_TOKEN  = os.environ.get("DEFAULT_BOT_TOKEN", "")
DEFAULT_CHAT_ID    = os.environ.get("DEFAULT_CHAT_ID", "")

# ── ANTI-TAMPER / APK SIGNATURE CONFIG ──
PROXY_HMAC_SECRET  = os.environ.get("PROXY_HMAC_SECRET", LICENSE_BOT_TOKEN or "stx_secret_key_change_me")
ALLOWED_APK_PKG    = os.environ.get("ALLOWED_APK_PKG", "com.supertoolsx.app")
ALLOWED_APK_SIG    = os.environ.get("ALLOWED_APK_SIG", "").strip().upper()

# ── FORCE JOIN CONFIG ──
FORCE_CHANNEL_USERNAME = "@SUPER_WORKERS"  # চ্যানেলের ইউজারনেম
FORCE_CHANNEL_LINK     = "https://t.me/SUPER_WORKERS"

# ConversationHandler states
CAPTCHA_STATE      = 1
CUSTOM_KEY_DAYS    = 2
USER_KEY_DURATION  = 3
SET_LIMIT_STATE    = 4
SET_ADMIN_STATE    = 5
AUTO_SELL_KEY_DAYS = 6
HWID_APPROVE_STATE = 10
HWID_AUTOSELL_STATE = 11
HWID_BAN_STATE = 12
HWID_SBAN_STATE = 13
HWID_UNBAN_STATE = 14
HWID_REJECT_STATE = 15
HWID_INLINE_SBAN = 16

# Admin settings (in-memory)
_admin_free_key_hours  = {"value": 24}
_admin_daily_key_limit = {"value": 1}

# Pending captcha answers
_captcha_pending = {}

# ══════════════════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════════════════

def header(title: str, emoji: str = "🛡️") -> str:
    line = "▰" * 11
    return (
        f"{line}\n"
        f"  {emoji}  <b>{title}</b>  {emoji}\n"
        f"{line}\n"
    )

def divider() -> str:
    return "┄" * 22 + "\n"

def footer() -> str:
    return f"\n╰─ 👨‍💻 Dev: {DEVELOPER_USERNAME}"

def progress_bar(current: int, total: int, length: int = 10) -> str:
    filled = int(length * current / total) if total else 0
    bar = "█" * filled + "░" * (length - filled)
    pct = int(100 * current / total) if total else 0
    return f"[{bar}] {pct}%"

def esc(text) -> str:
    return html.escape(str(text) if text is not None else "")

def btn(text: str, callback_data: str = None, url: str = None,
        style: str = None) -> InlineKeyboardButton:
    kwargs = {"text": text}
    if url:
        kwargs["url"] = url
    else:
        kwargs["callback_data"] = callback_data or "noop"
    if style:
        kwargs["style"] = style
    try:
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("style", None)
        return InlineKeyboardButton(**kwargs)

def kbtn(text: str, style: str = None) -> KeyboardButton:
    if style:
        try:
            return KeyboardButton(text=text, style=style)
        except TypeError:
            pass
    return KeyboardButton(text=text)

# ── Force Join Check Helper ──
async def is_joined(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """ইউজার চ্যানেলে জয়েন করেছে কিনা চেক করে"""
    try:
        member = await ctx.bot.get_chat_member(FORCE_CHANNEL_USERNAME, user_id)
        if member.status in ['left', 'kicked']:
            return False
        return True
    except Exception as e:
        print(f"Force Join Check Error: {e}", flush=True)
        # যদি বট অ্যাডমিন না থাকে বা চ্যানেল না পায়, তবে ইউজারকে ঢুকতে দেবে
        return True


# ══════════════════════════════════════════════════════════
#  DB SETUP
# ══════════════════════════════════════════════════════════

def get_db():
    return psycopg2.connect(DATABASE_URL)


# ══════════════════════════════════════════════════════════
#  AUTO SELL HELPER
# ══════════════════════════════════════════════════════════

def is_task_off_message(text):
    """Bot থেকে আসা 'task off' বা 'conversation reset' message detect করে।"""
    if not text:
        return False
    low = text.lower()
    patterns = [
        # Bot এর real reset messages
        "conversation was reset",
        "previous conversation was reset",
        "please start again",
        "start again from the main menu",
        "previous conversation",
        # Action cancel / task cancel
        "action cancel",
        "action was cancel",
        "task cancel",
        "task was cancel",

        # Task unavailable
        "session expired",
        "task is off", "tasks are off",
        "task not available", "no task available",
        "temporarily unavailable",
        "try again later",
        "under maintenance",
        # Bot reset variants
        "has been reset",
        "reset, please",
    ]
    return any(p in low for p in patterns)


# ══════════════════════════════════════════════════════════
#  COOKIE VALIDATOR HELPER
# ══════════════════════════════════════════════════════════

def check_fb_cookie_valid(cookie: str) -> dict:
    """
    Facebook cookie valid কিনা চেক করে।
    Returns: {"valid": bool, "uid": str or None, "reason": str}
    """
    if not cookie or "c_user=" not in cookie:
        return {"valid": False, "uid": None, "reason": "c_user= নেই"}

    # UID বের করো cookie থেকে
    uid = None
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("c_user="):
            uid = part.split("=", 1)[1].strip()
            break

    headers = {
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 11; Redmi Note 8) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = _requests.get(
            "https://m.facebook.com/",
            headers=headers,
            timeout=15,
            allow_redirects=True
        )
        text = r.text.lower()
        url  = r.url.lower()

        # Checkpoint / disabled
        if "checkpoint" in url or "checkpoint" in text:
            return {"valid": False, "uid": uid, "reason": "Checkpoint — account locked"}
        if "disabled" in text or "suspended" in text:
            return {"valid": False, "uid": uid, "reason": "Account disabled"}
        # Login page মানে cookie expire
        if "login" in url and "m.facebook.com/login" in url:
            return {"valid": False, "uid": uid, "reason": "Cookie expired — redirected to login"}
        # Logged in indicator
        if "logout" in text or "log out" in text or (uid and uid in text):
            return {"valid": True, "uid": uid, "reason": "Active"}

        return {"valid": False, "uid": uid, "reason": "Unknown state"}

    except Exception as e:
        return {"valid": False, "uid": uid, "reason": f"Network error: {e}"}


# ══════════════════════════════════════════════════════════
#  FLASK ENDPOINT — /check_cookie  (single cookie check)
# ══════════════════════════════════════════════════════════

@app.route("/check_cookie", methods=["POST"])
def api_check_cookie():
    """
    Android AUTO SELL panel থেকে cookie valid কিনা চেক করে।
    Body: {"cookie": "...", "twofa_key": "...(optional)..."}
    Response: {"valid": bool, "uid": str, "reason": str}
    """
    data   = request.get_json(silent=True) or {}
    cookie = str(data.get("cookie", "")).strip()

    if not cookie:
        return jsonify({"valid": False, "uid": None, "reason": "Cookie missing"}), 400

    result = check_fb_cookie_valid(cookie)
    return jsonify(result), 200


# ══════════════════════════════════════════════════════════
#  FLASK ENDPOINT — /batch_check_cookies  (bulk check)
# ══════════════════════════════════════════════════════════

@app.route("/batch_check_cookies", methods=["POST"])
def api_batch_check_cookies():
    """
    AUTO SELL panel এর ২ মিনিট পরপর bulk cookie check।
    Body: {"accounts": [{"id": "...", "cookie": "...", "twofa_key": "..."}, ...]}
    Response: {"results": [{"id": "...", "valid": bool, "uid": str, "reason": str}, ...]}
    """
    data     = request.get_json(silent=True) or {}
    accounts = data.get("accounts", [])

    if not accounts or not isinstance(accounts, list):
        return jsonify({"results": []}), 400

    results = []
    for acc in accounts:
        acc_id  = str(acc.get("id", ""))
        cookie  = str(acc.get("cookie", "")).strip()
        result  = check_fb_cookie_valid(cookie)
        result["id"] = acc_id
        results.append(result)
        time.sleep(0.3)   # rate limit এড়াতে ছোট delay

    return jsonify({"results": results}), 200


def ensure_tables():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_otp (
            phone            TEXT PRIMARY KEY,
            api_id           TEXT NOT NULL,
            api_hash         TEXT NOT NULL,
            phone_code_hash  TEXT NOT NULL,
            temp_session     TEXT
        )
    """)
    cur.execute("ALTER TABLE pending_otp ADD COLUMN IF NOT EXISTS temp_session TEXT")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            user_id         TEXT PRIMARY KEY,
            session_string  TEXT NOT NULL,
            api_id          TEXT NOT NULL,
            api_hash        TEXT NOT NULL,
            target_username TEXT NOT NULL
        )
    """)
    cur.execute("ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS api_id TEXT")
    cur.execute("ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS api_hash TEXT")
    cur.execute("ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS target_username TEXT")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sell_stats (
            user_id    TEXT PRIMARY KEY,
            sell_count INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS license_keys (
            key         TEXT PRIMARY KEY,
            created_at  BIGINT NOT NULL,
            expires_at  BIGINT NOT NULL,
            used_by     TEXT DEFAULT NULL,
            used_at     BIGINT DEFAULT NULL,
            device_id   TEXT DEFAULT NULL,
            tg_username TEXT DEFAULT NULL,
            tg_name     TEXT DEFAULT NULL,
            tg_id       TEXT DEFAULT NULL,
            is_active   BOOLEAN DEFAULT TRUE
        )
    """)
    cur.execute("ALTER TABLE license_keys ADD COLUMN IF NOT EXISTS device_id   TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE license_keys ADD COLUMN IF NOT EXISTS tg_username TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE license_keys ADD COLUMN IF NOT EXISTS tg_name     TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE license_keys ADD COLUMN IF NOT EXISTS tg_id       TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE license_keys ADD COLUMN IF NOT EXISTS key_type    TEXT DEFAULT 'regular'")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_key_usage (
            user_id      TEXT PRIMARY KEY,
            key_count    INTEGER DEFAULT 0,
            last_reset   BIGINT DEFAULT 0
        )
    """)
    # ── SCHEDULED SELL QUEUE ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sell_queue (
            id           SERIAL PRIMARY KEY,
            tg_user_id   TEXT NOT NULL,
            twofa_key    TEXT NOT NULL,
            cookie       TEXT NOT NULL,
            status       TEXT DEFAULT 'pending',
            added_at     BIGINT NOT NULL,
            sold_at      BIGINT DEFAULT NULL,
            retry_count  INTEGER DEFAULT 0
        )
    """)
    # ── SELL SCHEDULE CONFIG ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sell_schedule (
            tg_user_id        TEXT PRIMARY KEY,
            start_time_epoch  BIGINT NOT NULL,
            task_off_wait_sec INTEGER DEFAULT 300,
            gap_seconds       INTEGER DEFAULT 30,
            enabled           BOOLEAN DEFAULT TRUE,
            created_at        BIGINT NOT NULL
        )
    """)
    # ── SELL LOG (App এ দেখানোর জন্য) ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sell_log (
            id           SERIAL PRIMARY KEY,
            tg_user_id   TEXT NOT NULL,
            message      TEXT NOT NULL,
            log_time     BIGINT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sell_log_user ON sell_log(tg_user_id, log_time DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sell_queue_user ON sell_queue(tg_user_id, status)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_hwid (
            id           SERIAL UNIQUE,
            hwid         TEXT PRIMARY KEY,
            brand        TEXT DEFAULT '',
            model        TEXT DEFAULT '',
            device_name  TEXT DEFAULT '',
            android_ver  TEXT DEFAULT '',
            sdk_int      TEXT DEFAULT '',
            app_version  TEXT DEFAULT '',
            status       TEXT DEFAULT 'pending',
            key_type     TEXT DEFAULT 'regular',
            expires_at   BIGINT DEFAULT 0,
            ban_reason   TEXT DEFAULT '',
            ban_start_at BIGINT DEFAULT 0,
            ban_until    BIGINT DEFAULT 0,
            created_at   BIGINT NOT NULL,
            last_seen    BIGINT NOT NULL
        )
    """)
    for _col in (
        "user_device TEXT DEFAULT ''",
        "root_status TEXT DEFAULT ''",
        "ram TEXT DEFAULT ''",
        "storage TEXT DEFAULT ''",
        "cpu TEXT DEFAULT ''",
        "screen TEXT DEFAULT ''",
        "network TEXT DEFAULT ''",
        "sec_patch TEXT DEFAULT ''",
        "timezone TEXT DEFAULT ''",
        "last_sig TEXT DEFAULT ''",
    ):
        cur.execute(f"ALTER TABLE device_hwid ADD COLUMN IF NOT EXISTS {_col}")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key   TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

try:
    ensure_tables()
    print("[DB] Tables ready.", flush=True)
except Exception as e:
    import traceback
    print(f"[DB] ensure_tables failed: {e}", flush=True)
    traceback.print_exc()


# ══════════════════════════════════════════════════════════
#  LICENSE KEY HELPERS
# ══════════════════════════════════════════════════════════

def generate_key(prefix="STOOLS"):
    part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    return f"{prefix}-{part[:4]}-{part[4:8]}-{part[8:12]}-{part[12:]}"


def create_license_key(days: float,
                       tg_username: str = None,
                       tg_name: str = None,
                       tg_id: str = None,
                       key_type: str = "regular") -> str:
    key        = generate_key()
    now        = int(time.time())
    expires_at = int(now + days * 86400)
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO license_keys
           (key, created_at, expires_at, tg_username, tg_name, tg_id, key_type)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (key, now, expires_at, tg_username, tg_name, tg_id, key_type)
    )
    conn.commit(); cur.close(); conn.close()
    return key


def validate_key(key: str, device_id: str = None):
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        """SELECT key, created_at, expires_at, used_by, device_id,
                  tg_username, tg_name, tg_id, is_active,
                  COALESCE(key_type, 'regular') as key_type
           FROM license_keys WHERE key = %s""",
        (key,)
    )
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return False, "❌ Invalid key!", None
    k, created_at, expires_at, used_by, locked_device, \
        tg_username, tg_name, tg_id, is_active, key_type = row
    if not is_active:
        return False, "🚫 Key deactivated!", None
    now = int(time.time())
    if now > expires_at:
        return False, "⏰ Key expired!", None
    if device_id and locked_device and locked_device != device_id:
        return False, "🔒 This key is locked to another device!", None
    remaining  = expires_at - now
    days_left  = remaining // 86400
    hours_left = (remaining % 86400) // 3600
    mins_left  = (remaining % 3600) // 60
    exp_str    = datetime.datetime.fromtimestamp(expires_at).strftime("%d/%m/%Y %H:%M")
    info = {
        "key"        : k,
        "expires_at" : expires_at,
        "exp_str"    : exp_str,
        "days_left"  : days_left,
        "hours_left" : hours_left,
        "mins_left"  : mins_left,
        "tg_username": tg_username or "",
        "tg_name"    : tg_name     or "",
        "tg_id"      : tg_id       or "",
        "key_type"   : key_type or "regular",
        "auto_sell"  : (key_type == "auto_sell"),
    }
    return True, "✅ Valid", info


def mark_key_used(key: str, device_id: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "UPDATE license_keys SET used_by=%s, used_at=%s, device_id=%s WHERE key=%s",
        (device_id, int(time.time()), device_id, key)
    )
    conn.commit(); cur.close(); conn.close()


def check_key_usage_limit(user_id: int) -> tuple:
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT key_count, last_reset FROM user_key_usage WHERE user_id = %s",
        (str(user_id),)
    )
    row = cur.fetchone()
    now   = int(time.time())
    limit = _admin_daily_key_limit["value"]

    if row is None:
        cur.close(); conn.close()
        return True, "ok"

    key_count, last_reset = row
    if now - last_reset >= 86400:
        cur.close(); conn.close()
        return True, "ok"

    if limit > 0 and key_count >= limit:
        reset_in = 86400 - (now - last_reset)
        hours_r  = reset_in // 3600
        mins_r   = (reset_in % 3600) // 60
        bar      = progress_bar(key_count, limit)
        cur.close(); conn.close()
        return False, (
            f"📊 আজকের ব্যবহার: {bar}\n\n"
            f"⛔ <b>{key_count}/{limit}</b> টি Key নেওয়া হয়েছে\n"
            f"🔄 <b>{hours_r}h {mins_r}m</b> পরে Reset হবে"
        )

    cur.close(); conn.close()
    return True, "ok"


def increment_key_usage(user_id: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT key_count, last_reset FROM user_key_usage WHERE user_id = %s",
        (str(user_id),)
    )
    row = cur.fetchone()
    now = int(time.time())

    if row is None:
        cur.execute(
            "INSERT INTO user_key_usage (user_id, key_count, last_reset) VALUES (%s, 1, %s)",
            (str(user_id), now)
        )
    else:
        key_count, last_reset = row
        if now - last_reset >= 86400:
            cur.execute(
                "UPDATE user_key_usage SET key_count=1, last_reset=%s WHERE user_id=%s",
                (now, str(user_id))
            )
        else:
            cur.execute(
                "UPDATE user_key_usage SET key_count=key_count+1 WHERE user_id=%s",
                (str(user_id),)
            )
    conn.commit(); cur.close(); conn.close()


def _fmt_duration(days: float) -> str:
    total_secs = int(days * 86400)
    if total_secs >= 86400:
        return f"{int(total_secs // 86400)} দিন"
    return f"{int(total_secs // 3600)} ঘন্টা"


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ══════════════════════════════════════════════════════════
#  FLASK ENDPOINT — /validate_key
# ══════════════════════════════════════════════════════════

@app.route("/validate_key", methods=["POST"])
def api_validate_key():
    data   = request.json or {}
    key    = (data.get("key") or "").strip().upper()
    dev_id = data.get("device_id", "unknown")
    if not key:
        return jsonify({"valid": False, "message": "Key missing"}), 400
    valid, msg, info = validate_key(key, dev_id)
    if valid:
        mark_key_used(key, dev_id)
        return jsonify({
            "valid"      : True,
            "message"    : msg,
            "expires_at" : info["expires_at"],
            "exp_str"    : info["exp_str"],
            "days_left"  : info["days_left"],
            "hours_left" : info["hours_left"],
            "mins_left"  : info["mins_left"],
            "tg_username": info["tg_username"],
            "tg_name"    : info["tg_name"],
            "tg_id"      : info["tg_id"],
            "key_type"   : info["key_type"],
            "auto_sell"  : info["auto_sell"],
        })
    return jsonify({"valid": False, "message": msg}), 200

BD_TZ = datetime.timezone(datetime.timedelta(hours=6))

def _xml_safe(val) -> str:
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(val if val is not None else ""))
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&apos;")

def _col_letter(i: int) -> str:
    r = ""
    while i >= 0:
        r = chr(65 + (i % 26)) + r
        i = i // 26 - 1
    return r

def build_xlsx_bytes(rows: list, sheet_name: str = "Devices") -> bytes:
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for ri, row in enumerate(rows, 1):
        parts.append(f'<row r="{ri}">')
        for ci, val in enumerate(row):
            parts.append(f'<c r="{_col_letter(ci)}{ri}" t="inlineStr"><is><t>{_xml_safe(val)}</t></is></c>')
        parts.append('</row>')
    parts.append('</sheetData></worksheet>')
    ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rr = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wr = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    wb = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{_xml_safe(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("_rels/.rels", rr)
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", wr)
        zf.writestr("xl/worksheets/sheet1.xml", "".join(parts))
    return buf.getvalue()

def get_app_setting(key: str, default: str = "0") -> str:
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT setting_value FROM app_settings WHERE setting_key=%s", (key,))
        r = cur.fetchone(); cur.close(); conn.close()
        return r[0] if r else default
    except Exception:
        return default

def set_app_setting(key: str, val: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO app_settings (setting_key, setting_value) VALUES (%s,%s) ON CONFLICT (setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value", (key, val))
    conn.commit(); cur.close(); conn.close()

def _parse_dur(tok: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([smhd])", tok.strip().lower())
    return int(m.group(1)) * {"s":1,"m":60,"h":3600,"d":86400}[m.group(2)] if m else 0

def parse_ban_schedule(expr: str):
    raw = (expr or "").strip().lower(); now = int(time.time())
    if raw in ("perm", "permanent", "0"): return now, 0, None
    s = _parse_dur(raw)
    if s > 0: return now, now + s, None
    m = re.fullmatch(r"after\s+(\d+[smhd])(?:\s+for\s+(\d+[smhd]))?", raw)
    if m:
        sa = now + _parse_dur(m.group(1))
        ds = _parse_dur(m.group(2)) if m.group(2) else 0
        return sa, (sa + ds if ds > 0 else 0), None
    m2 = re.fullmatch(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})(?:\s+for\s+(\d+[smhd]))?", raw)
    if m2:
        try:
            sa = int(datetime.datetime.strptime(m2.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=BD_TZ).timestamp())
            ds = _parse_dur(m2.group(2)) if m2.group(2) else 0
            return sa, (sa + ds if ds > 0 else 0), None
        except Exception: pass
    return 0, 0, "❌ সঠিক ফরম্যাট দিন!\n• <code>2h</code> বা <code>7d</code>\n• <code>after 1h</code>\n• <code>after 1h for 24h</code>\n• <code>2026-11-26 22:00 for 6h</code>"

def sync_all_hwid_schedules():
    now = int(time.time())
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE device_hwid SET status='approved', ban_start_at=0, ban_until=0, ban_reason='' WHERE status='banned' AND ban_until>0 AND ban_until<=%s", (now,))
        cur.execute("UPDATE device_hwid SET status='banned', ban_start_at=0 WHERE status!='banned' AND ban_start_at>0 AND ban_start_at<=%s AND (ban_until=0 OR ban_until>%s)", (now, now))
        cur.execute("UPDATE device_hwid SET ban_start_at=0, ban_until=0, ban_reason='' WHERE status!='banned' AND ban_start_at>0 AND ban_until>0 AND ban_until<=%s", (now,))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f"[HWID-SCHED] {e}", flush=True)

def resolve_hwid(q: str):
    q = (q or "").strip().upper()
    conn = get_db(); cur = conn.cursor()
    if q.isdigit():
        cur.execute("SELECT hwid FROM device_hwid WHERE id=%s", (int(q),))
        r = cur.fetchone()
        if r: cur.close(); conn.close(); return r[0]
    cur.execute("SELECT hwid FROM device_hwid WHERE hwid=%s", (q,))
    r = cur.fetchone()
    if not r:
        cur.execute("SELECT hwid FROM device_hwid WHERE hwid LIKE %s ORDER BY last_seen DESC LIMIT 1", (f"%{q}",))
        r = cur.fetchone()
    cur.close(); conn.close()
    return r[0] if r else None

def build_inline_device_kb(dev_id: int, status: str) -> dict:
    if status == "approved":
        rows = [
            [
                {"text": "🚫 BAN", "callback_data": f"hw:ban:{dev_id}", "style": "danger"},
                {"text": "⏳ SCHEDULE BAN", "callback_data": f"hw:sban:{dev_id}", "style": "primary"},
            ],
            [
                {"text": "🔏 LOCK THIS SIG", "callback_data": f"hw:locksig:{dev_id}", "style": "success"},
                {"text": "❌ REJECT", "callback_data": f"hw:rej:{dev_id}", "style": "danger"},
            ],
        ]
    elif status == "banned":
        rows = [
            [
                {"text": "🔓 UNBAN & APPROVE", "callback_data": f"hw:unban:{dev_id}", "style": "success"},
            ],
            [
                {"text": "⏳ SCHEDULE BAN", "callback_data": f"hw:sban:{dev_id}", "style": "primary"},
            ],
        ]
    else:
        rows = [
            [
                {"text": "✅ APPROVE", "callback_data": f"hw:ok:{dev_id}", "style": "success"},
                {"text": "🤖 AUTO SELL", "callback_data": f"hw:as:{dev_id}", "style": "primary"},
            ],
            [
                {"text": "❌ REJECT", "callback_data": f"hw:rej:{dev_id}", "style": "danger"},
                {"text": "🚫 BAN", "callback_data": f"hw:ban:{dev_id}", "style": "danger"},
            ],
            [
                {"text": "⏳ SCHEDULE BAN", "callback_data": f"hw:sban:{dev_id}", "style": "primary"},
            ],
        ]
    return {"inline_keyboard": rows}

def build_ptb_device_kb(dev_id: int, status: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn(b["text"], callback_data=b["callback_data"], style=b.get("style")) for b in r]
        for r in build_inline_device_kb(dev_id, status)["inline_keyboard"]
    ])

def fetch_device_row(did: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT id, hwid, COALESCE(user_device,''), brand, model, device_name,
               android_ver, sdk_int, COALESCE(root_status,''), COALESCE(ram,''),
               COALESCE(storage,''), COALESCE(cpu,''), COALESCE(screen,''),
               COALESCE(network,''), app_version, status, key_type, expires_at,
               ban_reason, ban_start_at, ban_until, created_at
        FROM device_hwid WHERE id=%s
    """, (did,))
    row = cur.fetchone(); cur.close(); conn.close()
    return row

def format_device_caption(row) -> str:
    (did, hw, udev, br, md, dn, av, sdk, rt, ram, stg, cpu, scr, net, apv,
     st, kt, exp, rsn, bs, bu, cat) = row
    st = st or "pending"; kt = kt or "regular"; cat = cat or int(time.time())
    dt = datetime.datetime.fromtimestamp(cat, BD_TZ).strftime("%d/%m/%Y %H:%M")
    badge = {
        "pending": "🟡 PENDING",
        "approved": f"🟢 APPROVED ({kt.upper()})",
        "rejected": "🔴 REJECTED",
        "banned": "🚫 BANNED",
    }.get(st, st.upper())
    mobile_name = udev.strip() if udev and udev.strip() else f"{br} {md}".strip()
    extra = ""
    if st == "banned":
        ut = datetime.datetime.fromtimestamp(bu, BD_TZ).strftime("%d/%m %H:%M") if bu and bu > 0 else "Permanent"
        extra = f"\n│ 📝 Reason : {esc(rsn)}\n│ 🔓 Until  : <b>{ut}</b>"
    elif bs and bs > int(time.time()):
        extra = f"\n│ ⏳ Sched  : <b>{datetime.datetime.fromtimestamp(bs, BD_TZ).strftime('%d/%m %H:%M')}</b>"
    return (
        f"{header(f'DEVICE #{did}', '📲')}"
        f"┌─────────────────────\n"
        f"│ 📌 Status : <b>{badge}</b>\n"
        f"│ 📱 Mobile : <b>{esc(mobile_name)}</b>\n"
        f"│ 🏷 Model  : {esc(br)} {esc(md)} ({esc(dn)})\n"
        f"│ 🤖 OS     : Android <b>{esc(av)}</b> (SDK {esc(sdk)}) • {esc(rt or 'N/A')}\n"
        f"│ 💾 Spec   : {esc(ram or 'N/A')} | {esc(stg or 'N/A')}\n"
        f"│ 🌐 Net    : {esc(net or 'N/A')} | App: {esc(apv or APP_NAME)}\n"
        f"│ 🕒 Time   : {dt} (BD)"
        f"{extra}\n"
        f"└─────────────────────\n"
        f"🆔 <b>HWID:</b>\n<code>{hw}</code>"
        f"{footer()}"
    )

def send_request_xlsx_to_admins(dev_id: int):
    if not LICENSE_BOT_TOKEN: return
    try:
        row = fetch_device_row(dev_id)
        if not row: return
        (did, hw, udev, br, md, dn, av, sdk, rt, ram, stg, cpu, scr, net, apv,
         st, kt, exp, rsn, bs, bu, cat) = row
        dt = datetime.datetime.fromtimestamp(cat or int(time.time()), BD_TZ).strftime("%d/%m/%Y %H:%M:%S")
        mobile_name = udev.strip() if udev and udev.strip() else f"{br} {md}".strip()
        xb = build_xlsx_bytes([
            ["ID","Status","Type","Mobile Name","Brand","Model","Device","Android","SDK","Root","RAM","Storage","CPU","Screen","Network","App","HWID (SHA-256)","Time (BD)"],
            [did,(st or "pending").upper(),kt or "regular",mobile_name,br,md,dn,av,sdk,rt,ram,stg,cpu,scr,net,apv or APP_NAME,hw,dt]
        ], "RequestInfo")
        fn = f"REQ_{did}_{re.sub(r'[^A-Za-z0-9_-]+','_',f'{br}_{md}').strip('_') or 'Device'}.xlsx"
        rm = json.dumps(build_inline_device_kb(did, st or "pending"))
        cap = format_device_caption(row)
        url = f"https://api.telegram.org/bot{LICENSE_BOT_TOKEN}/sendDocument"
        for aid in ADMIN_IDS:
            try:
                _requests.post(
                    url,
                    data={"chat_id": str(aid), "caption": cap, "parse_mode": "HTML", "reply_markup": rm},
                    files={"document": (fn, xb, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    timeout=20,
                )
            except Exception as ex:
                print(f"[REQ_ADMIN] {ex}", flush=True)
    except Exception as e:
        print(f"[REQ_ADMIN] {e}", flush=True)

def _get_allowed_sig() -> str:
    if ALLOWED_APK_SIG:
        return ALLOWED_APK_SIG
    return get_app_setting("allowed_apk_sig", "").strip().upper()

def make_proxy_token(hwid: str, exp: int) -> str:
    msg = f"{hwid}:{exp}".encode("utf-8")
    return hmac.new(PROXY_HMAC_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def verify_proxy_auth(d: dict):
    hw  = str(d.get("hwid", "")).strip().upper()
    tok = str(d.get("token", "")).strip().lower()
    pkg = str(d.get("pkg", "")).strip()
    sig = str(d.get("sig", "")).strip().upper()

    if not hw or not tok:
        return False, "Missing HWID or session token"
    if ALLOWED_APK_PKG and pkg and pkg != ALLOWED_APK_PKG:
        return False, f"Invalid package: {pkg}"
    allowed_sig = _get_allowed_sig()
    if allowed_sig and sig != allowed_sig:
        return False, "Modified / Patched APK detected!"

    sync_all_hwid_schedules()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT status, expires_at FROM device_hwid WHERE hwid=%s", (hw,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return False, "Device not registered"
    st, exp = row
    now = int(time.time())
    if st != "approved":
        return False, f"Device status: {st}"
    if exp and exp > 0 and now > exp:
        return False, "Device access expired"

    expected = make_proxy_token(hw, exp or 0)
    if not hmac.compare_digest(tok, expected):
        return False, "Invalid proxy token"
    return True, hw

@app.route("/check_hwid", methods=["POST"])
def api_check_hwid():
    d = request.get_json(silent=True) or {}
    hw = str(d.get("hwid","")).strip().upper()
    if not hw: return jsonify({"allowed":False,"status":"error","message":"HWID missing"}), 400
    pkg = str(d.get("pkg","")).strip()
    sig = str(d.get("sig","")).strip().upper()
    if ALLOWED_APK_PKG and pkg and pkg != ALLOWED_APK_PKG:
        return jsonify({"allowed":False,"status":"banned","ban_reason":"Cloned APK detected!","message":"🚫 Cloned APK অনুমোদিত নয়।"}), 403
    allowed_sig = _get_allowed_sig()
    if allowed_sig and sig and sig != allowed_sig:
        return jsonify({"allowed":False,"status":"banned","ban_reason":"Modified / Patched APK detected!","message":"🚫 এই APK টি প্যাচ/এডিট করা হয়েছে! আসল APK ব্যবহার করুন।"}), 403

    ud  = str(d.get("user_device","")).strip()[:60]
    br  = str(d.get("brand","")).strip()[:40];       md  = str(d.get("model","")).strip()[:60]
    dn  = str(d.get("device_name","")).strip()[:40]; av  = str(d.get("android_ver","")).strip()[:20]
    sdk = str(d.get("sdk_int","")).strip()[:10];     apv = str(d.get("app_version","")).strip()[:30]
    rt  = str(d.get("root_status","")).strip()[:20]; ram = str(d.get("ram","")).strip()[:20]
    stg = str(d.get("storage","")).strip()[:40];     cpu = str(d.get("cpu","")).strip()[:60]
    scr = str(d.get("screen","")).strip()[:30];      net = str(d.get("network","")).strip()[:20]
    sp  = str(d.get("sec_patch","")).strip()[:20];   tz  = str(d.get("timezone","")).strip()[:40]
    now = int(time.time()); sync_all_hwid_schedules()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, status, key_type, expires_at, ban_reason, ban_start_at, ban_until FROM device_hwid WHERE hwid=%s", (hw,))
    row = cur.fetchone()
    if not row:
        ist = "approved" if get_app_setting("auto_approve","0")=="1" else "pending"
        cur.execute("""
            INSERT INTO device_hwid
            (hwid,user_device,brand,model,device_name,android_ver,sdk_int,root_status,ram,storage,cpu,screen,network,sec_patch,timezone,last_sig,app_version,status,key_type,expires_at,created_at,last_seen)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'regular',0,%s,%s) RETURNING id
        """, (hw,ud,br,md,dn,av,sdk,rt,ram,stg,cpu,scr,net,sp,tz,sig,apv,ist,now,now))
        did = cur.fetchone()[0]; conn.commit(); row = (did, ist, "regular", 0, "", 0, 0)
    else:
        cur.execute("""
            UPDATE device_hwid SET last_seen=%s,
                user_device=CASE WHEN %s<>'' THEN %s ELSE user_device END,
                brand=CASE WHEN brand='' THEN %s ELSE brand END,
                model=CASE WHEN model='' THEN %s ELSE model END,
                root_status=CASE WHEN %s<>'' THEN %s ELSE root_status END,
                ram=CASE WHEN %s<>'' THEN %s ELSE ram END,
                storage=CASE WHEN %s<>'' THEN %s ELSE storage END,
                network=CASE WHEN %s<>'' THEN %s ELSE network END,
                last_sig=CASE WHEN %s<>'' THEN %s ELSE last_sig END
            WHERE hwid=%s
        """, (now, ud, ud, br, md, rt, rt, ram, ram, stg, stg, net, net, sig, sig, hw))
        conn.commit()
    cur.close(); conn.close()
    did, st, kt, exp, rsn, bs, bu = row
    if st == "banned":
        return jsonify({"allowed":False,"id":did,"status":"banned","key_type":kt,"expires_at":exp,"ban_reason":rsn or "Banned by Admin","ban_until":bu,"ban_remaining":max(0,bu-now) if bu and bu>0 else 0,"message":"🚫 এই ডিভাইসটি ব্যান করা হয়েছে।"})
    if st == "rejected":
        return jsonify({"allowed":False,"id":did,"status":"rejected","key_type":kt,"expires_at":exp,"ban_reason":rsn or "Rejected by Admin","message":"❌ রিকোয়েস্ট রিজেক্ট হয়েছে।"})
    if st == "pending":
        return jsonify({"allowed":False,"id":did,"status":"pending","key_type":kt,"expires_at":exp,"message":"🔐 REQUEST ADMIN বাটনে চাপুন, অ্যাপ্রুভ হলে CHECK STATUS দিন।"})
    if exp > 0 and now > exp:
        return jsonify({"allowed":False,"id":did,"status":"expired","key_type":kt,"expires_at":exp,"message":"⏰ মেয়াদ শেষ হয়েছে।"})
    if allowed_sig and not sig:
        return jsonify({"allowed":False,"status":"banned","ban_reason":"Missing APK signature!","message":"🚫 APK সিগনেচার পাওয়া যায়নি।"})
    ptok = make_proxy_token(hw, exp or 0)
    return jsonify({"allowed":True,"id":did,"status":"approved","key_type":kt or "regular","expires_at":exp,"proxy_token":ptok,"message":"✅ Approved"})

@app.route("/request_admin", methods=["POST"])
def api_request_admin():
    d = request.get_json(silent=True) or {}
    hw = str(d.get("hwid","")).strip().upper()
    if not hw: return jsonify({"ok":False,"message":"HWID missing"}), 400
    sig = str(d.get("sig","")).strip().upper()
    ud  = str(d.get("user_device","")).strip()[:60]
    br  = str(d.get("brand","")).strip()[:40];       md  = str(d.get("model","")).strip()[:60]
    dn  = str(d.get("device_name","")).strip()[:40]; av  = str(d.get("android_ver","")).strip()[:20]
    sdk = str(d.get("sdk_int","")).strip()[:10];     apv = str(d.get("app_version","")).strip()[:30]
    rt  = str(d.get("root_status","")).strip()[:20]; ram = str(d.get("ram","")).strip()[:20]
    stg = str(d.get("storage","")).strip()[:40];     cpu = str(d.get("cpu","")).strip()[:60]
    scr = str(d.get("screen","")).strip()[:30];      net = str(d.get("network","")).strip()[:20]
    sp  = str(d.get("sec_patch","")).strip()[:20];   tz  = str(d.get("timezone","")).strip()[:40]
    now = int(time.time()); sync_all_hwid_schedules()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, status, ban_reason FROM device_hwid WHERE hwid=%s", (hw,))
    row = cur.fetchone()
    if row and row[1] == "banned":
        cur.close(); conn.close()
        return jsonify({"ok":False,"status":"banned","message":f"🚫 ডিভাইস ব্যান করা আছে ({row[2] or 'Banned'})"})
    if row and row[1] == "approved":
        cur.close(); conn.close()
        return jsonify({"ok":True,"status":"approved","message":"✅ ইতিমধ্যেই Approved!"})
    if not row:
        cur.execute("""
            INSERT INTO device_hwid
            (hwid,user_device,brand,model,device_name,android_ver,sdk_int,root_status,ram,storage,cpu,screen,network,sec_patch,timezone,last_sig,app_version,status,key_type,expires_at,created_at,last_seen)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending','regular',0,%s,%s) RETURNING id
        """, (hw,ud,br,md,dn,av,sdk,rt,ram,stg,cpu,scr,net,sp,tz,sig,apv,now,now))
        did = cur.fetchone()[0]
    else:
        did = row[0]
        cur.execute("""
            UPDATE device_hwid SET user_device=%s,brand=%s,model=%s,device_name=%s,
                android_ver=%s,sdk_int=%s,root_status=%s,ram=%s,storage=%s,cpu=%s,
                screen=%s,network=%s,sec_patch=%s,timezone=%s,last_sig=%s,app_version=%s,
                status='pending',ban_reason='',last_seen=%s WHERE id=%s
        """, (ud,br,md,dn,av,sdk,rt,ram,stg,cpu,scr,net,sp,tz,sig,apv,now,did))
    conn.commit(); cur.close(); conn.close()
    threading.Thread(target=send_request_xlsx_to_admins, args=(did,), daemon=True).start()
    return jsonify({"ok":True,"id":did,"status":"pending","message":"✅ অ্যাডমিনের কাছে রিকোয়েস্ট পাঠানো হয়েছে! অ্যাপ্রুভ হলে CHECK STATUS চাপুন।"})


#  TELEGRAM BOT HANDLERS
# ══════════════════════════════════════════════════════════

async def cb_check_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user

    joined = await is_joined(update, ctx, user.id)
    if not joined:
        await query.answer("❌ আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)
        return

    await query.answer("✅ ধন্যবাদ! আপনি সফলভাবে জয়েন করেছেন।", show_alert=True)
    name  = esc(user.first_name or "বন্ধু")
    if is_admin(user.id):
        try:
            await query.delete_message()
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id=user.id,
            text=f"{header(APP_NAME + ' ADMIN', '👑')}👋 স্বাগতম Admin <b>{name}!</b>\n👇 নিচের রঙিন Reply Keyboard থেকে কন্ট্রোল করুন:{footer()}",
            parse_mode="HTML",
            reply_markup=get_admin_reply_kb(),
        )
        return

    await query.edit_message_text(
        f"{header(APP_NAME + ' Access', '🛡️')}"
        f"👋 স্বাগতম, <b>{name}!</b>\n\n"
        f"┌─────────────────────\n"
        f"│ 📱  App     :  <b>{esc(APP_NAME)}</b>\n"
        f"│ 🔐  System  :  <b>Device Approval</b>\n"
        f"│ 📩  Step    :  অ্যাপে ঢুকে <b>REQUEST ADMIN</b> চাপুন\n"
        f"└─────────────────────\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑  GET NEW KEY", callback_data="get_new_key", style="success")],
            [
                btn("ℹ️ Info",    callback_data="info",    style="primary"),
                btn("📞 Support", callback_data="support", style="primary"),
            ],
        ]),
    )


async def cb_get_new_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = query.from_user

    # ✅ ক্যাপচা দেওয়ার আগেও আবার চেক (যদি কেউ মাঝখানে লিভ করে)
    joined = await is_joined(update, ctx, user.id)
    if not joined:
        await query.answer("❌ আগে চ্যানেলে জয়েন করুন!", show_alert=True)
        await cb_check_join(update, ctx)
        return ConversationHandler.END

    allowed, err_msg = check_key_usage_limit(user.id)
    if not allowed:
        await query.edit_message_text(
            f"{header('LIMIT REACHED', '🚫')}{err_msg}\n{footer()}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[btn("🔙 Back", callback_data="back_start", style="primary")]]
            )
        )
        return ConversationHandler.END

    emojis = ["🍎", "🍌", "🚗", "🐶", "🐱", "🍕", "⚽", "🎈", "🌟", "🔥"]
    e1, e2 = random.sample(emojis, 2)
    a = random.randint(10, 99)
    b = random.randint(10, 99)
    
    question_text = f"{e1} {a}  +  {e2} {b}"
    correct_ans = a + b
    
    _captcha_pending[user.id] = (correct_ans, time.time() + 120)

    await query.edit_message_text(
        f"{header('CAPTCHA চ্যালেঞ্জ', '🤖')}"
        f"🧮  <b>{question_text}  =  ?</b>\n\n"
        f"✏️ সঠিক উত্তর <b>শুধু সংখ্যায়</b> টাইপ করে পাঠান\n"
        f"⏱️ সময় বাকি: <b>২ মিনিট</b>\n"
        f"{divider()}"
        f"<i>/cancel দিয়ে বাতিল করুন</i>",
        parse_mode="HTML"
    )
    return CAPTCHA_STATE


async def handle_captcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    uid     = user.id
    text    = update.message.text.strip()
    pending = _captcha_pending.get(uid)

    if not pending:
        await update.message.reply_text("⚠️ আগে /start দিয়ে শুরু করুন।")
        return ConversationHandler.END

    correct_ans, expiry = pending
    if time.time() > expiry:
        del _captcha_pending[uid]
        await update.message.reply_text(
            f"{header('TIME OUT!', '⏰')}"
            f"CAPTCHA-র সময় শেষ।\n/start দিয়ে আবার চেষ্টা করুন।",
            parse_mode="HTML"
        )
        return ConversationHandler.END

    if not text.isdigit() or int(text) != correct_ans:
        await update.message.reply_text(
            f"❌ <b>ভুল উত্তর!</b>\n\nআবার চেষ্টা করুন 👇\n"
            f"<i>শুধু সঠিক সংখ্যাটি টাইপ করুন</i>",
            parse_mode="HTML"
        )
        return CAPTCHA_STATE

    del _captcha_pending[uid]
    increment_key_usage(uid)

    tg_username = user.username or ""
    tg_name     = (user.first_name or "") + (" " + (user.last_name or "") if user.last_name else "")
    tg_id       = str(user.id)

    hours   = _admin_free_key_hours["value"]
    days    = hours / 24.0
    key     = create_license_key(days,
                                  tg_username=tg_username,
                                  tg_name=tg_name.strip(),
                                  tg_id=tg_id)
    exp     = datetime.datetime.now() + datetime.timedelta(hours=hours)
    exp_str = exp.strftime("%d/%m/%Y %H:%M")

    if tg_username:
        user_line = f"│ 👤  @{esc(tg_username)}\n"
    else:
        user_line = f"│ 👤  {esc(tg_name.strip() or tg_id)}\n"

    await update.message.reply_text(
        f"{header('KEY GENERATED ✅', '🎉')}"
        f"┌─────────────────────\n"
        f"{user_line}"
        f"│ ⏱️  মেয়াদ  :  <b>{_fmt_duration(days)}</b>\n"
        f"│ 📅  Expire :  <b>{exp_str}</b>\n"
        f"│ 🔒  Lock   :  একটি Device\n"
        f"└─────────────────────\n\n"
        f"🔑 <b>Your License Key:</b>\n"
        f"<code>{key}</code>\n\n"
        f"📋 <i>Key copy করে App-এ দিন</i>\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Back", callback_data="back_start", style="primary")]]
        )
    )
    return ConversationHandler.END


async def cb_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    hours = _admin_free_key_hours["value"]
    limit = _admin_daily_key_limit["value"]
    limit_line = "∞ Unlimited" if limit == 0 else f"{limit}টি / দিন"
    await query.edit_message_text(
        f"{header('APP INFO', 'ℹ️')}"
        f"┌─────────────────────\n"
        f"│ 📱  App    :  <b>{esc(APP_NAME)}</b>\n"
        f"│ 🔑  Limit  :  <b>{limit_line}</b>\n"
        f"│ ⏱️  মেয়াদ  :  <b>{hours} ঘন্টা</b>\n"
        f"│ 🔒  Device :  একটি ফোন\n"
        f"└─────────────────────\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Back", callback_data="back_start", style="primary")]]
        )
    )


async def cb_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"{header('SUPPORT', '📞')}"
        f"সমস্যায় পড়লে নিচে যোগাযোগ করুন:\n\n"
        f"👤 <b>Developer:</b> {esc(DEVELOPER_USERNAME)}\n"
        f"🔗 {esc(TG_BOT_LINK)}\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [btn("📩 Contact Dev", url=TG_BOT_LINK, style="primary")],
            [btn("🔙 Back", callback_data="back_start", style="primary")],
        ])
    )


async def cb_back_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = query.from_user
    limit = _admin_daily_key_limit["value"]
    hours = _admin_free_key_hours["value"]
    admin = is_admin(user.id)
    limit_line = "∞ Unlimited" if limit == 0 else f"{limit}টি / দিন"

    inline_kb = [
        [btn("🔑  GET NEW KEY", callback_data="get_new_key", style="success")],
    ]
    if admin:
        inline_kb.append([btn("⚙️  ADMIN PANEL", callback_data="admin_panel", style="danger")])
    inline_kb.append([
        btn("ℹ️ Info",    callback_data="info",    style="primary"),
        btn("📞 Support", callback_data="support", style="primary"),
    ])

    await query.edit_message_text(
        f"{header(APP_NAME + ' License', '🛡️')}"
        f"┌─────────────────────\n"
        f"│ 🔑  Key / দিন :  <b>{limit_line}</b>\n"
        f"│ ⏱️  মেয়াদ     :  <b>{hours} ঘন্টা</b>\n"
        f"│ 🔒  Device    :  একটি ফোন\n"
        f"└─────────────────────\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_kb)
    )


# ══════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════

async def _send_admin_panel_msg(msg_obj, edit=False):
    limit = _admin_daily_key_limit["value"]
    hours = _admin_free_key_hours["value"]
    conn  = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM license_keys")
    total_keys = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM license_keys WHERE is_active=TRUE AND expires_at > %s", (int(time.time()),))
    active_keys = cur.fetchone()[0]
    cur.close(); conn.close()

    keyboard = [
        [
            btn("🔐 Custom Key", callback_data="admin_custom_key",   style="success"),
            btn("⏱️ Duration",   callback_data="admin_set_duration", style="primary"),
        ],
        [
            btn("🚦 Set Limit",  callback_data="admin_set_limit",    style="primary"),
            btn("📋 Keys List",  callback_data="admin_list_keys",    style="primary"),
        ],
        [
            btn("🤖 AUTO SELL KEY", callback_data="admin_auto_sell_key", style="success"),
        ],
        [
            btn("👑 SET ADMIN",  callback_data="admin_set_admin",    style="danger"),
        ],
        [btn("🔙 Back", callback_data="back_start", style="primary")],
    ]
    text = (
        f"{header('ADMIN PANEL', '⚙️')}"
        f"┌─────────────────────\n"
        f"│ ⏱️  Free duration :  <b>{hours}h</b>\n"
        f"│ 🚦  Daily limit   :  <b>{limit if limit > 0 else '∞'}</b>\n"
        f"│ 🔑  Total keys    :  <b>{total_keys}</b>\n"
        f"│ ✅  Active keys   :  <b>{active_keys}</b>\n"
        f"│ 👑  Total admins  :  <b>{len(ADMIN_IDS)}</b>\n"
        f"└─────────────────────\n"
        f"{footer()}"
    )
    if edit:
        await msg_obj.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg_obj.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def cb_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Access Denied!", show_alert=True); return
    await _send_admin_panel_msg(query, edit=True)


async def cb_admin_custom_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    await query.edit_message_text(
        f"{header('CUSTOM KEY', '🔐')}"
        f"কত <b>দিনের</b> Key বানাবেন?\n\n"
        f"│ <code>10</code>   → ১০ দিন\n"
        f"│ <code>1</code>    → ১ দিন\n"
        f"│ <code>0.5</code>  → ১২ ঘন্টা\n"
        f"│ <code>30</code>   → ১ মাস\n"
        f"{divider()}"
        f"<i>সংখ্যাটি টাইপ করুন 👇</i>",
        parse_mode="HTML"
    )
    return CUSTOM_KEY_DAYS


async def handle_custom_key_days(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END
    txt = update.message.text.strip().replace(",", ".")
    try:
        days = float(txt)
        assert days > 0
    except:
        await update.message.reply_text(
            "❌ সংখ্যা দিন (যেমন: <code>10</code> বা <code>0.5</code>)",
            parse_mode="HTML"
        )
        return CUSTOM_KEY_DAYS
    key     = create_license_key(days)
    exp     = datetime.datetime.now() + datetime.timedelta(days=days)
    exp_str = exp.strftime("%d/%m/%Y %H:%M")
    await update.message.reply_text(
        f"{header('CUSTOM KEY CREATED ✅', '🔐')}"
        f"🔑 <b>Key:</b>\n<code>{key}</code>\n\n"
        f"│ ⏱️  মেয়াদ  :  <b>{_fmt_duration(days)}</b>\n"
        f"│ 📅  Expire :  <b>{exp_str}</b>\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
        )
    )
    return ConversationHandler.END


async def cb_admin_auto_sell_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin Panel থেকে AUTO SELL KEY বানানোর শুরু"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Access Denied!", show_alert=True)
        return ConversationHandler.END
    await query.edit_message_text(
        f"{header('AUTO SELL KEY', '🤖')}"
        f"🔑 <b>AUTO SELL KEY</b> বানাতে কত <b>দিনের</b> Key চাই?\n\n"
        f"│ <code>1</code>   → ১ দিন\n"
        f"│ <code>7</code>   → ৭ দিন\n"
        f"│ <code>30</code>  → ১ মাস\n"
        f"│ <code>0.5</code> → ১২ ঘন্টা\n\n"
        f"⚡ এই Key দিয়ে App-এ AUTO SELL বাটন দেখা যাবে!\n"
        f"{divider()}"
        f"<i>সংখ্যাটি টাইপ করুন 👇</i>",
        parse_mode="HTML"
    )
    return AUTO_SELL_KEY_DAYS


async def handle_auto_sell_key_days(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """AUTO SELL KEY এর দিন সংখ্যা নিয়ে key তৈরি করে"""
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END
    txt = update.message.text.strip().replace(",", ".")
    try:
        days = float(txt)
        assert days > 0
    except:
        await update.message.reply_text(
            "❌ সঠিক সংখ্যা দিন (যেমন: <code>7</code> বা <code>0.5</code>)",
            parse_mode="HTML"
        )
        return AUTO_SELL_KEY_DAYS

    key     = create_license_key(days, key_type="auto_sell")
    exp     = datetime.datetime.now() + datetime.timedelta(days=days)
    exp_str = exp.strftime("%d/%m/%Y %H:%M")

    await update.message.reply_text(
        f"{header('AUTO SELL KEY CREATED ✅', '🤖')}"
        f"🔑 <b>AUTO SELL Key:</b>\n<code>{key}</code>\n\n"
        f"┌─────────────────────\n"
        f"│ 🤖  Type   :  <b>AUTO SELL</b>\n"
        f"│ ⏱️  মেয়াদ  :  <b>{_fmt_duration(days)}</b>\n"
        f"│ 📅  Expire :  <b>{exp_str}</b>\n"
        f"└─────────────────────\n\n"
        f"⚡ এই Key দিয়ে লগিন করলে App-এ <b>AUTO SELL</b> বাটন দেখাবে!\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
        )
    )
    return ConversationHandler.END


async def cb_admin_set_duration(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    cur_h = _admin_free_key_hours["value"]
    await query.edit_message_text(
        f"{header('KEY DURATION SET', '⏱️')}"
        f"বর্তমান মেয়াদ: <b>{cur_h} ঘন্টা</b>\n\n"
        f"User 'GET NEW KEY' চাপলে কত <b>ঘন্টার</b> Key পাবে?\n\n"
        f"│ <code>1</code>   → ১ ঘন্টা\n"
        f"│ <code>24</code>  → ১ দিন\n"
        f"│ <code>72</code>  → ৩ দিন\n"
        f"│ <code>168</code> → ৭ দিন\n"
        f"{divider()}"
        f"<i>সংখ্যাটি টাইপ করুন 👇</i>",
        parse_mode="HTML"
    )
    return USER_KEY_DURATION


async def handle_set_duration(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END
    txt = update.message.text.strip()
    try:
        hours = int(txt)
        assert hours > 0
    except:
        await update.message.reply_text(
            "❌ পূর্ণসংখ্যা দিন (যেমন: <code>24</code>)",
            parse_mode="HTML"
        )
        return USER_KEY_DURATION
    _admin_free_key_hours["value"] = hours
    await update.message.reply_text(
        f"✅ <b>Duration Updated!</b>\n\n"
        f"User এখন থেকে <b>{hours} ঘন্টার</b> Key পাবে।",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
        )
    )
    return ConversationHandler.END


async def cb_admin_set_limit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    current = _admin_daily_key_limit["value"]
    cur_label = "Unlimited ∞" if current == 0 else f"{current}টি"
    await query.edit_message_text(
        f"{header('SET DAILY LIMIT', '🚦')}"
        f"বর্তমান Limit: <b>{cur_label}</b>\n\n"
        f"প্রতি User ২৪ ঘন্টায় কয়টি Key নিতে পারবে?\n\n"
        f"│ <code>0</code> → Unlimited ∞\n"
        f"│ <code>1</code> → দিনে ১টি\n"
        f"│ <code>3</code> → দিনে ৩টি\n"
        f"│ <code>5</code> → দিনে ৫টি\n"
        f"{divider()}"
        f"<i>সংখ্যাটি টাইপ করুন 👇</i>",
        parse_mode="HTML"
    )
    return SET_LIMIT_STATE


async def handle_set_limit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END
    txt = update.message.text.strip()
    try:
        limit = int(txt)
        assert limit >= 0
    except:
        await update.message.reply_text(
            "❌ সংখ্যা দিন (<code>0</code> = unlimited)",
            parse_mode="HTML"
        )
        return SET_LIMIT_STATE
    _admin_daily_key_limit["value"] = limit
    label = "∞ Unlimited" if limit == 0 else f"<b>{limit}টি</b>"
    await update.message.reply_text(
        f"✅ <b>Limit Updated!</b>\n\n"
        f"প্রতি User প্রতিদিন {label} Key নিতে পারবে।\n"
        f"🔄 ২৪ ঘন্টা পর Automatic Reset।",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
        )
    )
    return ConversationHandler.END


async def cb_admin_set_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Access Denied!", show_alert=True)
        return ConversationHandler.END

    admin_list_str = "\n".join([f"│ 👑  <code>{aid}</code>" for aid in ADMIN_IDS])

    await query.edit_message_text(
        f"{header('SET ADMIN', '👑')}"
        f"বর্তমান Admin তালিকা:\n"
        f"{admin_list_str}\n\n"
        f"{divider()}"
        f"নতুন Admin যোগ করতে তার <b>User ID</b> বা <b>@username</b> পাঠান:\n\n"
        f"│ উদাহরণ: <code>123456789</code>\n"
        f"│ অথবা: <code>@username</code>\n\n"
        f"<i>/cancel দিয়ে বাতিল করুন</i>",
        parse_mode="HTML"
    )
    return SET_ADMIN_STATE


async def handle_set_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END

    text = update.message.text.strip()

    if text.startswith("@"):
        username = text.lstrip("@")
        try:
            chat = await ctx.bot.get_chat(f"@{username}")
            new_admin_id = chat.id
            new_admin_name = f"@{username}"
        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Username পাওয়া যায়নি!</b>\n\n"
                f"Error: <code>{esc(str(e)[:100])}</code>\n\n"
                f"সরাসরি Numeric <b>User ID</b> দিন।",
                parse_mode="HTML"
            )
            return SET_ADMIN_STATE
    elif text.isdigit():
        new_admin_id   = int(text)
        new_admin_name = str(new_admin_id)
    else:
        await update.message.reply_text(
            "❌ <b>সঠিক ID বা @username দিন!</b>\n\n"
            "উদাহরণ: <code>123456789</code> বা <code>@username</code>",
            parse_mode="HTML"
        )
        return SET_ADMIN_STATE

    if new_admin_id in ADMIN_IDS:
        safe_name = esc(new_admin_name)
        await update.message.reply_text(
            f"⚠️ <b>{safe_name}</b> ইতিমধ্যে Admin আছে!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
            )
        )
        return ConversationHandler.END

    ADMIN_IDS.append(new_admin_id)

    await update.message.reply_text(
        f"{header('ADMIN ADDED ✅', '👑')}"
        f"🎉 নতুন Admin যোগ হয়েছে!\n\n"
        f"│ 👑  ID     :  <code>{new_admin_id}</code>\n"
        f"│ 📊  মোট   :  <b>{len(ADMIN_IDS)}</b> জন Admin\n"
        f"{divider()}"
        f"⚠️ <i>Note: Server restart হলে এই change হারিয়ে যাবে।</i>\n"
        f"<i>Permanent করতে ADMIN_IDS env variable আপডেট করুন।</i>\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
        )
    )
    return ConversationHandler.END


async def cb_admin_list_keys(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT key, expires_at, is_active, device_id, tg_username FROM license_keys ORDER BY created_at DESC LIMIT 10"
    )
    rows = cur.fetchall(); cur.close(); conn.close()
    if not rows:
        await query.edit_message_text(
            f"{header('KEYS LIST', '📋')}কোনো Key নেই।",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
            )
        )
        return
    now   = int(time.time())
    lines = [f"{header('শেষ ১০টি Key', '📋')}"]
    for i, r in enumerate(rows, 1):
        k, exp, active, dev, tg_user = r
        ok      = active and exp > now
        status  = "🟢" if ok else "🔴"
        rem     = max(0, exp - now)
        d, h    = rem // 86400, (rem % 86400) // 3600
        dev_str = "🔒 Locked" if dev else "🔓 Free"
        user_str = f"@{esc(tg_user)}" if tg_user else "—"
        lines.append(
            f"{status} <b>#{i}</b> <code>{k[-12:]}</code>\n"
            f"   👤 {user_str}  |  ⏱ {d}d {h}h  |  {dev_str}"
        )
    await query.edit_message_text(
        "\n".join(lines) + footer(),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 Admin Panel", callback_data="admin_panel", style="primary")]]
        )
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _captcha_pending.pop(uid, None)
    await update.message.reply_text(
        "❌ <b>বাতিল করা হয়েছে।</b>\n\n/start দিয়ে আবার শুরু করুন।",
        parse_mode="HTML"
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#  BOT RUNNER (With Timeout Fix + Infinite Retry)
# ══════════════════════════════════════════════════
DEVICE_BTN_RE = r"^[🟢🟡🔴❌⚪]\s*#\d+\b"
ADMIN_MENU_RE = (
    r"^(📱 Device List|⏳ Pending|🔴 Banned List|✅ Approve|🤖 AutoSell|"
    r"🚫 Device Ban|⏳ Schedule Ban|🔓 Unban|❌ Reject|📊 Export XLSX|"
    r"⚡ Auto-Approve|⚙️ Key Panel|🔄 Menu|🔙 Main Menu|🔄 Refresh List|"
    r"⬅️ Prev Page|➡️ Next Page|[🟢🟡🔴❌⚪]\s*#\d+.*)$"
)

def get_admin_reply_kb():
    return ReplyKeyboardMarkup(
        [
            [kbtn("📱 Device List", "primary"),  kbtn("⏳ Pending", "primary"),      kbtn("🔴 Banned List", "danger")],
            [kbtn("✅ Approve", "success"),      kbtn("🤖 AutoSell", "success"),     kbtn("❌ Reject", "danger")],
            [kbtn("🚫 Device Ban", "danger"),    kbtn("⏳ Schedule Ban", "primary"), kbtn("🔓 Unban", "success")],
            [kbtn("📊 Export XLSX", "primary"),  kbtn("⚡ Auto-Approve", "primary"), kbtn("⚙️ Key Panel", "primary")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

def build_device_list_reply_kb(ctx: ContextTypes.DEFAULT_TYPE = None, page: int = 0):
    sync_all_hwid_schedules()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT id, COALESCE(user_device,''), brand, model, status, COALESCE(key_type,'regular')
        FROM device_hwid
        ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, id DESC
    """)
    rows = cur.fetchall(); cur.close(); conn.close()

    per_page = 20
    total = len(rows)
    max_page = max(0, (total - 1) // per_page) if total > 0 else 0
    page = max(0, min(page, max_page))
    if ctx is not None:
        ctx.user_data["dev_list_page"] = page

    chunk = rows[page * per_page : (page + 1) * per_page]
    kb_rows = []
    for did, ud, br, md, st, kt in chunk:
        st = st or "pending"
        ico = {"approved": "🟢", "pending": "🟡", "rejected": "❌", "banned": "🔴"}.get(st, "⚪")
        style = {"approved": "success", "pending": "primary", "rejected": "danger", "banned": "danger"}.get(st, "primary")
        mname = ud.strip() if ud and ud.strip() else f"{br} {md}".strip()
        if not mname:
            mname = "Unknown Device"
        tag = " [AUTO]" if (st == "approved" and kt == "auto_sell") else ""
        label = f"{ico} #{did} {mname[:24]}{tag}"
        kb_rows.append([kbtn(label, style)])

    nav_row = []
    if page > 0:
        nav_row.append(kbtn("⬅️ Prev Page", "primary"))
    if page < max_page:
        nav_row.append(kbtn("➡️ Next Page", "primary"))
    if nav_row:
        kb_rows.append(nav_row)

    kb_rows.append([kbtn("🔄 Refresh List", "primary"), kbtn("🔙 Main Menu", "danger")])
    return ReplyKeyboardMarkup(kb_rows, resize_keyboard=True, is_persistent=True), total, page, max_page

def _admin_dashboard_text(name: str) -> str:
    sync_all_hwid_schedules()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM device_hwid GROUP BY status")
    sm = {r[0]: r[1] for r in cur.fetchall()}
    cur.close(); conn.close()
    auto_st = "ON ✅" if get_app_setting("auto_approve", "0") == "1" else "OFF ❌"
    return (
        f"{header(APP_NAME + ' ADMIN', '👑')}"
        f"👋 স্বাগতম Admin <b>{name}!</b>\n\n"
        f"┌─────────────────────\n"
        f"│ 🟢 Approved : <b>{sm.get('approved', 0)}</b>\n"
        f"│ 🟡 Pending  : <b>{sm.get('pending', 0)}</b>\n"
        f"│ 🔴 Rejected : <b>{sm.get('rejected', 0)}</b>\n"
        f"│ 🚫 Banned   : <b>{sm.get('banned', 0)}</b>\n"
        f"│ ⚡ Auto     : <b>{auto_st}</b>\n"
        f"└─────────────────────\n\n"
        f"👇 নিচের <b>রঙিন বাটন</b> থেকে কন্ট্রোল করুন:{footer()}"
    )

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_joined(update, ctx, user.id):
        await update.message.reply_text(
            f"{header('JOIN REQUIRED', '⚠️')}"
            f"🚀 বট ব্যবহার করতে আমাদের অফিসিয়াল চ্যানেলে জয়েন করুন:\n\n"
            f"👇 নিচের বাটনে ক্লিক করে জয়েন করুন:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [btn("📢 Join Channel", url=FORCE_CHANNEL_LINK, style="primary")],
                [btn("✅ Joined (Check Again)", callback_data="check_join", style="success")],
            ]),
        )
        return
    name = esc(user.first_name or "বন্ধু")
    if is_admin(user.id):
        await update.message.reply_text(
            _admin_dashboard_text(name),
            parse_mode="HTML",
            reply_markup=get_admin_reply_kb(),
        )
    else:
        await update.message.reply_text(
            f"{header(APP_NAME + ' Access', '🛡️')}"
            f"👋 স্বাগতম, <b>{name}!</b>\n\n"
            f"┌─────────────────────\n"
            f"│ 📱  App     :  <b>{esc(APP_NAME)}</b>\n"
            f"│ 🔐  System  :  <b>Device Approval</b>\n"
            f"│ 📩  Step    :  অ্যাপে ঢুকে <b>REQUEST ADMIN</b> চাপুন\n"
            f"└─────────────────────\n"
            f"{footer()}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [btn("🔑  GET NEW KEY", callback_data="get_new_key", style="success")],
                [
                    btn("ℹ️ Info", callback_data="info", style="primary"),
                    btn("📞 Support", callback_data="support", style="primary"),
                ],
            ]),
        )

async def rk_main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    name = esc(update.effective_user.first_name or "Admin")
    await update.message.reply_text(
        _admin_dashboard_text(name),
        parse_mode="HTML",
        reply_markup=get_admin_reply_kb(),
    )
    return ConversationHandler.END

async def cb_hwid_inline_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("❌ Access Denied!", show_alert=True); return
    _, act, did_s = q.data.split(":")
    did = int(did_s)
    conn = get_db(); cur = conn.cursor()
    toast = "✅ Updated!"
    if act == "ok":
        cur.execute("UPDATE device_hwid SET status='approved',key_type='regular',expires_at=0,ban_reason='',ban_start_at=0,ban_until=0 WHERE id=%s", (did,))
        toast = "✅ Approved (Regular)"
    elif act == "as":
        cur.execute("UPDATE device_hwid SET status='approved',key_type='auto_sell',expires_at=0,ban_reason='',ban_start_at=0,ban_until=0 WHERE id=%s", (did,))
        toast = "🤖 Approved (AUTO SELL)"
    elif act == "rej":
        cur.execute("UPDATE device_hwid SET status='rejected',ban_reason='Rejected by Admin',ban_start_at=0,ban_until=0 WHERE id=%s", (did,))
        toast = "❌ Rejected!"
    elif act == "ban":
        cur.execute("UPDATE device_hwid SET status='banned',ban_reason='Banned by Admin',ban_start_at=0,ban_until=0 WHERE id=%s", (did,))
        toast = "🚫 Banned!"
    elif act == "unban":
        cur.execute("UPDATE device_hwid SET status='approved',ban_reason='',ban_start_at=0,ban_until=0 WHERE id=%s", (did,))
        toast = "🔓 Unbanned & Approved!"
    elif act == "locksig":
        cur.execute("SELECT COALESCE(last_sig,'') FROM device_hwid WHERE id=%s", (did,))
        srow = cur.fetchone()
        sig_val = (srow[0] or "").strip().upper() if srow else ""
        if not sig_val:
            cur.close(); conn.close()
            await q.answer("⚠️ এই ডিভাইসের APK Signature এখনো পাওয়া যায়নি! আগে অ্যাপ ওপেন করুন।", show_alert=True)
            return
        set_app_setting("allowed_apk_sig", sig_val)
        toast = f"🔏 APK Signature Locked! ({sig_val[:12]}...)"
    conn.commit(); cur.close(); conn.close()
    row = fetch_device_row(did)
    await q.answer(toast, show_alert=True)
    if row:
        cap = format_device_caption(row)
        kb  = build_ptb_device_kb(did, row[15])
        try:
            await q.edit_message_caption(caption=cap, parse_mode="HTML", reply_markup=kb)
        except Exception:
            try:
                await q.edit_message_text(text=cap, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass

async def cb_hwid_sban_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    did = int(q.data.split(":")[2]); ctx.user_data["sban_dev_id"] = did
    await q.message.reply_text(
        f"{header(f'SCHEDULE BAN #{did}', '⏳')}"
        f"সময় লিখুন (<code>| কারণ</code> ঐচ্ছিক):\n\n"
        f"• <code>2h</code>  • <code>7d | স্প্যাম</code>\n"
        f"• <code>after 1h</code>  • <code>after 1h for 24h</code>\n"
        f"• <code>2026-11-26 22:00 for 6h</code>\n"
        f"{divider()}<i>/cancel দিয়ে বাতিল করুন</i>",
        parse_mode="HTML",
    )
    return HWID_INLINE_SBAN

async def handle_hwid_sban_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    did = ctx.user_data.get("sban_dev_id")
    if not did: return ConversationHandler.END
    segs = [s.strip() for s in update.message.text.split("|")]
    sa, ua, err = parse_ban_schedule(segs[0])
    if err: await update.message.reply_text(err, parse_mode="HTML"); return HWID_INLINE_SBAN
    rsn = segs[1] if len(segs) > 1 and segs[1] else "Scheduled Ban"
    now = int(time.time()); imm = (sa <= now)
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE device_hwid SET status=%s,ban_reason=%s,ban_start_at=%s,ban_until=%s WHERE id=%s", ("banned" if imm else "approved", rsn, 0 if imm else sa, ua, did))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text(
        f"⏳ <b>Device #{did} Schedule Ban Set!</b>\n📝 Reason: {esc(rsn)}",
        parse_mode="HTML", reply_markup=get_admin_reply_kb(),
    )
    return ConversationHandler.END

async def _send_device_list_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    kb, total, page, max_page = build_device_list_reply_kb(ctx, page)
    if total == 0:
        await update.message.reply_text("📱 কোনো ডিভাইস নেই।", reply_markup=get_admin_reply_kb())
        return
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM device_hwid GROUP BY status")
    sm = {r[0]: r[1] for r in cur.fetchall()}
    cur.close(); conn.close()
    await update.message.reply_text(
        f"{header('ALL DEVICES LIST', '📱')}"
        f"📊 মোট ডিভাইস: <b>{total}</b> টি  (Page {page + 1}/{max_page + 1})\n"
        f"┌─────────────────────\n"
        f"│ 🟢 Approved : <b>{sm.get('approved', 0)}</b>\n"
        f"│ 🟡 Pending  : <b>{sm.get('pending', 0)}</b>\n"
        f"│ 🔴 Banned   : <b>{sm.get('banned', 0)}</b>  | ❌ Rej: <b>{sm.get('rejected', 0)}</b>\n"
        f"└─────────────────────\n\n"
        f"👇 নিচের <b>রঙিন Reply Keyboard</b> থেকে যেকোনো ডিভাইসের নামে ক্লিক করে কন্ট্রোল করুন:",
        parse_mode="HTML",
        reply_markup=kb,
    )

async def rk_device_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await _send_device_list_page(update, ctx, 0)
    return ConversationHandler.END

async def rk_device_prev(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    cur_p = int(ctx.user_data.get("dev_list_page", 0))
    await _send_device_list_page(update, ctx, max(0, cur_p - 1))
    return ConversationHandler.END

async def rk_device_next(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    cur_p = int(ctx.user_data.get("dev_list_page", 0))
    await _send_device_list_page(update, ctx, cur_p + 1)
    return ConversationHandler.END

async def rk_select_device(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    txt = (update.message.text or "").strip()
    m = re.search(r"#(\d+)\b", txt)
    if not m:
        await update.message.reply_text("❌ ডিভাইস আইডি পাওয়া যায়নি।")
        return ConversationHandler.END
    did = int(m.group(1))
    sync_all_hwid_schedules()
    row = fetch_device_row(did)
    if not row:
        await update.message.reply_text(f"❌ Device #{did} পাওয়া যায়নি।")
        return ConversationHandler.END
    await update.message.reply_text(
        format_device_caption(row),
        parse_mode="HTML",
        reply_markup=build_ptb_device_kb(did, row[15] or "pending"),
    )
    return ConversationHandler.END

async def rk_pending_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM device_hwid WHERE status='pending' ORDER BY id DESC LIMIT 10")
    ids = [r[0] for r in cur.fetchall()]; cur.close(); conn.close()
    if not ids:
        await update.message.reply_text("✅ কোনো Pending Request নেই!", reply_markup=get_admin_reply_kb()); return ConversationHandler.END
    for did in ids:
        row = fetch_device_row(did)
        if row:
            await update.message.reply_text(
                format_device_caption(row),
                parse_mode="HTML",
                reply_markup=build_ptb_device_kb(did, "pending"),
            )
    return ConversationHandler.END

async def rk_banned_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    sync_all_hwid_schedules()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT id,hwid,COALESCE(user_device,''),brand,model,ban_reason,ban_until,ban_start_at
        FROM device_hwid WHERE status='banned' OR ban_start_at>0 ORDER BY id DESC LIMIT 15
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    if not rows:
        await update.message.reply_text("🟢 কোনো Banned বা Scheduled Ban ডিভাইস নেই!", reply_markup=get_admin_reply_kb()); return ConversationHandler.END
    now = int(time.time()); lines = [f"{header('BANNED & SCHEDULED', '🔴')}"]
    for did, hw, ud, br, md, rsn, bu, bs in rows:
        mname = ud.strip() if ud and ud.strip() else f"{br} {md}".strip()
        info = f"⏳ @{datetime.datetime.fromtimestamp(bs,BD_TZ).strftime('%d/%m %H:%M')}" if bs>now else (f"⏱ {max(0,bu-now)//60}m left" if bu>0 else "♾ Perm")
        lines.append(f"🔴 <b>#{did}</b> {esc(mname)} (<code>{hw[-8:]}</code>)\n   📝 {esc(rsn)} | {info}")
    await update.message.reply_text("\n".join(lines)+footer(), parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

async def rk_export_xlsx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    sync_all_hwid_schedules()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT id,status,key_type,COALESCE(user_device,''),brand,model,device_name,
               android_ver,sdk_int,COALESCE(root_status,''),COALESCE(ram,''),
               COALESCE(storage,''),COALESCE(network,''),hwid,ban_reason,created_at
        FROM device_hwid ORDER BY id DESC
    """)
    db_rows = cur.fetchall(); cur.close(); conn.close()
    rows = [["ID","Status","Type","Mobile Name","Brand","Model","Device","Android","SDK","Root","RAM","Storage","Network","HWID (SHA-256)","Ban Reason","Time (BD)"]]
    for r in db_rows:
        mname = r[3].strip() if r[3] and r[3].strip() else f"{r[4]} {r[5]}".strip()
        rows.append([r[0],r[1].upper(),r[2],mname,r[4],r[5],r[6],r[7],r[8],r[9],r[10],r[11],r[12],r[13],r[14],datetime.datetime.fromtimestamp(r[15],BD_TZ).strftime("%d/%m/%Y %H:%M")])
    await update.message.reply_document(document=io.BytesIO(build_xlsx_bytes(rows,"AllDevices")), filename=f"ALL_DEVICES_{int(time.time())}.xlsx", caption=f"📊 মোট ডিভাইস: <b>{len(db_rows)}</b> টি", parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

async def rk_toggle_auto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    nv = "0" if get_app_setting("auto_approve","0")=="1" else "1"
    set_app_setting("auto_approve", nv)
    await update.message.reply_text(f"⚡ Auto-Approve এখন: <b>{'ON ✅' if nv=='1' else 'OFF ❌'}</b>", parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

async def rk_key_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await _send_admin_panel_msg(update.message, edit=False)
    return ConversationHandler.END

async def rk_prompt_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("✅ <b>Approve (Regular):</b>\nDevice ID বা HWID (ও চাইলে দিন) লিখুন:\nউদা: <code>1</code> বা <code>1 30</code>", parse_mode="HTML")
    return HWID_APPROVE_STATE

async def rk_prompt_autosell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("🤖 <b>Approve (AUTO SELL):</b>\nDevice ID বা HWID (ও চাইলে দিন) লিখুন:\nউদা: <code>1</code> বা <code>1 30</code>", parse_mode="HTML")
    return HWID_AUTOSELL_STATE

async def rk_prompt_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("❌ <b>Reject Device:</b>\nDevice ID বা HWID লিখুন (উদা: <code>1 কারণ</code>):", parse_mode="HTML")
    return HWID_REJECT_STATE

async def rk_prompt_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("🚫 <b>Device Ban (Permanent):</b>\nলিখুন: <code>ID_বা_HWID কারণ</code>", parse_mode="HTML")
    return HWID_BAN_STATE

async def rk_prompt_sban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("⏳ <b>Schedule Ban:</b>\nলিখুন: <code>ID | সময় | কারণ</code>\nউদা: <code>1 | 2h</code> বা <code>1 | after 1h for 24h</code>", parse_mode="HTML")
    return HWID_SBAN_STATE

async def rk_prompt_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("🔓 <b>Unban Device:</b>\nDevice ID বা HWID লিখুন:", parse_mode="HTML")
    return HWID_UNBAN_STATE

async def _do_approve(update: Update, ktype: str):
    parts = update.message.text.strip().split()
    hw = resolve_hwid(parts[0]) or parts[0].upper()
    days = float(parts[1]) if len(parts)>=2 and parts[1].replace('.','',1).isdigit() else 0.0
    now = int(time.time()); exp = int(now + days*86400) if days>0 else 0
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO device_hwid (hwid,status,key_type,expires_at,created_at,last_seen) VALUES (%s,'approved',%s,%s,%s,%s) ON CONFLICT (hwid) DO UPDATE SET status='approved',key_type=EXCLUDED.key_type,expires_at=EXCLUDED.expires_at,ban_reason='',ban_start_at=0,ban_until=0", (hw,ktype,exp,now,now))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text(f"✅ Approved ({ktype})!\n<code>{hw}</code>", parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

async def handle_hwid_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await _do_approve(update, "regular") if is_admin(update.effective_user.id) else ConversationHandler.END

async def handle_hwid_autosell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await _do_approve(update, "auto_sell") if is_admin(update.effective_user.id) else ConversationHandler.END

async def handle_hwid_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    p = update.message.text.strip().split(None, 1)
    hw = resolve_hwid(p[0]) or p[0].upper()
    rsn = p[1] if len(p)>1 else "Rejected by Admin"
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE device_hwid SET status='rejected',ban_reason=%s,ban_start_at=0,ban_until=0 WHERE hwid=%s", (rsn, hw))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text(f"❌ Rejected!\n<code>{hw}</code>", parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

async def handle_hwid_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    p = update.message.text.strip().split(None, 1)
    hw = resolve_hwid(p[0]) or p[0].upper()
    rsn = p[1] if len(p)>1 else "Banned by Admin"
    now = int(time.time())
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO device_hwid (hwid,status,ban_reason,ban_start_at,ban_until,created_at,last_seen) VALUES (%s,'banned',%s,0,0,%s,%s) ON CONFLICT (hwid) DO UPDATE SET status='banned',ban_reason=EXCLUDED.ban_reason,ban_start_at=0,ban_until=0", (hw,rsn,now,now))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text(f"🚫 Device Banned!\n<code>{hw}</code>", parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

async def handle_hwid_sban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    segs = [s.strip() for s in update.message.text.split("|")]
    if len(segs) < 2:
        await update.message.reply_text("❌ ফরম্যাট: <code>1 | 2h</code>", parse_mode="HTML"); return HWID_SBAN_STATE
    hw = resolve_hwid(segs[0]) or segs[0].upper()
    rsn = segs[2] if len(segs)>=3 and segs[2] else "Scheduled Ban"
    sa, ua, err = parse_ban_schedule(segs[1])
    if err: await update.message.reply_text(err, parse_mode="HTML"); return HWID_SBAN_STATE
    now = int(time.time()); imm = (sa <= now)
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO device_hwid (hwid,status,ban_reason,ban_start_at,ban_until,created_at,last_seen) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (hwid) DO UPDATE SET status=EXCLUDED.status,ban_reason=EXCLUDED.ban_reason,ban_start_at=EXCLUDED.ban_start_at,ban_until=EXCLUDED.ban_until", (hw,"banned" if imm else "approved",rsn,0 if imm else sa,ua,now,now))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text(f"⏳ Schedule Ban Set!\n<code>{hw}</code>", parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

async def handle_hwid_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    hw = resolve_hwid(update.message.text.strip())
    if not hw:
        await update.message.reply_text("❌ পাওয়া যায়নি।", reply_markup=get_admin_reply_kb()); return ConversationHandler.END
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE device_hwid SET status='approved',ban_reason='',ban_start_at=0,ban_until=0 WHERE hwid=%s", (hw,))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text(f"🔓 Unbanned!\n<code>{hw}</code>", parse_mode="HTML", reply_markup=get_admin_reply_kb())
    return ConversationHandler.END

def run_license_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def _run():
        bot_app = None
        while True:
            try:
                bot_app = (
                    Application.builder()
                    .token(LICENSE_BOT_TOKEN)
                    .connect_timeout(30.0).read_timeout(30.0).write_timeout(30.0)
                    .pool_timeout(30.0).get_updates_read_timeout(30.0).build()
                )
                txt_flt = filters.TEXT & ~filters.COMMAND & ~filters.Regex(ADMIN_MENU_RE)
                rk_routes = [
                    MessageHandler(filters.Regex(r"^📱 Device List$"),          rk_device_list),
                    MessageHandler(filters.Regex(r"^🔄 Refresh List$"),         rk_device_list),
                    MessageHandler(filters.Regex(r"^⬅️ Prev Page$"),            rk_device_prev),
                    MessageHandler(filters.Regex(r"^➡️ Next Page$"),            rk_device_next),
                    MessageHandler(filters.Regex(r"^(🔙 Main Menu|🔄 Menu)$"),  rk_main_menu),
                    MessageHandler(filters.Regex(DEVICE_BTN_RE),                rk_select_device),
                    MessageHandler(filters.Regex(r"^⏳ Pending$"),              rk_pending_list),
                    MessageHandler(filters.Regex(r"^🔴 Banned List$"),          rk_banned_list),
                    MessageHandler(filters.Regex(r"^📊 Export XLSX$"),          rk_export_xlsx),
                    MessageHandler(filters.Regex(r"^⚡ Auto-Approve$"),         rk_toggle_auto),
                    MessageHandler(filters.Regex(r"^⚙️ Key Panel$"),            rk_key_panel),
                    MessageHandler(filters.Regex(r"^✅ Approve$"),              rk_prompt_approve),
                    MessageHandler(filters.Regex(r"^🤖 AutoSell$"),             rk_prompt_autosell),
                    MessageHandler(filters.Regex(r"^❌ Reject$"),               rk_prompt_reject),
                    MessageHandler(filters.Regex(r"^🚫 Device Ban$"),           rk_prompt_ban),
                    MessageHandler(filters.Regex(r"^⏳ Schedule Ban$"),         rk_prompt_sban),
                    MessageHandler(filters.Regex(r"^🔓 Unban$"),                rk_prompt_unban),
                ]
                conv = ConversationHandler(
                    entry_points=[
                        CallbackQueryHandler(cb_get_new_key,        pattern="^get_new_key$"),
                        CallbackQueryHandler(cb_admin_custom_key,   pattern="^admin_custom_key$"),
                        CallbackQueryHandler(cb_admin_set_duration, pattern="^admin_set_duration$"),
                        CallbackQueryHandler(cb_admin_set_limit,    pattern="^admin_set_limit$"),
                        CallbackQueryHandler(cb_admin_set_admin,    pattern="^admin_set_admin$"),
                        CallbackQueryHandler(cb_admin_auto_sell_key,pattern="^admin_auto_sell_key$"),
                        CallbackQueryHandler(cb_hwid_sban_inline,   pattern=r"^hw:sban:\d+$"),
                    ] + rk_routes,
                    states={
                        CAPTCHA_STATE:      [MessageHandler(txt_flt, handle_captcha)],
                        CUSTOM_KEY_DAYS:    [MessageHandler(txt_flt, handle_custom_key_days)],
                        USER_KEY_DURATION:  [MessageHandler(txt_flt, handle_set_duration)],
                        SET_LIMIT_STATE:    [MessageHandler(txt_flt, handle_set_limit)],
                        SET_ADMIN_STATE:    [MessageHandler(txt_flt, handle_set_admin)],
                        AUTO_SELL_KEY_DAYS: [MessageHandler(txt_flt, handle_auto_sell_key_days)],
                        HWID_APPROVE_STATE: [MessageHandler(txt_flt, handle_hwid_approve)],
                        HWID_AUTOSELL_STATE:[MessageHandler(txt_flt, handle_hwid_autosell)],
                        HWID_REJECT_STATE:  [MessageHandler(txt_flt, handle_hwid_reject)],
                        HWID_BAN_STATE:     [MessageHandler(txt_flt, handle_hwid_ban)],
                        HWID_SBAN_STATE:    [MessageHandler(txt_flt, handle_hwid_sban)],
                        HWID_UNBAN_STATE:   [MessageHandler(txt_flt, handle_hwid_unban)],
                        HWID_INLINE_SBAN:   [MessageHandler(txt_flt, handle_hwid_sban_inline)],
                    },
                    fallbacks=[CommandHandler("cancel", cmd_cancel)] + rk_routes,
                    allow_reentry=True,
                )
                async def cmd_locksig(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(update.effective_user.id): return
                    args = ctx.args or []
                    if not args:
                        cur_sig = _get_allowed_sig()
                        await update.message.reply_text(
                            f"🔏 <b>Current APK Signature Lock:</b>\n"
                            f"<code>{cur_sig or 'UNLOCKED (যেকোনো সিগনেচার)'}</code>\n\n"
                            f"Lock করতে: <code>/locksig &lt;Device_ID&gt;</code> অথবা ডিভাইস কার্ডে <b>🔏 LOCK THIS SIG</b> চাপুন।\n"
                            f"Unlock করতে: <code>/unlocksig</code>",
                            parse_mode="HTML"
                        )
                        return
                    arg = args[0].strip().upper()
                    if len(arg) == 64:
                        set_app_setting("allowed_apk_sig", arg)
                        await update.message.reply_text(f"🔏 Signature Locked!\n<code>{arg}</code>", parse_mode="HTML")
                        return
                    hw = resolve_hwid(arg)
                    if not hw:
                        await update.message.reply_text("❌ ডিভাইস পাওয়া যায়নি।")
                        return
                    conn = get_db(); cur = conn.cursor()
                    cur.execute("SELECT COALESCE(last_sig,'') FROM device_hwid WHERE hwid=%s", (hw,))
                    r = cur.fetchone(); cur.close(); conn.close()
                    s = (r[0] or "").strip().upper() if r else ""
                    if not s:
                        await update.message.reply_text("⚠️ এই ডিভাইসের APK Signature এখনো আসেনি।")
                        return
                    set_app_setting("allowed_apk_sig", s)
                    await update.message.reply_text(f"🔏 APK Signature Locked!\n<code>{s}</code>", parse_mode="HTML")

                async def cmd_unlocksig(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(update.effective_user.id): return
                    set_app_setting("allowed_apk_sig", "")
                    await update.message.reply_text("🔓 APK Signature Lock খোলা হয়েছে।")

                bot_app.add_handler(CommandHandler("start", cmd_start))
                bot_app.add_handler(CommandHandler("locksig", cmd_locksig))
                bot_app.add_handler(CommandHandler("unlocksig", cmd_unlocksig))
                bot_app.add_handler(CallbackQueryHandler(cb_check_join,         pattern="^check_join$"))
                bot_app.add_handler(CallbackQueryHandler(cb_admin_panel,        pattern="^admin_panel$"))
                bot_app.add_handler(CallbackQueryHandler(cb_admin_list_keys,    pattern="^admin_list_keys$"))
                bot_app.add_handler(CallbackQueryHandler(cb_back_start,         pattern="^back_start$"))
                bot_app.add_handler(CallbackQueryHandler(cb_info,               pattern="^info$"))
                bot_app.add_handler(CallbackQueryHandler(cb_support,            pattern="^support$"))
                bot_app.add_handler(CallbackQueryHandler(cb_hwid_inline_action, pattern=r"^hw:(ok|as|rej|ban|unban|locksig):\d+$"))
                bot_app.add_handler(conv)
                for attempt in range(5):
                    try: await bot_app.initialize(); break
                    except Exception:
                        if attempt == 4: raise
                        await asyncio.sleep(10)
                await bot_app.start()
                await bot_app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
                print("[LICENSE BOT] ✅ Polling active!", flush=True)
                while True: await asyncio.sleep(3600)
            except Exception as e:
                print(f"[LICENSE BOT] ❌ Error: {e}", flush=True)
                await asyncio.sleep(15)
    try: loop.run_until_complete(_run())
    except KeyboardInterrupt: pass
    finally: loop.close()


# ══════════════════════════════════════════════════════════
#  EXISTING FLASK ENDPOINTS
# ══════════════════════════════════════════════════════════

@app.route("/send_otp", methods=["POST"])
def send_otp():
    data     = request.json
    api_id   = int(data["api_id"])
    api_hash = data["api_hash"]
    phone    = data["phone"]

    async def _send():
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone)
        phone_code_hash = result.phone_code_hash
        temp_session    = client.session.save()
        await client.disconnect()
        return phone_code_hash, temp_session

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        phone_code_hash, temp_session = loop.run_until_complete(_send())
        loop.close()
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO pending_otp (phone, api_id, api_hash, phone_code_hash, temp_session)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (phone) DO UPDATE SET
                api_id=EXCLUDED.api_id, api_hash=EXCLUDED.api_hash,
                phone_code_hash=EXCLUDED.phone_code_hash, temp_session=EXCLUDED.temp_session
        """, (phone, str(api_id), api_hash, phone_code_hash, temp_session))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"status": "otp_sent", "phone": phone})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    data            = request.get_json(silent=True) or {}
    phone           = data.get("phone", "").strip()
    otp             = data.get("otp", "").strip()
    tg_user_id      = (data.get("tg_user_id") or data.get("user_id", "")).strip()
    target_username = (data.get("target_username") or data.get("target", "@admin")).strip()

    if not phone or not otp or not tg_user_id:
        return jsonify({"status": "error", "message": "phone, otp, tg_user_id দরকার।"}), 400

    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT api_id, api_hash, phone_code_hash, temp_session FROM pending_otp WHERE phone = %s",
        (phone,)
    )
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return jsonify({"status": "error", "message": "No pending OTP."}), 400

    api_id, api_hash, phone_code_hash, temp_session = row

    async def _verify():
        client = TelegramClient(StringSession(temp_session), int(api_id), api_hash)
        await client.connect()
        await client.sign_in(phone, otp, phone_code_hash=phone_code_hash)
        session_string = client.session.save()
        await client.disconnect()
        return session_string

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        session_string = loop.run_until_complete(_verify())
        loop.close()
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_sessions (user_id, session_string, api_id, api_hash, target_username)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                session_string=EXCLUDED.session_string, api_id=EXCLUDED.api_id,
                api_hash=EXCLUDED.api_hash, target_username=EXCLUDED.target_username
        """, (tg_user_id, session_string, str(api_id), api_hash, target_username))
        cur.execute("DELETE FROM pending_otp WHERE phone = %s", (phone,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"status": "success", "message": "Session saved!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/automate_sale", methods=["POST"])
def automate_sale():
    data       = request.json
    tg_user_id = data["tg_user_id"]
    twofa_key  = data.get("twofa_key", "").strip()
    cookie     = data.get("cookie", "").strip()

    if not twofa_key:
        return jsonify({"status": "error", "message": "2FA key দরকার।"}), 400
    if not cookie or "c_user=" not in cookie:
        return jsonify({"status": "error", "message": "Cookie invalid — c_user= নেই।"}), 400

    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT session_string, api_id, api_hash, target_username FROM user_sessions WHERE user_id = %s",
        (tg_user_id,)
    )
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return jsonify({"status": "error", "message": "User not found."}), 404

    session_string, api_id, api_hash, target_username = row

    async def _sell():
        import re as _re
        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("Session expire হয়েছে।")

        sold = False
        step = {"current": 0}
        too_often_retry = {"count": 0, "max": 5}

        async def try_click_or_send(msg, btn_labels, fallback_text):
            """বাটন ক্লিক করার চেষ্টা করে, না পেলে text পাঠায়"""
            wanted = [l.lower() for l in btn_labels]
            for button_row in (msg.buttons or []):
                for button in button_row:
                    bt = (getattr(button, "text", "") or "").strip()
                    if any(w in bt.lower() for w in wanted):
                        try:
                            await msg.click(text=bt)
                            return True
                        except Exception:
                            pass
            if fallback_text:
                await client.send_message(BOT, fallback_text)
                return True
            return False

        @client.on(events.NewMessage(from_users=BOT))
        async def handler(event):
            nonlocal sold
            if sold:
                return
            msg  = event.message
            text = msg.text or ""
            low  = text.lower()

            # ⭐ Task off detect
            if is_task_off_message(text):
                step["current"] = -1
                print(f"[AUTOMATE_SALE] Task off: {text[:80]}", flush=True)
                return

            # Rate limit হ্যান্ডেল
            if "too often" in low or ("please wait" in low and "report" not in low):
                nums = _re.findall(r'\d+', text)
                wait_sec = int(nums[0]) + 2 if nums else 35
                too_often_retry["count"] += 1
                if too_often_retry["count"] <= too_often_retry["max"]:
                    step["current"] = 0
                    await asyncio.sleep(wait_sec)
                    await client.send_message(BOT, "/start")
                return

            # STEP 0 → 1: Welcome message
            if step["current"] == 0 and "welcome" in low:
                step["current"] = 1
                await asyncio.sleep(1)
                await try_click_or_send(msg, ["tasks", "task"], "📋 Tasks")

            # STEP 1 → 2: Task selection menu — keyboard এ 🍪 আছে কিনা চেক করো
            elif step["current"] == 1 and "please select a task" in low:
                cookie_btn_found = False
                for button_row in (msg.buttons or []):
                    for button in button_row:
                        bt = (getattr(button, "text", "") or "").strip()
                        if "🍪" in bt or "cookie" in bt.lower():
                            cookie_btn_found = True
                            break
                    if cookie_btn_found:
                        break

                if not cookie_btn_found:
                    step["current"] = -1  # task_off
                    print(f"[AUTOMATE_SALE] Task OFF — 🍪 button নেই", flush=True)
                    return

                step["current"] = 2
                await asyncio.sleep(1)
                # শুধু exact "🍪 ($0.0280)" button থাকলেই click — অন্য কিছু হলে task_off
                exact_btn = "🍪 ($0.0280)"
                clicked = False
                for button_row in (msg.buttons or []):
                    for button in button_row:
                        bt = (getattr(button, "text", "") or "").strip()
                        if bt == exact_btn:
                            try:
                                await msg.click(text=bt)
                                clicked = True
                            except Exception:
                                pass
                        if clicked: break
                    if clicked: break
                if not clicked:
                    task_off = True
                    print(f"[AUTOMATE_SALE] Task OFF — 🍪 ($0.0280) button নেই", flush=True)
                    return

            # STEP 2 → 3: Cookie task list দেখালে 2FA task বেছে নাও
            elif step["current"] == 2 and "🍪" in text:
                step["current"] = 3
                await asyncio.sleep(1)
                await try_click_or_send(
                    msg,
                    ["2fa", "create fb", "no mail"],
                    "🌟2FA:Create FB (No mail) ($0.0280)"
                )

            # STEP 3 → 4: Task description দেখালে Start দাও
            elif step["current"] == 3 and ("description" in low or "required" in low or "review time" in low):
                step["current"] = 4
                await asyncio.sleep(1)
                await try_click_or_send(msg, ["start", "▶️"], "▶️ Start")

            # STEP 4 → 5: 2FA key চাইলে key পাঠাও
            elif step["current"] == 4 and ("2fa key" in low or "enter your 2fa" in low or "2fa" in low):
                step["current"] = 5
                await asyncio.sleep(1)
                await client.send_message(BOT, twofa_key)

            # STEP 5 → 6: OTP/code দেখালে এবং cookie চাইলে cookie পাঠাও
            elif step["current"] == 5 and (
                "send the account" in low or
                "please send" in low or
                "one-time code" in low or
                "tap the code" in low or
                ("🍪" in text and "send" in low)
            ):
                step["current"] = 6
                await asyncio.sleep(1.5)
                await client.send_message(BOT, cookie)

            # STEP 6 → 7: Confirm registration button আসলে click করো
            elif step["current"] == 6 and (
                "confirm registration" in low or
                "press the button" in low or
                "cancel the task" in low
            ):
                step["current"] = 7
                await asyncio.sleep(1)
                await try_click_or_send(
                    msg,
                    ["account registered", "✅ account", "registered"],
                    "✅ Account registered"
                )

            # STEP 7 → 8: সফলভাবে জমা হলে
            elif step["current"] >= 6 and (
                "report has been received" in low or
                "your report has been received" in low or
                "task submitted successfully" in low or
                "submitted successfully" in low or
                "received! please wait" in low or
                ("received" in low and "wait" in low)
            ):
                step["current"] = 8
                sold = True
                if target_username:
                    try:
                        await client.send_message(
                            target_username,
                            f"🎉 Account Sold!\n2FA Key: {twofa_key}"
                        )
                    except Exception:
                        pass

        await client.send_message(BOT, "/start")
        for _ in range(120):   # 2 মিনিট — sell gap এর সাথে মিলিয়ে
            await asyncio.sleep(1)
            if step["current"] == 8:
                break
            if step["current"] == -1:  # ⭐ task_off
                break
        client.remove_event_handler(handler)
        await client.disconnect()
        return sold, step["current"]

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sold, last_step = loop.run_until_complete(_sell())
        loop.close()
        if sold:
            conn2 = get_db(); cur2 = conn2.cursor()
            cur2.execute("""
                INSERT INTO sell_stats (user_id, sell_count) VALUES (%s, 1)
                ON CONFLICT (user_id) DO UPDATE SET sell_count = sell_stats.sell_count + 1
            """, (tg_user_id,))
            conn2.commit(); cur2.close(); conn2.close()
            return jsonify({"status": "success", "message": "Sale সম্পন্ন! ✅"})
        if last_step == -1:  # ⭐ task_off
            return jsonify({"status": "task_off", "retry_after_seconds": 300})
        return jsonify({"status": "timeout", "message": f"Flow incomplete। Step: {last_step}/8"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ══════════════════════════════════════════════════════════
#  AUTO SELL — /auto_sell  (সম্পূর্ণ আলাদা endpoint)
#  /automate_sale এর সাথে কোনো সম্পর্ক নেই।
# ══════════════════════════════════════════════════════════

@app.route("/auto_sell", methods=["POST"])
def auto_sell_endpoint():
    """
    AUTO SELL Panel এর জন্য আলাদা endpoint।
    /automate_sale এর মতোই bot এ sell করে, কিন্তু:
    - task_off detect করে আলাদা response দেয়
    - rate_limit এ wait_seconds দেয়
    - session_expired detect করে
    - সম্পূর্ণ স্বাধীন ফাংশন
    """
    data = request.json or {}
    tg_user_id = data.get("tg_user_id", "").strip()
    twofa_key  = data.get("twofa_key", "").strip()
    cookie     = data.get("cookie", "").strip()

    if not tg_user_id:
        return jsonify({"status": "error", "message": "tg_user_id প্রয়োজন"}), 400
    if not twofa_key:
        return jsonify({"status": "error", "message": "2FA key প্রয়োজন"}), 400
    if not cookie or "c_user=" not in cookie:
        return jsonify({"status": "error", "message": "Cookie invalid"}), 400

    # ── Session DB থেকে নাও ──
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT session_string, api_id, api_hash, target_username "
        "FROM user_sessions WHERE user_id = %s",
        (tg_user_id,)
    )
    row = cur.fetchone(); cur.close(); conn.close()

    if not row:
        return jsonify({
            "status": "session_expired",
            "message": "User session নেই — আগে Connect করুন"
        }), 404

    session_string, api_id, api_hash, target_username = row

    # ── Sell flow (Telethon দিয়ে) ──
    async def _auto_sell():
        import re as _re
        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return "session_expired", "Session expire হয়েছে", 0

        sold = False
        task_off = False
        rate_limit_secs = 0
        step = {"current": 0}
        too_often_retry = {"count": 0, "max": 3}

        async def try_click_or_send(msg, btn_labels, fallback_text):
            wanted = [l.lower() for l in btn_labels]
            for button_row in (msg.buttons or []):
                for button in button_row:
                    bt = (getattr(button, "text", "") or "").strip()
                    if any(w in bt.lower() for w in wanted):
                        try:
                            await msg.click(text=bt)
                            return True
                        except Exception:
                            pass
            if fallback_text:
                await client.send_message(BOT, fallback_text)
                return True
            return False

        @client.on(events.NewMessage(from_users=BOT))
        async def handler(event):
            nonlocal sold, task_off, rate_limit_secs
            if sold or task_off:
                return
            msg  = event.message
            text = msg.text or ""
            low  = text.lower()

            # ⭐ Task off detect
            if is_task_off_message(text):
                task_off = True
                print(f"[AUTO_SELL] Task off: {text[:80]}", flush=True)
                return

            # Rate limit detect
            if "too often" in low or ("please wait" in low and "report" not in low):
                nums = _re.findall(r'\d+', text)
                wait_s = int(nums[0]) + 2 if nums else 35
                too_often_retry["count"] += 1
                if too_often_retry["count"] <= too_often_retry["max"]:
                    step["current"] = 0
                    await asyncio.sleep(wait_s)
                    rate_limit_secs = wait_s
                    await client.send_message(BOT, "/start")
                else:
                    rate_limit_secs = wait_s
                return

            # STEP 0 → 1: Welcome
            if step["current"] == 0 and "welcome" in low:
                step["current"] = 1
                await asyncio.sleep(1)
                await try_click_or_send(msg, ["tasks", "task"], "📋 Tasks")

            # STEP 1 → 2: Task menu — keyboard এ 🍪 আছে কিনা চেক করো
            elif step["current"] == 1 and "please select a task" in low:
                # Keyboard এ 🍪 button খোঁজো
                cookie_btn_found = False
                for button_row in (msg.buttons or []):
                    for button in button_row:
                        bt = (getattr(button, "text", "") or "").strip()
                        if "🍪" in bt or "cookie" in bt.lower():
                            cookie_btn_found = True
                            break
                    if cookie_btn_found:
                        break

                if not cookie_btn_found:
                    # 🍪 button নেই → Task OFF
                    task_off = True
                    print(f"[AUTO_SELL] Task OFF — 🍪 button নেই keyboard এ", flush=True)
                    return

                step["current"] = 2
                await asyncio.sleep(1)
                # শুধু exact "🍪 ($0.0280)" button থাকলেই click — অন্য কিছু হলে task_off
                exact_btn = "🍪 ($0.0280)"
                clicked = False
                for button_row in (msg.buttons or []):
                    for button in button_row:
                        bt = (getattr(button, "text", "") or "").strip()
                        if bt == exact_btn:
                            try:
                                await msg.click(text=bt)
                                clicked = True
                            except Exception:
                                pass
                        if clicked: break
                    if clicked: break
                if not clicked:
                    task_off = True
                    print(f"[AUTO_SELL] Task OFF — 🍪 ($0.0280) button নেই", flush=True)
                    return

            # STEP 2 → 3: Cookie list → 2FA task
            elif step["current"] == 2 and "🍪" in text:
                step["current"] = 3
                await asyncio.sleep(1)
                await try_click_or_send(
                    msg,
                    ["2fa", "create fb", "no mail"],
                    "🌟2FA:Create FB (No mail) ($0.0280)"
                )

            # STEP 3 → 4: Task description → Start
            elif step["current"] == 3 and (
                "description" in low or "required" in low or "review time" in low
            ):
                step["current"] = 4
                await asyncio.sleep(1)
                await try_click_or_send(msg, ["start", "▶️"], "▶️ Start")

            # STEP 4 → 5: 2FA key চাওয়া
            elif step["current"] == 4 and (
                "2fa key" in low or "enter your 2fa" in low or "2fa" in low
            ):
                step["current"] = 5
                await asyncio.sleep(1)
                await client.send_message(BOT, twofa_key)

            # STEP 5 → 6: Cookie চাওয়া
            elif step["current"] == 5 and (
                "send the account" in low
                or "please send" in low
                or "one-time code" in low
                or ("🍪" in text and "send" in low)
            ):
                step["current"] = 6
                await asyncio.sleep(1.5)
                await client.send_message(BOT, cookie)

            # STEP 6 → 7: Confirm registration
            elif step["current"] == 6 and (
                "confirm registration" in low
                or "press the button" in low
            ):
                step["current"] = 7
                await asyncio.sleep(1)
                await try_click_or_send(
                    msg,
                    ["account registered", "✅ account", "registered"],
                    "✅ Account registered"
                )

            # STEP 7 → 8: Success
            elif step["current"] >= 6 and (
                "report has been received" in low
                or "your report has been received" in low
                or "task submitted successfully" in low
                or "submitted successfully" in low
                or "received! please wait" in low
                or ("received" in low and "wait" in low)
            ):
                step["current"] = 8
                sold = True

        await client.send_message(BOT, "/start")
        for _ in range(120):  # 2 মিনিট — sell gap এর সাথে মিলিয়ে
            await asyncio.sleep(1)
            if step["current"] == 8:
                break
            if task_off:
                break
            if rate_limit_secs > 0 and too_often_retry["count"] > too_often_retry["max"]:
                break

        client.remove_event_handler(handler)
        await client.disconnect()

        if sold:
            return "success", "Sale সম্পন্ন", 0
        if task_off:
            return "task_off", "Task OFF — 🍪 button নেই", 0
        if rate_limit_secs > 0:
            return "rate_limit", "Rate limited", rate_limit_secs
        return "timeout", f"Step: {step['current']}/8", 0

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result_status, result_msg, wait_secs = loop.run_until_complete(_auto_sell())
        loop.close()

        if result_status == "success":
            # Stats update
            conn2 = get_db(); cur2 = conn2.cursor()
            cur2.execute("""
                INSERT INTO sell_stats (user_id, sell_count) VALUES (%s, 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    sell_count = sell_stats.sell_count + 1
            """, (tg_user_id,))
            conn2.commit(); cur2.close(); conn2.close()

            if target_username:
                try:
                    loop2 = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop2)
                    # ✅ FIX: tg_user_id পাস করো session lookup এর জন্য
                    loop2.run_until_complete(_notify_sold(tg_user_id, target_username, twofa_key))
                    loop2.close()
                except Exception:
                    pass

            return jsonify({
                "status": "success",
                "message": "✅ Sale সম্পন্ন!"
            })

        if result_status == "task_off":
            return jsonify({
                "status": "task_off",
                "message": result_msg,
                "retry_after_seconds": wait_secs
            })

        if result_status == "rate_limit":
            return jsonify({
                "status": "rate_limit",
                "message": result_msg,
                "wait_seconds": wait_secs
            })

        if result_status == "session_expired":
            return jsonify({
                "status": "session_expired",
                "message": result_msg
            })

        return jsonify({
            "status": "timeout",
            "message": result_msg
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


async def _notify_sold(tg_user_id: str, target_username: str, twofa_key: str):
    """
    AUTO SELL সফল হলে target user কে Telegram এ notify করো।
    tg_user_id  — DB তে session খোঁজার key (numeric Telegram ID)
    target_username — message পাঠানোর destination (@username বা numeric id)
    """
    if not target_username:
        return
    try:
        conn = get_db(); cur = conn.cursor()
        # ✅ FIX: tg_user_id দিয়ে session lookup করো, target_username দিয়ে নয়
        cur.execute(
            "SELECT session_string, api_id, api_hash FROM user_sessions WHERE user_id = %s",
            (tg_user_id,)
        )
        row = cur.fetchone(); cur.close(); conn.close()
        if row:
            client = TelegramClient(StringSession(row[0]), int(row[1]), row[2])
            await client.connect()
            if await client.is_user_authorized():
                await client.send_message(
                    target_username,
                    f"🎉 AUTO SELL সফল!\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"🔑 2FA Key : {twofa_key}\n"
                    f"⏰ সময়    : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                    f"━━━━━━━━━━━━━━"
                )
            await client.disconnect()
    except Exception as e:
        print(f"[NOTIFY] Error: {e}", flush=True)


@app.route("/automate_cookie_sale", methods=["POST"])
def automate_cookie_sale():
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    uid        = str(data.get("uid", "")).strip()
    cookie     = str(data.get("cookie", "")).strip()

    if not tg_user_id:
        return jsonify({"status": "error", "message": "tg_user_id দরকার।"}), 400
    if not uid.isdigit():
        return jsonify({"status": "error", "message": "Numeric UID দরকার।"}), 400
    if not cookie or "c_user=" not in cookie:
        return jsonify({"status": "error", "message": "Cookie invalid।"}), 400

    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT session_string, api_id, api_hash, target_username FROM user_sessions WHERE user_id = %s",
        (tg_user_id,)
    )
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return jsonify({"status": "error", "message": "User not found."}), 404

    session_string, api_id, api_hash, target_username = row

    async def _sell_cookie():
        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("Session expire হয়েছে।")
        sold = False
        step = {"current": 0}

        async def click_or_send(msg, labels, fallback):
            wanted = [label.lower() for label in labels]
            for button_row in (msg.buttons or []):
                for button in button_row:
                    button_text = (getattr(button, "text", "") or "").strip()
                    if any(label in button_text.lower() for label in wanted):
                        await msg.click(text=button_text); return True
            if fallback:
                await client.send_message(COOKIE_SELL_BOT, fallback); return True
            return False

        too_often_retry = {"count": 0, "max": 5}

        async def handler(event):
            nonlocal sold
            if sold: return
            msg  = event.message
            text = msg.text or ""
            low  = text.lower()

            # Rate limit হ্যান্ডেল
            if "too often" in low or ("please wait" in low and "report" not in low):
                import re as _re2
                nums = _re2.findall(r'\d+', text)
                wait_sec = int(nums[0]) + 2 if nums else 35
                too_often_retry["count"] += 1
                if too_often_retry["count"] <= too_often_retry["max"]:
                    step["current"] = 0
                    await asyncio.sleep(wait_sec)
                    await client.send_message(COOKIE_SELL_BOT, "/start")
                return

            if step["current"] == 0 and ("welcome" in low or "gotask pay" in low or "this bot helps" in low):
                step["current"] = 1; await asyncio.sleep(0.8)
                await click_or_send(msg, ["task", "tasks"], "📋 Tasks")
            elif step["current"] == 1 and ("which platform" in low or "platform" in low or "select" in low):
                step["current"] = 2; await asyncio.sleep(0.8)
                await click_or_send(msg, ["facebook"], "Facebook")
            elif step["current"] == 2 and ("fb cookies" in low or "facebook" in low or "cookie" in low):
                step["current"] = 3; await asyncio.sleep(0.8)
                await click_or_send(msg, ["fb cookies", "cookie"], "Fb Cookies (4 BDT)")
            elif step["current"] == 3 and ("submit uid" in low or "uid" in low):
                step["current"] = 4; await asyncio.sleep(0.8)
                await click_or_send(msg, ["submit uid", "uid"], "Submit UID 🆔")
            elif step["current"] == 4 and ("send me the uid" in low or "send uid" in low or "send your uid" in low):
                step["current"] = 5; await asyncio.sleep(0.8)
                await client.send_message(COOKIE_SELL_BOT, uid)
            elif step["current"] == 5 and ("uid received" in low or "uid" in low and "received" in low):
                step["current"] = 6; await asyncio.sleep(0.8)
                await client.send_message(COOKIE_SELL_BOT, cookie)
            elif step["current"] == 6 and ("cookies received" in low or "cookie received" in low or "received" in low):
                step["current"] = 7; await asyncio.sleep(0.8)
                await click_or_send(msg, ["complete and submit", "complete", "submit"], "Complete and Submit")
            elif step["current"] >= 6 and (
                "task submitted successfully" in low or
                "submitted successfully" in low or
                "report has been received" in low or
                "your report has been received" in low or
                "received! please wait" in low or
                ("received" in low and "wait" in low)
            ):
                step["current"] = 8; sold = True
                if target_username:
                    try:
                        await client.send_message(
                            target_username,
                            f"🎉 Cookie Task Submitted!\nUID: {uid}\nBot: {COOKIE_SELL_BOT}"
                        )
                    except Exception:
                        pass

        client.add_event_handler(handler, events.NewMessage(from_users=COOKIE_SELL_BOT))
        client.add_event_handler(handler, events.MessageEdited(from_users=COOKIE_SELL_BOT))
        await client.send_message(COOKIE_SELL_BOT, "/start")
        for _ in range(600):
            await asyncio.sleep(1)
            if sold: break
        client.remove_event_handler(handler)
        await client.disconnect()
        return sold, step["current"]

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sold, last_step = loop.run_until_complete(_sell_cookie())
        loop.close()
        if sold:
            conn2 = get_db(); cur2 = conn2.cursor()
            cur2.execute("""
                INSERT INTO sell_stats (user_id, sell_count) VALUES (%s, 1)
                ON CONFLICT (user_id) DO UPDATE SET sell_count = sell_stats.sell_count + 1
            """, (tg_user_id,))
            conn2.commit(); cur2.close(); conn2.close()
            return jsonify({"status": "success", "message": "Cookie task submitted!"})
        return jsonify({"status": "timeout", "message": f"Incomplete (step {last_step})"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/check_session", methods=["POST"])
def check_session():
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    if not tg_user_id:
        return jsonify({"status": "invalid", "message": "tg_user_id দরকার।"}), 400

    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT session_string, api_id, api_hash, target_username FROM user_sessions WHERE user_id = %s",
        (tg_user_id,)
    )
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return jsonify({"status": "invalid", "message": "Session নেই — আগে Connect করুন।"})

    session_string, api_id, api_hash, target_username = row

    async def _check():
        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        await client.connect()
        authorized = await client.is_user_authorized()
        me = None
        if authorized:
            try:
                me = await client.get_me()
            except Exception:
                pass
        await client.disconnect()
        return authorized, me

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        authorized, me = loop.run_until_complete(_check())
        loop.close()

        if authorized:
            tg_name     = ""
            tg_username = ""
            tg_id_str   = ""
            if me:
                tg_name     = (me.first_name or "") + (" " + (me.last_name or "") if me.last_name else "")
                tg_username = me.username or ""
                tg_id_str   = str(me.id)
            return jsonify({
                "status"        : "valid",
                "tg_name"       : tg_name.strip(),
                "tg_username"   : tg_username,
                "tg_id"         : tg_id_str,
                "target_username": target_username or "",
            })

        # Expired → DB থেকে সরাও
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM user_sessions WHERE user_id = %s", (tg_user_id,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"status": "invalid", "message": "Session expire হয়েছে — আবার Connect করুন।"})

    except Exception as e:
        return jsonify({"status": "invalid", "message": str(e)})


@app.route("/ping", methods=["GET", "POST"])
def ping():
    return jsonify({"status": "ok", "message": "Server is alive!"}), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "message": "Auto Server is running!"}), 200


# ══════════════════════════════════════════════════════════
#  SCHEDULED SELL — ENDPOINTS + BACKGROUND WORKER
# ══════════════════════════════════════════════════════════

def sell_log_add(tg_user_id: str, message: str):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO sell_log (tg_user_id, message, log_time) VALUES (%s, %s, %s)",
            (tg_user_id, message, int(time.time()))
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f"[SELL_LOG] DB error: {e}", flush=True)


@app.route("/upload_holds", methods=["POST"])
def upload_holds():
    """Android থেকে hold accounts upload → Server Queue তে add।"""
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    accounts   = data.get("accounts", [])
    if not tg_user_id:
        return jsonify({"status": "error", "message": "tg_user_id দরকার"}), 400
    if not accounts or not isinstance(accounts, list):
        return jsonify({"status": "error", "message": "accounts list দরকার"}), 400
    now = int(time.time())
    added = 0
    conn = get_db(); cur = conn.cursor()
    for acc in accounts:
        key    = str(acc.get("twofa_key", "")).strip()
        cookie = str(acc.get("cookie", "")).strip()
        if not key or not cookie or "c_user=" not in cookie:
            continue
        cur.execute(
            "INSERT INTO sell_queue (tg_user_id, twofa_key, cookie, status, added_at) VALUES (%s,%s,%s,'pending',%s)",
            (tg_user_id, key, cookie, now)
        )
        added += 1
    conn.commit(); cur.close(); conn.close()
    sell_log_add(tg_user_id, f"📥 Queue +{added} accounts added")
    return jsonify({"status": "success", "added": added})


@app.route("/set_schedule", methods=["POST"])
def set_schedule():
    """Schedule set — কখন sell শুরু হবে।"""
    data              = request.get_json(silent=True) or {}
    tg_user_id        = str(data.get("tg_user_id", "")).strip()
    start_time_epoch  = int(data.get("start_time_epoch", 0))
    task_off_wait_sec = int(data.get("task_off_wait_sec", 300))
    gap_seconds       = int(data.get("gap_seconds", 30))
    if not tg_user_id or start_time_epoch <= 0:
        return jsonify({"status": "error", "message": "tg_user_id ও start_time_epoch দরকার"}), 400
    now = int(time.time())
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO sell_schedule (tg_user_id, start_time_epoch, task_off_wait_sec, gap_seconds, enabled, created_at)
        VALUES (%s,%s,%s,%s,TRUE,%s)
        ON CONFLICT (tg_user_id) DO UPDATE SET
            start_time_epoch=EXCLUDED.start_time_epoch,
            task_off_wait_sec=EXCLUDED.task_off_wait_sec,
            gap_seconds=EXCLUDED.gap_seconds,
            enabled=TRUE, created_at=EXCLUDED.created_at
    """, (tg_user_id, start_time_epoch, task_off_wait_sec, gap_seconds, now))
    conn.commit(); cur.close(); conn.close()
    import datetime as _dt
    fmt = _dt.datetime.fromtimestamp(start_time_epoch).strftime("%H:%M %d/%m/%Y")
    sell_log_add(tg_user_id, f"⏰ Schedule set → Start: {fmt} | Gap: {gap_seconds}s | TaskOff: {task_off_wait_sec}s")
    return jsonify({"status": "success", "message": f"Schedule saved! Start: {fmt}"})


@app.route("/get_sell_log", methods=["POST"])
def get_sell_log():
    """Android app এ LOG দেখানোর জন্য।"""
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    after_id   = int(data.get("after_id", 0))
    if not tg_user_id:
        return jsonify({"status": "error"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT id, message, log_time FROM sell_log WHERE tg_user_id=%s AND id>%s ORDER BY id ASC LIMIT 100",
        (tg_user_id, after_id)
    )
    rows = cur.fetchall()
    cur.execute("SELECT status, COUNT(*) FROM sell_queue WHERE tg_user_id=%s GROUP BY status", (tg_user_id,))
    stats = {r[0]: r[1] for r in cur.fetchall()}
    cur.close(); conn.close()
    return jsonify({
        "status": "success",
        "logs"  : [{"id": r[0], "message": r[1], "time": r[2]} for r in rows],
        "stats" : {"pending": stats.get("pending",0), "selling": stats.get("selling",0),
                   "sold": stats.get("sold",0), "failed": stats.get("failed",0)}
    })


@app.route("/get_queue_stats", methods=["POST"])
def get_queue_stats():
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    if not tg_user_id:
        return jsonify({"status": "error"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM sell_queue WHERE tg_user_id=%s GROUP BY status", (tg_user_id,))
    stats = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT start_time_epoch, enabled, gap_seconds, task_off_wait_sec FROM sell_schedule WHERE tg_user_id=%s", (tg_user_id,))
    sched = cur.fetchone()
    cur.close(); conn.close()
    import datetime as _dt
    sched_info = {}
    if sched:
        sched_info = {
            "start_time"    : _dt.datetime.fromtimestamp(sched[0]).strftime("%H:%M %d/%m"),
            "enabled"       : sched[1],
            "gap"           : sched[2],
            "task_off_wait" : sched[3],
        }
    return jsonify({
        "status"  : "success",
        "stats"   : {"pending": stats.get("pending",0), "selling": stats.get("selling",0),
                     "sold": stats.get("sold",0), "failed": stats.get("failed",0)},
        "schedule": sched_info
    })


# ── Queue List (pending account দেখার জন্য) ──
@app.route("/get_queue_list", methods=["POST"])
def get_queue_list():
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    if not tg_user_id:
        return jsonify({"status": "error"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "SELECT id, twofa_key, cookie, status, added_at, retry_count FROM sell_queue "
        "WHERE tg_user_id=%s AND status IN ('pending','selling') ORDER BY id ASC",
        (tg_user_id,)
    )
    rows = cur.fetchall(); cur.close(); conn.close()
    items = []
    for r in rows:
        items.append({
            "id"          : r[0],
            "twofa_key"   : r[1],
            "cookie_short": (r[2] or "")[:40] + "..." if len(r[2] or "") > 40 else (r[2] or ""),
            "status"      : r[3],
            "added_at"    : r[4],
            "retry_count" : r[5],
        })
    return jsonify({"status": "success", "items": items, "total": len(items)})


# ── Queue Item Delete ──
@app.route("/delete_queue_item", methods=["POST"])
def delete_queue_item():
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    item_id    = data.get("item_id")
    if not tg_user_id or not item_id:
        return jsonify({"status": "error", "message": "Missing params"}), 400
    conn = get_db(); cur = conn.cursor()
    # শুধু এই user এর item delete করতে পারবে (security)
    cur.execute(
        "DELETE FROM sell_queue WHERE id=%s AND tg_user_id=%s",
        (item_id, tg_user_id)
    )
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if deleted > 0:
        sell_log_add(tg_user_id, f"🗑 Queue #{item_id} deleted by user")
        return jsonify({"status": "success", "message": f"#{item_id} deleted"})
    return jsonify({"status": "error", "message": "Not found"}), 404


# ── Queue Clear All Pending ──
@app.route("/clear_queue", methods=["POST"])
def clear_queue():
    data       = request.get_json(silent=True) or {}
    tg_user_id = str(data.get("tg_user_id", "")).strip()
    if not tg_user_id:
        return jsonify({"status": "error"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "DELETE FROM sell_queue WHERE tg_user_id=%s AND status='pending'",
        (tg_user_id,)
    )
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    sell_log_add(tg_user_id, f"🗑 Queue cleared — {deleted}টি pending account মুছা হয়েছে")
    return jsonify({"status": "success", "deleted": deleted})


# ── Scheduled Sell Worker ──
_scheduler_running = {}

def run_scheduled_sell_for_user(tg_user_id: str, gap_sec: int, task_off_wait: int):
    """
    একজন user এর পুরো queue শেষ করে।
    Task off → task_off_wait সেকেন্ড wait → আবার চেষ্টা (কোনো limit নেই)।
    নতুন account add হলেও সেগুলোও বিক্রি হবে।
    """
    _scheduler_running[tg_user_id] = True
    sell_log_add(tg_user_id, "🟢 Server sell শুরু হয়েছে!")

    while True:
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute(
                "SELECT id, twofa_key, cookie FROM sell_queue WHERE tg_user_id=%s AND status='pending' ORDER BY id ASC LIMIT 1",
                (tg_user_id,)
            )
            row = cur.fetchone(); cur.close(); conn.close()
        except Exception as e:
            sell_log_add(tg_user_id, f"❌ DB error: {e}"); time.sleep(10); continue

        if not row:
            # Queue খালি
            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sell_queue WHERE tg_user_id=%s AND status='sold'", (tg_user_id,))
            total_sold = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sell_queue WHERE tg_user_id=%s AND status='failed'", (tg_user_id,))
            total_fail = cur.fetchone()[0]
            cur.close(); conn.close()
            sell_log_add(tg_user_id, f"✅ সব শেষ! Sold: {total_sold} | Failed: {total_fail}")
            try:
                conn = get_db(); cur = conn.cursor()
                cur.execute("SELECT session_string, api_id, api_hash, target_username FROM user_sessions WHERE user_id=%s", (tg_user_id,))
                srow = cur.fetchone(); cur.close(); conn.close()
                if srow and srow[3]:
                    async def _notify():
                        c = TelegramClient(StringSession(srow[0]), int(srow[1]), srow[2])
                        await c.connect()
                        await c.send_message(srow[3], f"✅ AUTO SELL শেষ!\nTotal Sold: {total_sold}\nFailed: {total_fail}")
                        await c.disconnect()
                    lp = asyncio.new_event_loop(); lp.run_until_complete(_notify()); lp.close()
            except Exception:
                pass
            break

        queue_id, twofa_key, cookie = row

        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE sell_queue SET status='selling' WHERE id=%s", (queue_id,))
            conn.commit(); cur.close(); conn.close()
        except Exception:
            pass

        sell_log_add(tg_user_id, f"🚀 Selling #{queue_id}...")

        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT session_string, api_id, api_hash FROM user_sessions WHERE user_id=%s", (tg_user_id,))
            srow = cur.fetchone(); cur.close(); conn.close()
        except Exception as e:
            sell_log_add(tg_user_id, f"❌ Session DB error: {e}"); time.sleep(10); continue

        if not srow:
            sell_log_add(tg_user_id, "🔴 Session নেই! Sell বন্ধ।"); break

        session_string, api_id, api_hash = srow
        result_status = "timeout"

        try:
            async def _do_sell():
                import re as _re
                client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
                await client.connect()
                if not await client.is_user_authorized():
                    await client.disconnect(); return "session_expired"
                sold = False; task_off = False; rate_limit_secs = 0
                step = {"current": 0}; too_often = {"count": 0, "max": 5}

                async def try_click(msg, labels, fallback):
                    for brow in (msg.buttons or []):
                        for b in brow:
                            bt = (getattr(b, "text", "") or "").strip()
                            if any(l.lower() in bt.lower() for l in labels):
                                try: await msg.click(text=bt); return True
                                except: pass
                    if fallback:
                        await client.send_message(BOT, fallback); return True
                    return False

                @client.on(events.NewMessage(from_users=BOT))
                @client.on(events.MessageEdited(from_users=BOT))
                async def handler(event):
                    nonlocal sold, task_off, rate_limit_secs
                    if sold or task_off: return
                    msg = event.message; text = msg.text or ""; low = text.lower()
                    if is_task_off_message(text):
                        task_off = True; return
                    if "too often" in low or ("please wait" in low and "report" not in low):
                        nums = _re.findall(r'\d+', text)
                        wait_s = int(nums[0]) + 2 if nums else 35
                        too_often["count"] += 1
                        if too_often["count"] <= too_often["max"]:
                            step["current"] = 0; await asyncio.sleep(wait_s)
                            rate_limit_secs = wait_s; await client.send_message(BOT, "/start")
                        else:
                            rate_limit_secs = wait_s
                        return
                    if step["current"] == 0 and "welcome" in low:
                        step["current"] = 1; await asyncio.sleep(1)
                        await try_click(msg, ["tasks","task"], "📋 Tasks")
                    elif step["current"] == 1 and "please select a task" in low:
                        cb = any("🍪" in (getattr(b,"text","") or "") or "cookie" in (getattr(b,"text","") or "").lower()
                                 for brow in (msg.buttons or []) for b in brow)
                        if not cb: task_off = True; return
                        step["current"] = 2; await asyncio.sleep(1)
                        clicked = False
                        for brow in (msg.buttons or []):
                            for b in brow:
                                bt = (getattr(b,"text","") or "").strip()
                                if "🍪" in bt:
                                    try: await msg.click(text=bt); clicked = True
                                    except: pass
                                if clicked: break
                            if clicked: break
                        if not clicked: task_off = True; return
                    elif step["current"] == 2 and "🍪" in text:
                        step["current"] = 3; await asyncio.sleep(1)
                        await try_click(msg, ["2fa","create fb","no mail"], "🌟2FA:Create FB (No mail) ($0.0280)")
                    elif step["current"] == 3 and ("description" in low or "required" in low or "review time" in low):
                        step["current"] = 4; await asyncio.sleep(1)
                        await try_click(msg, ["start","▶️"], "▶️ Start")
                    elif step["current"] == 4 and ("2fa key" in low or "enter your 2fa" in low or "2fa" in low):
                        step["current"] = 5; await asyncio.sleep(1)
                        await client.send_message(BOT, twofa_key)
                    elif step["current"] == 5 and ("send the account" in low or "please send" in low or ("🍪" in text and "send" in low)):
                        step["current"] = 6; await asyncio.sleep(1.5)
                        await client.send_message(BOT, cookie)
                    elif step["current"] == 6 and ("confirm registration" in low or "press the button" in low):
                        step["current"] = 7; await asyncio.sleep(1)
                        # ReplyKeyboard বাটন — সরাসরি text message পাঠাতে হবে
                        await client.send_message(BOT, "✅ Account registered")
                    elif step["current"] >= 6 and ("report has been received" in low or "task submitted" in low or "submitted successfully" in low or ("received" in low and "wait" in low)):
                        step["current"] = 8; sold = True

                await client.send_message(BOT, "/start")
                for _ in range(180):
                    await asyncio.sleep(1)
                    if sold or task_off: break
                    if rate_limit_secs > 0 and too_often["count"] > too_often["max"]: break
                client.remove_event_handler(handler)
                await client.disconnect()
                if sold: return "success"
                if task_off: return "task_off"
                if rate_limit_secs > 0: return "rate_limit"
                return "timeout"

            lp = asyncio.new_event_loop(); asyncio.set_event_loop(lp)
            result_status = lp.run_until_complete(_do_sell()); lp.close()
        except Exception as e:
            result_status = "error"
            sell_log_add(tg_user_id, f"❌ Sell error: {e}")

        if result_status == "success":
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE sell_queue SET status='sold', sold_at=%s WHERE id=%s", (int(time.time()), queue_id))
            cur.execute("INSERT INTO sell_stats (user_id,sell_count) VALUES (%s,1) ON CONFLICT (user_id) DO UPDATE SET sell_count=sell_stats.sell_count+1", (tg_user_id,))
            conn.commit(); cur.close(); conn.close()
            sell_log_add(tg_user_id, f"✅ Sold #{queue_id}")
            time.sleep(gap_sec)

        elif result_status == "task_off":
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE sell_queue SET status='pending' WHERE id=%s", (queue_id,))
            conn.commit(); cur.close(); conn.close()
            sell_log_add(tg_user_id, f"⚠️ Task OFF — {task_off_wait}s পর আবার চেক করবে...")
            time.sleep(task_off_wait)

        elif result_status == "session_expired":
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE sell_queue SET status='pending' WHERE id=%s", (queue_id,))
            conn.commit(); cur.close(); conn.close()
            sell_log_add(tg_user_id, "🔴 Session expire! Sell বন্ধ।"); break

        else:
            # timeout/error → pending রাখো, retry limit নেই
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE sell_queue SET status='pending', retry_count=retry_count+1 WHERE id=%s", (queue_id,))
            conn.commit(); cur.close(); conn.close()
            sell_log_add(tg_user_id, f"⏳ Retry #{queue_id} — {gap_sec}s পর...")
            time.sleep(gap_sec)

    _scheduler_running.pop(tg_user_id, None)


def schedule_checker_loop():
    """প্রতি 30s এ check — schedule start হওয়ার সময় হয়েছে কিনা।"""
    print("[SCHED] Checker started", flush=True)
    while True:
        try:
            sync_all_hwid_schedules()
            now = int(time.time())
            conn = get_db(); cur = conn.cursor()
            cur.execute(
                "SELECT tg_user_id, gap_seconds, task_off_wait_sec FROM sell_schedule WHERE enabled=TRUE AND start_time_epoch<=%s",
                (now,)
            )
            due = cur.fetchall(); cur.close(); conn.close()

            for (tg_user_id, gap_sec, task_off_wait) in due:
                conn2 = get_db(); cur2 = conn2.cursor()
                cur2.execute("SELECT COUNT(*) FROM sell_queue WHERE tg_user_id=%s AND status='pending'", (tg_user_id,))
                pending = cur2.fetchone()[0]; cur2.close(); conn2.close()
                if pending == 0:
                    conn3 = get_db(); cur3 = conn3.cursor()
                    cur3.execute("UPDATE sell_schedule SET enabled=FALSE WHERE tg_user_id=%s", (tg_user_id,))
                    conn3.commit(); cur3.close(); conn3.close()
                    continue
                if _scheduler_running.get(tg_user_id):
                    continue
                threading.Thread(
                    target=run_scheduled_sell_for_user,
                    args=(tg_user_id, gap_sec, task_off_wait),
                    daemon=True
                ).start()
                conn4 = get_db(); cur4 = conn4.cursor()
                cur4.execute("UPDATE sell_schedule SET enabled=FALSE WHERE tg_user_id=%s", (tg_user_id,))
                conn4.commit(); cur4.close(); conn4.close()

        except Exception as e:
            print(f"[SCHED] Checker error: {e}", flush=True)
        time.sleep(30)

# ══════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════
#  SECURE API PROXY (ALL API KEYS STAY ON SERVER ONLY)
# ══════════════════════════════════════════════════════════

_PROXY_CACHE = {
    "p1_otp": {"ts": 0, "data": []},
    "p2_otp": {"ts": 0, "data": []},
    "p4_rng": {"ts": 0, "ranges": []},
    "p4_nums": {},
    "p4_msg": {"ts": 0, "records": [], "cooldown_until": 0},
    "p4_num_cooldown": 0,
    "p4_last_num_req": 0,
}
_PROXY_LOCKS = {
    "p1_otp": threading.Lock(),
    "p2_otp": threading.Lock(),
    "p4_rng": threading.Lock(),
    "p4_num": threading.Lock(),
    "p4_msg": threading.Lock(),
}

_PREFIX_COUNTRY_MAP = {
    "1": ("US", "USA / CANADA"), "7": ("RU", "RUSSIA"), "20": ("EG", "EGYPT"),
    "27": ("ZA", "SOUTH AFRICA"), "30": ("GR", "GREECE"), "31": ("NL", "NETHERLANDS"),
    "32": ("BE", "BELGIUM"), "33": ("FR", "FRANCE"), "34": ("ES", "SPAIN"),
    "36": ("HU", "HUNGARY"), "39": ("IT", "ITALY"), "40": ("RO", "ROMANIA"),
    "41": ("CH", "SWITZERLAND"), "43": ("AT", "AUSTRIA"), "44": ("GB", "UNITED KINGDOM"),
    "45": ("DK", "DENMARK"), "46": ("SE", "SWEDEN"), "47": ("NO", "NORWAY"),
    "48": ("PL", "POLAND"), "49": ("DE", "GERMANY"), "51": ("PE", "PERU"),
    "52": ("MX", "MEXICO"), "53": ("CU", "CUBA"), "54": ("AR", "ARGENTINA"),
    "55": ("BR", "BRAZIL"), "56": ("CL", "CHILE"), "57": ("CO", "COLOMBIA"),
    "58": ("VE", "VENEZUELA"), "60": ("MY", "MALAYSIA"), "61": ("AU", "AUSTRALIA"),
    "62": ("ID", "INDONESIA"), "63": ("PH", "PHILIPPINES"), "64": ("NZ", "NEW ZEALAND"),
    "65": ("SG", "SINGAPORE"), "66": ("TH", "THAILAND"), "81": ("JP", "JAPAN"),
    "82": ("KR", "SOUTH KOREA"), "84": ("VN", "VIETNAM"), "86": ("CN", "CHINA"),
    "90": ("TR", "TURKEY"), "91": ("IN", "INDIA"), "92": ("PK", "PAKISTAN"),
    "93": ("AF", "AFGHANISTAN"), "94": ("LK", "SRI LANKA"), "95": ("MM", "MYANMAR"),
    "98": ("IR", "IRAN"), "212": ("MA", "MOROCCO"), "213": ("DZ", "ALGERIA"),
    "216": ("TN", "TUNISIA"), "218": ("LY", "LIBYA"), "220": ("GM", "GAMBIA"),
    "221": ("SN", "SENEGAL"), "223": ("ML", "MALI"), "224": ("GN", "GUINEA"),
    "225": ("CI", "IVORY COAST"), "226": ("BF", "BURKINA FASO"), "227": ("NE", "NIGER"),
    "228": ("TG", "TOGO"), "229": ("BJ", "BENIN"), "231": ("LR", "LIBERIA"),
    "232": ("SL", "SIERRA LEONE"), "233": ("GH", "GHANA"), "234": ("NG", "NIGERIA"),
    "235": ("TD", "CHAD"), "237": ("CM", "CAMEROON"), "240": ("GQ", "EQUATORIAL GUINEA"),
    "241": ("GA", "GABON"), "242": ("CG", "CONGO"), "243": ("CD", "DR CONGO"),
    "244": ("AO", "ANGOLA"), "249": ("SD", "SUDAN"), "250": ("RW", "RWANDA"),
    "251": ("ET", "ETHIOPIA"), "252": ("SO", "SOMALIA"), "253": ("DJ", "DJIBOUTI"),
    "254": ("KE", "KENYA"), "255": ("TZ", "TANZANIA"), "256": ("UG", "UGANDA"),
    "257": ("BI", "BURUNDI"), "258": ("MZ", "MOZAMBIQUE"), "260": ("ZM", "ZAMBIA"),
    "261": ("MG", "MADAGASCAR"), "263": ("ZW", "ZIMBABWE"), "264": ("NA", "NAMIBIA"),
    "265": ("MW", "MALAWI"), "266": ("LS", "LESOTHO"), "267": ("BW", "BOTSWANA"),
    "351": ("PT", "PORTUGAL"), "353": ("IE", "IRELAND"), "355": ("AL", "ALBANIA"),
    "358": ("FI", "FINLAND"), "359": ("BG", "BULGARIA"), "370": ("LT", "LITHUANIA"),
    "371": ("LV", "LATVIA"), "372": ("EE", "ESTONIA"), "373": ("MD", "MOLDOVA"),
    "374": ("AM", "ARMENIA"), "375": ("BY", "BELARUS"), "380": ("UA", "UKRAINE"),
    "381": ("RS", "SERBIA"), "385": ("HR", "CROATIA"), "420": ("CZ", "CZECH REPUBLIC"),
    "421": ("SK", "SLOVAKIA"), "855": ("KH", "CAMBODIA"), "856": ("LA", "LAOS"),
    "880": ("BD", "BANGLADESH"), "886": ("TW", "TAIWAN"), "961": ("LB", "LEBANON"),
    "962": ("JO", "JORDAN"), "963": ("SY", "SYRIA"), "964": ("IQ", "IRAQ"),
    "965": ("KW", "KUWAIT"), "966": ("SA", "SAUDI ARABIA"), "967": ("YE", "YEMEN"),
    "968": ("OM", "OMAN"), "971": ("AE", "UAE"), "972": ("IL", "ISRAEL"),
    "973": ("BH", "BAHRAIN"), "974": ("QA", "QATAR"), "977": ("NP", "NEPAL"),
    "992": ("TJ", "TAJIKISTAN"), "993": ("TM", "TURKMENISTAN"), "994": ("AZ", "AZERBAIJAN"),
    "995": ("GE", "GEORGIA"), "996": ("KG", "KYRGYZSTAN"), "998": ("UZ", "UZBEKISTAN"),
}

def _iso_flag(iso: str) -> str:
    if not iso or len(iso) != 2:
        return "🌍"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso.upper())

def _country_from_prefix(prefix: str, fallback: str = "GLOBAL"):
    clean = re.sub(r"\D", "", str(prefix or ""))
    for l in (3, 2, 1):
        if len(clean) >= l and clean[:l] in _PREFIX_COUNTRY_MAP:
            iso, name = _PREFIX_COUNTRY_MAP[clean[:l]]
            return _iso_flag(iso), name
    fb = fallback.strip().upper() if fallback and fallback.strip() else "GLOBAL"
    return "🌍", fb

def _extract_otp_code(text: str) -> str:
    t = str(text or "")
    m6 = re.search(r"\b(\d{6})\b", t)
    if m6: return m6.group(1)
    m5 = re.search(r"\b(\d{5})\b", t)
    if m5: return m5.group(1)
    mf = re.search(r"\b(\d{4,8})\b", t)
    return mf.group(1) if mf else ""

def _p4_get_ranges():
    now = time.time()
    with _PROXY_LOCKS["p4_rng"]:
        if _PROXY_CACHE["p4_rng"]["ranges"] and (now - _PROXY_CACHE["p4_rng"]["ts"] < 45):
            return _PROXY_CACHE["p4_rng"]["ranges"]
        res = []
        if LAMIX_API_KEY:
            try:
                r = _requests.get(
                    f"{LAMIX_BASE_URL}/api/v1/ranges",
                    headers={"Authorization": f"Bearer {LAMIX_API_KEY}"},
                    timeout=15
                )
                if r.status_code == 200:
                    res = r.json().get("ranges", []) or []
            except Exception as e:
                print(f"[P4 RANGES ERR] {e}", flush=True)
        if res:
            _PROXY_CACHE["p4_rng"] = {"ts": time.time(), "ranges": res}
        return _PROXY_CACHE["p4_rng"]["ranges"] or res

@app.route("/proxy/ranges", methods=["POST"])
def proxy_ranges():
    d = request.get_json(silent=True) or {}
    ok, msg = verify_proxy_auth(d)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 403
    panel = int(d.get("panel", 1))

    if panel == 1:
        if not ZENEX_API_KEY:
            return jsonify({"ok": False, "error": "ZENEX_API_KEY not configured on server"})
        try:
            r = _requests.get("https://api.zenexnetwork.com/v1/active-ranges",
                              headers={"mapikey": ZENEX_API_KEY}, timeout=15)
            ar = (r.json().get("data") or {}).get("active_ranges", []) or []
            fb = [x for x in ar if "FACEBOOK" in str(x.get("service", "")).upper()]
            fb.sort(key=lambda x: int(x.get("hits", 0) or 0), reverse=True)
            out = [f"{x['range']}  ({x.get('hits', 0)} hits)" for x in fb[:15]]
            raw = [x["range"] for x in fb[:15]]
            return jsonify({"ok": True, "ranges": out, "raw": raw})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    if panel == 2:
        if not PANEL2_API_KEY:
            return jsonify({"ok": False, "error": "PANEL2_API_KEY not configured on server"})
        try:
            r = _requests.get(f"{PANEL2_BASE_URL}/liveaccess",
                              headers={"mauthapi": PANEL2_API_KEY}, timeout=15)
            svcs = (r.json().get("data") or {}).get("services", []) or []
            ranges = []
            for s in svcs:
                if str(s.get("sid", "")).upper() == "FACEBOOK":
                    ranges = s.get("ranges", []) or []
                    break
            return jsonify({"ok": True, "ranges": ranges})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    if panel == 3:
        if not PANEL3_API_KEY:
            return jsonify({"ok": False, "error": "PANEL3_API_KEY not configured on server"})
        cc = str(d.get("country_code", "")).strip()
        try:
            if cc:
                r = _requests.get(f"{PANEL3_BASE_URL}/api/v1/developer/available-tags",
                                  params={"countryCode": cc},
                                  headers={"X-API-KEY": PANEL3_API_KEY}, timeout=15)
                tags = [x.get("tag", "") for x in (r.json().get("data") or []) if x.get("tag")]
                return jsonify({"ok": True, "tags": tags})
            r = _requests.get(f"{PANEL3_BASE_URL}/api/v1/developer/available-countries",
                              params={"service": "any"},
                              headers={"X-API-KEY": PANEL3_API_KEY}, timeout=15)
            seen = set(); countries = []
            for c in (r.json().get("data") or []):
                code = c.get("countryCode", "")
                if not code or code in seen: continue
                seen.add(code)
                countries.append({
                    "country": c.get("country", ""),
                    "countryCode": code,
                    "flag": c.get("flag", "🌍"),
                    "prefix": c.get("prefix", ""),
                    "rateUsd": c.get("rateUsd", "?"),
                    "tag": c.get("tag", ""),
                })
            return jsonify({"ok": True, "countries": countries})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    if panel == 4:
        if not LAMIX_API_KEY:
            return jsonify({"ok": False, "error": "LAMIX_API_KEY not configured on server"})
        ranges = _p4_get_ranges()
        grouped = {}
        for r in ranges:
            if not r.get("active", True) or int(r.get("numbers", 0) or 0) <= 0:
                continue
            rid = str(r.get("id", "")).strip()
            if not rid: continue
            flag, cname = _country_from_prefix(r.get("prefix", ""), r.get("name", ""))
            if cname not in grouped:
                grouped[cname] = {"flag": flag, "name": cname, "range_ids": []}
            grouped[cname]["range_ids"].append(rid)

        if not grouped:
            try:
                r = _requests.get(f"{LAMIX_BASE_URL}/api/v1/numbers",
                                  params={"limit": 500},
                                  headers={"Authorization": f"Bearer {LAMIX_API_KEY}"}, timeout=15)
                if r.status_code == 200:
                    for rec in (r.json().get("records") or []):
                        num = str(rec.get("number", "")).strip()
                        rid = str(rec.get("rangeId", "")).strip()
                        if not num: continue
                        flag, cname = _country_from_prefix(num, rec.get("range", ""))
                        if cname not in grouped:
                            grouped[cname] = {"flag": flag, "name": cname, "range_ids": []}
                        if rid and rid not in grouped[cname]["range_ids"]:
                            grouped[cname]["range_ids"].append(rid)
            except Exception as e:
                print(f"[P4 FALLBACK ERR] {e}", flush=True)
        return jsonify({"ok": True, "countries": list(grouped.values())})

    return jsonify({"ok": False, "error": "Invalid panel"}), 400


@app.route("/proxy/getnum", methods=["POST"])
def proxy_getnum():
    d = request.get_json(silent=True) or {}
    ok, msg = verify_proxy_auth(d)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 403
    panel  = int(d.get("panel", 1))
    prefix = str(d.get("prefix", "")).strip()

    if panel == 1:
        if not ZENEX_API_KEY:
            return jsonify({"ok": False, "error": "ZENEX_API_KEY not configured"})
        try:
            rng = prefix
            if not rng:
                r0 = _requests.get("https://api.zenexnetwork.com/v1/active-ranges",
                                   headers={"mapikey": ZENEX_API_KEY}, timeout=15)
                ar = (r0.json().get("data") or {}).get("active_ranges", []) or []
                fb = [x for x in ar if "FACEBOOK" in str(x.get("service", "")).upper()]
                fb.sort(key=lambda x: int(x.get("hits", 0) or 0), reverse=True)
                rng = fb[0]["range"] if fb else "237626XXX"
            r1 = _requests.post("https://api.zenexnetwork.com/v1/getnum",
                                headers={"mapikey": ZENEX_API_KEY, "Content-Type": "application/json"},
                                json={"range": rng, "is_national": False, "remove_plus": False},
                                timeout=15)
            num = ((r1.json().get("data") or {}).get("full_number") or "").replace("+", "").strip()
            return jsonify({"ok": bool(num), "number": num, "range": rng})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    if panel == 2:
        if not PANEL2_API_KEY:
            return jsonify({"ok": False, "error": "PANEL2_API_KEY not configured"})
        try:
            r0 = _requests.get(f"{PANEL2_BASE_URL}/liveaccess",
                               headers={"mauthapi": PANEL2_API_KEY}, timeout=15)
            svcs = (r0.json().get("data") or {}).get("services", []) or []
            chosen = ""
            for s in svcs:
                if str(s.get("sid", "")).upper() == "FACEBOOK":
                    ranges = s.get("ranges", []) or []
                    if ranges:
                        if prefix:
                            pfx = re.sub(r"[xX]+$", "", prefix)
                            for rr in ranges:
                                if rr.startswith(pfx):
                                    chosen = rr; break
                        if not chosen:
                            chosen = ranges[0]
                    break
            if not chosen:
                return jsonify({"ok": False, "error": "No FB range on Panel 2"})
            r1 = _requests.post(f"{PANEL2_BASE_URL}/getnum",
                                headers={"mauthapi": PANEL2_API_KEY, "Content-Type": "application/json"},
                                json={"range": chosen}, timeout=15)
            gd = r1.json().get("data") or {}
            num = (gd.get("no_plus_number") or gd.get("full_number", "")).replace("+", "").strip()
            nid = str(gd.get("otp_id") or gd.get("id") or gd.get("num_id") or "")
            return jsonify({"ok": bool(num), "number": num, "num_id": nid, "range": chosen})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    if panel == 3:
        if not PANEL3_API_KEY:
            return jsonify({"ok": False, "error": "PANEL3_API_KEY not configured"})
        try:
            cc  = str(d.get("country_code", "ET")).strip() or "ET"
            tag = str(d.get("tag", "")).strip()
            if prefix and not d.get("country_code"):
                r0 = _requests.get(f"{PANEL3_BASE_URL}/api/v1/developer/available-countries",
                                   params={"service": "any"},
                                   headers={"X-API-KEY": PANEL3_API_KEY}, timeout=15)
                for c in (r0.json().get("data") or []):
                    if prefix == c.get("tag") or prefix.startswith(str(c.get("prefix", "") or "__")):
                        cc = c.get("countryCode", cc); break
                if "SLVN" in prefix or "-" in prefix:
                    tag = prefix
            payload = {"service": "Facebook", "countryCode": cc}
            if tag:
                payload["tag"] = tag
            r1 = _requests.post(f"{PANEL3_BASE_URL}/api/v1/developer/rent",
                                headers={"X-API-KEY": PANEL3_API_KEY, "Content-Type": "application/json"},
                                json=payload, timeout=15)
            gd = r1.json().get("data") or {}
            num = str(gd.get("phoneNumber", "")).replace("+", "").replace(" ", "").strip()
            rid = str(gd.get("rentalId", "")).strip()
            return jsonify({"ok": bool(num), "number": num, "rental_id": rid})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    if panel == 4:
        if not LAMIX_API_KEY:
            return jsonify({"ok": False, "error": "LAMIX_API_KEY not configured"})
        range_ids = d.get("range_ids") or []
        exclude   = set(str(x) for x in (d.get("exclude_numbers") or []))
        with _PROXY_LOCKS["p4_num"]:
            if not range_ids:
                all_r = _p4_get_ranges()
                if prefix.startswith("P4:"):
                    target_c = prefix[3:]
                    for rr in all_r:
                        if not rr.get("active", True) or int(rr.get("numbers", 0) or 0) <= 0:
                            continue
                        _, cname = _country_from_prefix(rr.get("prefix", ""), rr.get("name", ""))
                        if cname == target_c:
                            range_ids.append(str(rr.get("id", "")))
                if not range_ids:
                    range_ids = [str(rr.get("id", "")) for rr in all_r if rr.get("active", True) and int(rr.get("numbers", 0) or 0) > 0]
            if not range_ids:
                range_ids = [""]

            for rid in range_ids:
                now = time.time()
                centry = _PROXY_CACHE["p4_nums"].get(rid)
                pool = centry["numbers"] if (centry and now - centry["ts"] < 120) else []
                avail = [n for n in pool if n not in exclude]
                if not avail and now >= _PROXY_CACHE["p4_num_cooldown"]:
                    diff = now - _PROXY_CACHE["p4_last_num_req"]
                    if diff < 1.1:
                        time.sleep(1.1 - diff)
                    _PROXY_CACHE["p4_last_num_req"] = time.time()
                    try:
                        params = {"limit": 500}
                        if rid: params["rangeId"] = rid
                        nxt = centry.get("next_cursor") if centry else ""
                        if nxt: params["after"] = nxt
                        r = _requests.get(f"{LAMIX_BASE_URL}/api/v1/numbers",
                                          params=params,
                                          headers={"Authorization": f"Bearer {LAMIX_API_KEY}"}, timeout=15)
                        if r.status_code == 429:
                            ra = int(float(r.headers.get("Retry-After") or 10))
                            _PROXY_CACHE["p4_num_cooldown"] = time.time() + max(5, ra)
                        elif r.status_code == 200:
                            jd = r.json()
                            recs = jd.get("records") or []
                            recs.sort(key=lambda x: bool(x.get("client")))
                            new_pool = []
                            for rec in recs:
                                cn = re.sub(r"\D", "", str(rec.get("number", "")))
                                if cn and cn not in new_pool:
                                    new_pool.append(cn)
                            _PROXY_CACHE["p4_nums"][rid] = {
                                "ts": time.time(),
                                "numbers": new_pool,
                                "next_cursor": jd.get("nextCursor") or ""
                            }
                            pool = new_pool
                            avail = [n for n in pool if n not in exclude]
                    except Exception as e:
                        print(f"[P4 GETNUM ERR] {e}", flush=True)
                picked = avail[0] if avail else (random.choice(pool) if pool else "")
                if picked:
                    return jsonify({"ok": True, "number": picked})
        return jsonify({"ok": False, "error": "No number available on Lamix"})

    return jsonify({"ok": False, "error": "Invalid panel"}), 400


@app.route("/proxy/check_otp", methods=["POST"])
def proxy_check_otp():
    d = request.get_json(silent=True) or {}
    ok, msg = verify_proxy_auth(d)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 403
    panel  = int(d.get("panel", 1))
    number = re.sub(r"\D", "", str(d.get("number", "")))
    ref_id = str(d.get("ref_id", "")).strip()
    if not number and not ref_id:
        return jsonify({"ok": True, "otp": ""})

    if panel == 1:
        if not ZENEX_API_KEY: return jsonify({"ok": True, "otp": ""})
        with _PROXY_LOCKS["p1_otp"]:
            now = time.time()
            if now - _PROXY_CACHE["p1_otp"]["ts"] > 2.0:
                try:
                    r = _requests.get("https://api.zenexnetwork.com/v1/numsuccess/info",
                                      headers={"mapikey": ZENEX_API_KEY}, timeout=10)
                    if r.status_code == 200:
                        _PROXY_CACHE["p1_otp"] = {"ts": time.time(), "data": (r.json().get("data") or {}).get("otps", []) or []}
                except Exception:
                    pass
            recs = _PROXY_CACHE["p1_otp"]["data"]
        for item in recs:
            anum = re.sub(r"\D", "", str(item.get("number", "")))
            if anum == number:
                otp = _extract_otp_code(item.get("otp", ""))
                if otp:
                    return jsonify({"ok": True, "otp": otp})
        return jsonify({"ok": True, "otp": ""})

    if panel == 2:
        if not PANEL2_API_KEY: return jsonify({"ok": True, "otp": ""})
        with _PROXY_LOCKS["p2_otp"]:
            now = time.time()
            if now - _PROXY_CACHE["p2_otp"]["ts"] > 2.0:
                try:
                    r = _requests.get(f"{PANEL2_BASE_URL}/success-otp",
                                      headers={"mauthapi": PANEL2_API_KEY}, timeout=10)
                    if r.status_code == 200:
                        _PROXY_CACHE["p2_otp"] = {"ts": time.time(), "data": (r.json().get("data") or {}).get("otps", []) or []}
                except Exception:
                    pass
            recs = _PROXY_CACHE["p2_otp"]["data"]
        for item in recs:
            anum = re.sub(r"\D", "", str(item.get("number", "")))
            oid  = str(item.get("otp_id", ""))
            txt  = str(item.get("message", ""))
            if (anum and anum == number) or (ref_id and oid == ref_id) or (len(number) >= 8 and number in re.sub(r"\D", "", txt)):
                otp = _extract_otp_code(txt)
                if otp:
                    return jsonify({"ok": True, "otp": otp})
        return jsonify({"ok": True, "otp": ""})

    if panel == 3:
        if not PANEL3_API_KEY or not ref_id: return jsonify({"ok": True, "otp": ""})
        try:
            r = _requests.get(f"{PANEL3_BASE_URL}/api/v1/developer/check-otp/{ref_id}",
                              headers={"X-API-KEY": PANEL3_API_KEY}, timeout=10)
            if r.status_code == 200:
                gd = r.json().get("data") or {}
                if str(gd.get("status", "")).upper() in ("RECEIVED", "SUCCESS"):
                    code = str(gd.get("otpCode", "")).strip()
                    if code:
                        return jsonify({"ok": True, "otp": code})
                    msgs = gd.get("messages") or []
                    if msgs:
                        otp = _extract_otp_code(msgs[-1].get("fullSms", ""))
                        if otp:
                            return jsonify({"ok": True, "otp": otp})
        except Exception:
            pass
        return jsonify({"ok": True, "otp": ""})

    if panel == 4:
        if not LAMIX_API_KEY: return jsonify({"ok": True, "otp": ""})
        with _PROXY_LOCKS["p4_msg"]:
            now = time.time()
            if now >= _PROXY_CACHE["p4_msg"]["cooldown_until"] and (now - _PROXY_CACHE["p4_msg"]["ts"] >= 9.0):
                try:
                    since_iso = (datetime.datetime.utcnow() - datetime.timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    r = _requests.get(f"{LAMIX_BASE_URL}/api/v1/messages",
                                      params={"from": since_iso, "limit": 100},
                                      headers={"Authorization": f"Bearer {LAMIX_API_KEY}"}, timeout=12)
                    if r.status_code == 429:
                        ra = int(float(r.headers.get("Retry-After") or 12))
                        _PROXY_CACHE["p4_msg"]["cooldown_until"] = time.time() + max(10, ra)
                    elif r.status_code == 200:
                        _PROXY_CACHE["p4_msg"]["records"] = r.json().get("records") or []
                    _PROXY_CACHE["p4_msg"]["ts"] = time.time()
                except Exception as e:
                    print(f"[P4 OTP ERR] {e}", flush=True)
            recs = _PROXY_CACHE["p4_msg"]["records"]
        for rec in recs:
            rnum = re.sub(r"\D", "", str(rec.get("number", "")))
            if rnum == number:
                otp = _extract_otp_code(rec.get("content", ""))
                if otp:
                    return jsonify({"ok": True, "otp": otp})
        return jsonify({"ok": True, "otp": ""})

    return jsonify({"ok": True, "otp": ""})


@app.route("/proxy/send_otp_tg", methods=["POST"])
def proxy_send_otp_tg():
    d = request.get_json(silent=True) or {}
    ok, msg = verify_proxy_auth(d)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 403
    if not DEFAULT_BOT_TOKEN or not DEFAULT_CHAT_ID:
        return jsonify({"ok": False, "error": "Bot not configured on server"})

    number = re.sub(r"\D", "", str(d.get("number", "")))
    otp    = str(d.get("otp", "")).strip()
    panel  = int(d.get("panel", 1))
    if not number or not otp:
        return jsonify({"ok": False, "error": "Missing number or otp"}), 400

    filtered_num = f"{number[:4]}<b>SUPER</b>{number[-3:]}" if len(number) >= 10 else number
    p_label = {1: "ZENEX", 2: "SUPER 2", 3: "SL VIRTUAL", 4: "LAMIX"}.get(panel, "SUPER")
    dt_str = datetime.datetime.now(BD_TZ).strftime("%Y-%m-%d %H:%M:%S")

    text = (
        f"🔔 <b>NEW OTP</b>\n\n"
        f"📱 {filtered_num}\n"
        f"🌐 FACEBOOK\n"
        f"🔑 {esc(otp)}\n"
        f"⚙️ {p_label}\n"
        f"🕒 {dt_str}"
    )
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "🔴 NUMBER", "url": "https://t.me/SUPER_WORKERS", "style": "danger"},
                {"text": "🟢 MAIN",   "url": "https://t.me/SUPERWORKERSBACKUP", "style": "success"},
            ],
            [
                {"text": "🔵 DEV",    "url": "https://t.me/NEXEX_99", "style": "primary"},
            ],
        ]
    }
    try:
        r = _requests.post(
            f"https://api.telegram.org/bot{DEFAULT_BOT_TOKEN}/sendMessage",
            json={"chat_id": DEFAULT_CHAT_ID, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup},
            timeout=15
        )
        return jsonify({"ok": r.status_code == 200})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


_started = False
def start_bg():
    global _started
    if _started: return
    _started = True
    if LICENSE_BOT_TOKEN: threading.Thread(target=run_license_bot, daemon=True).start()
    threading.Thread(target=schedule_checker_loop, daemon=True).start()
start_bg()
if __name__ == "__main__":
    # License Bot thread
    bot_thread = threading.Thread(target=run_license_bot, daemon=True)
    bot_thread.start()

    # Schedule checker thread
    sched_thread = threading.Thread(target=schedule_checker_loop, daemon=True)
    sched_thread.start()

    # Flask server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

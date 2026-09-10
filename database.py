"""
Database Management Module (Dual-Sync: Supabase Cloud + Local Cache Fallback)
Compatible with Python 3.11 (Windows / Linux / Android)
Bulletproof: Zero-Downtime Local Cache + Direct PostgREST Cloud Sync
"""

import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Tuple
import config

REST_URL: str = f"{config.SUPABASE_URL.rstrip('/')}/rest/v1"
LOCAL_BACKUP_FILE: str = "local_storage.json"

HEADERS: Dict[str, str] = {
    "apikey": config.SUPABASE_KEY,
    "Authorization": f"Bearer {config.SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation,resolution=merge-duplicates"
}


# --- LOCAL BACKUP STORAGE HELPERS ---

def _load_local_cache() -> Dict[str, Any]:
    """Loads backup cache from local disk to guarantee 100% uptime."""
    if not os.path.exists(LOCAL_BACKUP_FILE):
        default_data = {
            "accounts": {},
            "channels": {},
            "sub_bots": {},
            "allowed_reactions": config.DEFAULT_REACTIONS,
            "min_delay": config.MIN_DELAY,
            "max_delay": config.MAX_DELAY
        }
        _save_local_cache(default_data)
        return default_data
    try:
        with open(LOCAL_BACKUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"accounts": {}, "channels": {}, "sub_bots": {}, "allowed_reactions": config.DEFAULT_REACTIONS, "min_delay": config.MIN_DELAY, "max_delay": config.MAX_DELAY}


def _save_local_cache(data: Dict[str, Any]) -> None:
    """Safely saves local backup cache to disk."""
    try:
        with open(LOCAL_BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Local Cache Warning] {e}")


# --- SUPABASE HTTP REST ENGINE ---

def _make_request(endpoint: str, method: str = "GET", payload: Any = None) -> Any:
    """Executes direct HTTP REST request to Supabase Cloud API with safe error handling."""
    url = f"{REST_URL}/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    
    req = urllib.request.Request(url=url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            res_body = response.read().decode("utf-8")
            return json.loads(res_body) if res_body else []
    except urllib.error.HTTPError as e:
        return []
    except Exception:
        return []


def init_db() -> None:
    """Initializes local cache and syncs cloud settings."""
    _load_local_cache()
    try:
        res = _make_request("bot_settings?key=eq.allowed_reactions&select=value")
        if not res:
            _make_request("bot_settings", method="POST", payload={
                "key": "allowed_reactions",
                "value": config.DEFAULT_REACTIONS
            })
    except Exception:
        pass


# --- ACCOUNTS MANAGEMENT (DUAL-SYNC) ---

def save_account(phone: str, session_string: str, first_name: str = "", user_id: int = 0) -> bool:
    """Saves user account to BOTH Local Backup Cache and Supabase Cloud."""
    clean_phone = str(phone).strip()
    
    # 1. Save to Local Backup First (Instant Guarantee)
    cache = _load_local_cache()
    cache["accounts"][clean_phone] = {
        "session_string": session_string,
        "first_name": first_name,
        "user_id": user_id,
        "is_active": 1
    }
    _save_local_cache(cache)

    # 2. Sync to Supabase Cloud
    payload = {
        "phone": clean_phone,
        "session_string": session_string,
        "first_name": first_name,
        "user_id": user_id,
        "is_active": 1
    }
    _make_request("accounts?on_conflict=phone", method="POST", payload=payload)
    return True


def add_session(session_str: str) -> bool:
    """Fallback helper to add session string."""
    dummy_phone = f"user_{abs(hash(session_str)) % (10**10)}"
    return save_account(phone=dummy_phone, session_string=session_str)


def get_all_sessions() -> List[str]:
    """
    Fetches all active session strings by merging Supabase Cloud + Local Cache.
    Guarantees accounts will NEVER be 0 if imported.
    """
    sessions_set = set()

    # 1. Fetch from Local Cache
    cache = _load_local_cache()
    for acc in cache.get("accounts", {}).values():
        if isinstance(acc, dict) and acc.get("session_string"):
            sessions_set.add(acc["session_string"])

    # 2. Fetch from Supabase Cloud
    res = _make_request("accounts?select=*")
    if isinstance(res, list):
        for row in res:
            if isinstance(row, dict) and row.get("session_string"):
                # Also backfill local cache if missing
                s_str = row["session_string"]
                phone = str(row.get("phone", f"user_{abs(hash(s_str)) % (10**10)}"))
                if phone not in cache["accounts"]:
                    cache["accounts"][phone] = {
                        "session_string": s_str,
                        "first_name": row.get("first_name", ""),
                        "user_id": row.get("user_id", 0),
                        "is_active": row.get("is_active", 1)
                    }
                sessions_set.add(s_str)
        _save_local_cache(cache)

    return list(sessions_set)


# --- CHANNELS MANAGEMENT (DUAL-SYNC) ---

def add_channel(channel_id: str, title: str, link: str | None = None) -> bool:
    """Upserts a channel into Local Cache and Supabase Cloud."""
    ch_id = str(channel_id).strip()
    
    # Local Save
    cache = _load_local_cache()
    cache["channels"][ch_id] = {"title": title, "link": link or ""}
    _save_local_cache(cache)

    # Cloud Save
    payload = {"channel_id": ch_id, "title": title, "link": link or ""}
    _make_request("channels?on_conflict=channel_id", method="POST", payload=payload)
    return True


def remove_channel(channel_id: str) -> bool:
    """Deletes channel from Local Cache and Supabase Cloud."""
    ch_id = str(channel_id).strip()
    
    cache = _load_local_cache()
    if ch_id in cache.get("channels", {}):
        del cache["channels"][ch_id]
        _save_local_cache(cache)

    _make_request(f"channels?channel_id=eq.{ch_id}", method="DELETE")
    return True


def get_monitored_channels() -> Dict[str, Dict[str, Any]]:
    """Returns all registered channels merging Supabase Cloud + Local Cache."""
    cache = _load_local_cache()
    channels_dict = dict(cache.get("channels", {}))

    res = _make_request("channels?select=*")
    if isinstance(res, list):
        for row in res:
            if isinstance(row, dict) and "channel_id" in row:
                ch_id = str(row.get("channel_id"))
                channels_dict[ch_id] = {
                    "title": row.get("title", "Channel"),
                    "link": row.get("link", "")
                }
                cache["channels"][ch_id] = channels_dict[ch_id]
        _save_local_cache(cache)

    return channels_dict


# --- SUB-BOT TOKENS MANAGEMENT ---

def add_bot_token(token: str, username: str = "") -> bool:
    """Saves sub-bot token to Local Cache and Supabase Cloud."""
    clean_token = token.strip()
    
    cache = _load_local_cache()
    cache["sub_bots"][clean_token] = username.replace("@", "")
    _save_local_cache(cache)

    payload = {"token": clean_token, "username": username.replace("@", "")}
    _make_request("sub_bots?on_conflict=token", method="POST", payload=payload)
    return True


def get_all_bot_tokens() -> List[str]:
    """Fetches all sub-bot tokens merging Supabase Cloud + Local Cache."""
    cache = _load_local_cache()
    tokens_set = set(cache.get("sub_bots", {}).keys())

    res = _make_request("sub_bots?select=*")
    if isinstance(res, list):
        for row in res:
            if isinstance(row, dict) and "token" in row:
                t = str(row.get("token"))
                tokens_set.add(t)
                cache["sub_bots"][t] = row.get("username", "")
        _save_local_cache(cache)

    return list(tokens_set)


# --- REACTIONS & DELAY SETTINGS ---

def get_reactions() -> List[str]:
    cache = _load_local_cache()
    return cache.get("allowed_reactions", config.DEFAULT_REACTIONS)


def set_reactions(reactions_list: List[str]) -> bool:
    cache = _load_local_cache()
    cache["allowed_reactions"] = reactions_list
    _save_local_cache(cache)

    payload = {"key": "allowed_reactions", "value": reactions_list}
    _make_request("bot_settings?on_conflict=key", method="POST", payload=payload)
    return True


def get_delay_settings() -> Tuple[float, float]:
    cache = _load_local_cache()
    return (
        float(cache.get("min_delay", config.MIN_DELAY)),
        float(cache.get("max_delay", config.MAX_DELAY))
    )


def set_delay_settings(min_d: float, max_d: float) -> bool:
    cache = _load_local_cache()
    cache["min_delay"] = min_d
    cache["max_delay"] = max_d
    _save_local_cache(cache)

    payload = {
        "key": "delay_settings",
        "value": {"min_delay": min_d, "max_delay": max_d}
    }
    _make_request("bot_settings?on_conflict=key", method="POST", payload=payload)
    return True


def get_db() -> Dict[str, Any]:
    """Dashboard compatibility helper."""
    min_d, max_d = get_delay_settings()
    return {
        "channels": get_monitored_channels(),
        "sessions": get_all_sessions(),
        "bot_tokens": get_all_bot_tokens(),
        "allowed_reactions": get_reactions(),
        "min_delay": min_d,
        "max_delay": max_d
    }

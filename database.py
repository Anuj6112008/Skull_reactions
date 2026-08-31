"""
Database Management Module
Compatible with Python 3.11
"""

import json
import os
from typing import Any, Dict, List
import config

DB_PATH: str = config.DATABASE_FILE


def init_db() -> None:
    """Initializes the JSON database file if it doesn't already exist."""
    if not os.path.exists(DB_PATH):
        default_data: Dict[str, Any] = {
            "channels": {},       # Format: {"-100123456": {"title": "My Channel", "link": "https://t.me/..."}}
            "sessions": [],       # List of Pyrogram MTProto session strings
            "bot_tokens": [],     # List of Sub-Bot tokens
            "allowed_reactions": config.DEFAULT_REACTIONS,
            "min_delay": config.MIN_DELAY,
            "max_delay": config.MAX_DELAY
        }
        save_db(default_data)


def get_db() -> Dict[str, Any]:
    """Reads and returns the complete database dictionary."""
    init_db()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        init_db()
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def save_db(data: Dict[str, Any]) -> None:
    """Writes the updated dictionary data safely back to the JSON file."""
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# --- Channel Management ---

def add_channel(channel_id: str, title: str, link: str | None = None) -> None:
    """Adds or updates a monitored channel in the database."""
    db = get_db()
    db["channels"][str(channel_id)] = {
        "title": title,
        "link": link
    }
    save_db(db)


def remove_channel(channel_id: str) -> bool:
    """Removes a channel from the database."""
    db = get_db()
    if str(channel_id) in db["channels"]:
        del db["channels"][str(channel_id)]
        save_db(db)
        return True
    return False


def get_monitored_channels() -> Dict[str, Dict[str, Any]]:
    """Returns all registered channels."""
    return get_db().get("channels", {})


# --- User Session Management ---

def add_session(session_str: str) -> bool:
    """Adds a new Pyrogram user session string."""
    db = get_db()
    if session_str not in db["sessions"]:
        db["sessions"].append(session_str)
        save_db(db)
        return True
    return False


def get_all_sessions() -> List[str]:
    """Returns all saved active user session strings."""
    return get_db().get("sessions", [])


# --- Sub-Bot Tokens Management ---

def add_bot_token(token: str) -> bool:
    """Adds a secondary bot token."""
    db = get_db()
    if token not in db["bot_tokens"]:
        db["bot_tokens"].append(token)
        save_db(db)
        return True
    return False


def get_all_bot_tokens() -> List[str]:
    """Returns all secondary bot tokens."""
    return get_db().get("bot_tokens", [])


# --- Reactions & Delays ---

def get_reactions() -> List[str]:
    """Returns list of allowed emojis for auto-reaction."""
    return get_db().get("allowed_reactions", config.DEFAULT_REACTIONS)


def set_reactions(reactions_list: List[str]) -> None:
    """Updates allowed emojis list."""
    db = get_db()
    db["allowed_reactions"] = reactions_list
    save_db(db)


def get_delay_settings() -> tuple[float, float]:
    """Returns minimum and maximum delay in seconds."""
    db = get_db()
    return (
        float(db.get("min_delay", config.MIN_DELAY)),
        float(db.get("max_delay", config.MAX_DELAY))
    )
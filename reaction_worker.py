"""
Automated Reaction Worker & Multi-Account Dispatcher
Compatible with Python 3.11
Fixed: Direct Telegram Bot API HTTP Engine for Sub-Bots (Zero Peer Issues)
"""

import asyncio
import json
import random
import urllib.request
import urllib.error
from pyrogram import Client
from pyrogram.errors import (
    FloodWait, 
    ReactionInvalid, 
    UserNotParticipant, 
    PeerIdInvalid
)

import config
import database as db


async def resolve_and_get_chat(client: Client, chat_id: int, channel_link: str = None):
    """Resolves and caches channel peer for User Accounts."""
    try:
        return await client.get_chat(chat_id)
    except (PeerIdInvalid, Exception):
        if channel_link:
            try:
                return await client.get_chat(channel_link)
            except Exception:
                pass
        return None


async def send_reaction_from_user(
    session_string: str, 
    chat_id: int, 
    message_id: int, 
    emoji: str,
    channel_link: str = None
) -> bool:
    """Connects an alt user account (MTProto) and applies the reaction."""
    user_client = Client(
        name=f"react_usr_{random.randint(1000, 9999)}",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=session_string,
        in_memory=True
    )
    
    try:
        await user_client.connect()
        await resolve_and_get_chat(user_client, chat_id, channel_link)
        
        await user_client.send_reaction(
            chat_id=chat_id,
            message_id=message_id,
            emoji=emoji
        )
        await user_client.disconnect()
        print(f"✅ [User Reaction] Sent {emoji} on post {message_id}")
        return True
    except FloodWait as e:
        try:
            await user_client.disconnect()
        except Exception:
            pass
        print(f"⚠️ [User Reaction FloodWait] Waiting {e.value}s")
        return False
    except (ReactionInvalid, UserNotParticipant) as err:
        try:
            await user_client.disconnect()
        except Exception:
            pass
        print(f"⚠️ [User Reaction Skipped] {err}")
        return False
    except Exception as err:
        try:
            await user_client.disconnect()
        except Exception:
            pass
        print(f"❌ [User Reaction Error] {err}")
        return False


def _send_bot_api_reaction_sync(bot_token: str, chat_id: int, message_id: int, emoji: str) -> bool:
    """
    Executes standard Telegram Bot API setMessageReaction method.
    Accepts raw -100 numeric chat IDs directly with zero peer cache errors.
    """
    url = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": emoji}],
        "is_big": False
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("ok", False)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"❌ [Sub-Bot API Error] HTTP {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"❌ [Sub-Bot Request Error] {e}")
        return False


async def send_reaction_from_bot(
    bot_token: str, 
    chat_id: int, 
    message_id: int, 
    emoji: str
) -> bool:
    """Non-blocking async wrapper for Bot API reaction dispatch."""
    success = await asyncio.to_thread(
        _send_bot_api_reaction_sync, 
        bot_token, 
        chat_id, 
        message_id, 
        emoji
    )
    if success:
        print(f"✅ [Sub-Bot Reaction] Sent {emoji} on post {message_id}")
    return success


async def dispatch_safe_reactions(chat_id: int, message_id: int) -> None:
    """
    Dispatches randomized reactions across all User Accounts
    and Sub-Bots with human anti-freeze delays.
    """
    database_data = db.get_db()
    sessions = database_data.get("sessions", [])
    bot_tokens = database_data.get("bot_tokens", [])
    allowed_emojis = database_data.get("allowed_reactions", config.DEFAULT_REACTIONS)
    min_delay, max_delay = db.get_delay_settings()

    channel_info = database_data.get("channels", {}).get(str(chat_id), {})
    channel_link = channel_info.get("link")

    target_chat_id = int(chat_id)

    # 1. Dispatch User Accounts Reactions (MTProto)
    if sessions:
        user_list = list(sessions)
        random.shuffle(user_list)

        for session_str in user_list:
            chosen_emoji = random.choice(allowed_emojis)
            await send_reaction_from_user(
                session_string=session_str,
                chat_id=target_chat_id,
                message_id=message_id,
                emoji=chosen_emoji,
                channel_link=channel_link
            )
            await asyncio.sleep(random.uniform(min_delay, max_delay))

    # 2. Dispatch Sub-Bots Reactions (Direct Bot API)
    if bot_tokens:
        tokens_list = list(bot_tokens)
        random.shuffle(tokens_list)

        for token in tokens_list:
            chosen_emoji = random.choice(allowed_emojis)
            await send_reaction_from_bot(
                bot_token=token,
                chat_id=target_chat_id,
                message_id=message_id,
                emoji=chosen_emoji
            )
            await asyncio.sleep(random.uniform(min_delay, max_delay))
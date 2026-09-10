"""
Channel Management, Multi-Account Auto-Join & Universal Full Sync Engine
Compatible with Python 3.11 (Windows / Linux / Android)
Fixed: Fast HTTP Bot Username Resolver & Bulletproof Dual Bot Promotion
"""

import asyncio
import json
import random
import ssl
import urllib.request
from typing import Tuple
from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message, ChatPrivileges
from pyrogram.errors import (
    UserAlreadyParticipant, 
    InviteHashExpired, 
    FloodWait, 
    ChatAdminRequired,
    PeerIdInvalid
)

import config
import database as db
from ui_animations import run_bot_progress

# Universal SSL Context for Telegram Bot API requests
SSL_CTX = ssl._create_unverified_context()


def get_bot_username_http(token: str) -> str | None:
    """
    Instantly fetches sub-bot username via Telegram HTTP API in 0.05 seconds.
    Zero Pyrogram client overhead & bypasses SSL inspection issues.
    """
    url = f"https://api.telegram.org/bot{token}/getMe"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data["result"].get("username")
    except Exception as e:
        print(f"[Bot HTTP getMe Error] {e}")
    return None


async def resolve_peer_safely(client: Client, chat_id: int, channel_link: str = None):
    """Ensures channel peer is resolved and cached in client memory."""
    try:
        return await client.get_chat(chat_id)
    except (PeerIdInvalid, Exception):
        if channel_link:
            try:
                return await client.get_chat(channel_link)
            except Exception:
                pass
        return None


async def find_admin_account(sessions: list[str], chat_id: int, channel_link: str = None) -> tuple[Client, str] | tuple[None, None]:
    """Scans logged-in Alt Accounts to find which one has Admin rights in this channel."""
    for idx, s in enumerate(sessions, start=1):
        client = Client(
            name=f"admin_scan_{random.randint(100, 999)}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=s,
            in_memory=True
        )
        try:
            await client.connect()
            await resolve_peer_safely(client, chat_id, channel_link)
            member = await client.get_chat_member(chat_id, "me")
            
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                print(f"[Admin Found] Alt Account #{idx} has Admin Rights in channel {chat_id}!")
                return client, s
            
            await client.disconnect()
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass

    return None, None


async def add_single_bot_to_channel(
    admin_client: Client, 
    chat_id: int, 
    bot_username: str, 
    channel_link: str = None
) -> bool:
    """Promotes a sub-bot as Administrator in the channel using the Admin Alt account."""
    clean_bot_user = bot_username.replace("@", "")
    try:
        await resolve_peer_safely(admin_client, chat_id, channel_link)
        bot_obj = await admin_client.get_users(clean_bot_user)

        # 1. Try Promoting Bot as Admin
        await admin_client.promote_chat_member(
            chat_id=chat_id,
            user_id=bot_obj.id,
            privileges=ChatPrivileges(
                can_manage_chat=True,
                can_post_messages=True,
                can_edit_messages=True
            )
        )
        print(f"[Bot Auto-Added] Promoted @{clean_bot_user} as Admin in channel {chat_id}")
        return True
    except UserAlreadyParticipant:
        print(f"[Bot Present] @{clean_bot_user} is already in channel {chat_id}")
        return True
    except ChatAdminRequired:
        # 2. If promote fails, try adding as regular member
        try:
            bot_obj = await admin_client.get_users(clean_bot_user)
            await admin_client.add_chat_members(chat_id, bot_obj.id)
            print(f"[Bot Member Added] Added @{clean_bot_user} to channel {chat_id}")
            return True
        except Exception as e:
            print(f"[Bot Add Error] Alt account needs 'Add New Admins' rights to add @{clean_bot_user}: {e}")
            return False
    except Exception as e:
        print(f"[Bot Add Error] @{clean_bot_user}: {e}")
        return False


async def add_and_sync_channel(
    main_bot: Client, 
    channel_input: str, 
    status_message: Message
) -> Tuple[bool, str]:
    """Handles adding a single channel and initial syncing of alts & bots."""
    clean_input = channel_input.strip()
    sessions = db.get_all_sessions()
    sub_bots = db.get_all_bot_tokens()
    
    channel_id = None
    channel_title = "Monitored Channel"
    resolved_via_user = False

    # 1. Resolve Channel
    if "t.me/+" in clean_input or "joinchat" in clean_input:
        if not sessions:
            return False, "User Account Required! Please add at least 1 Alt Account first."
        
        temp_client = Client(f"resolver_{random.randint(100, 999)}", api_id=config.API_ID, api_hash=config.API_HASH, session_string=sessions[0], in_memory=True)
        try:
            await temp_client.connect()
            chat_obj = await temp_client.join_chat(clean_input)
            channel_id = str(chat_obj.id)
            channel_title = chat_obj.title or "Private Channel"
            await temp_client.disconnect()
            resolved_via_user = True
        except UserAlreadyParticipant:
            try:
                chat_obj = await temp_client.get_chat(clean_input)
                channel_id = str(chat_obj.id)
                channel_title = chat_obj.title or "Private Channel"
                await temp_client.disconnect()
                resolved_via_user = True
            except Exception:
                await temp_client.disconnect()
        except Exception as e:
            await temp_client.disconnect()
            return False, f"Failed to resolve private link: {str(e)}"

    if not resolved_via_user:
        try:
            chat_target = int(clean_input) if clean_input.replace("-", "").isdigit() else clean_input
            chat = await main_bot.get_chat(chat_target)
            channel_id = str(chat.id)
            channel_title = chat.title or clean_input
        except Exception as err:
            return False, f"Could not access channel: {err}"

    db.add_channel(channel_id, channel_title, clean_input)

    # 2. Auto-Join Alt Accounts
    total_accounts = len(sessions)
    joined_accounts = 0

    if sessions:
        await status_message.edit_text(f"Syncing Step 1/2: Joining {total_accounts} Alt Accounts to {channel_title}...")

        for index, session_string in enumerate(sessions, start=1):
            if resolved_via_user and index == 1:
                joined_accounts += 1
                continue

            joiner = Client(f"joiner_{random.randint(1000, 9999)}", api_id=config.API_ID, api_hash=config.API_HASH, session_string=session_string, in_memory=True)
            try:
                await joiner.connect()
                target = clean_input if ("t.me/+" in clean_input or "joinchat" in clean_input) else int(channel_id)
                await joiner.join_chat(target)
                await joiner.disconnect()
                joined_accounts += 1
            except UserAlreadyParticipant:
                try:
                    await joiner.disconnect()
                except Exception:
                    pass
                joined_accounts += 1
            except Exception as e:
                try:
                    await joiner.disconnect()
                except Exception:
                    pass
                print(f"[Join Warning] Account #{index}: {e}")

            await run_bot_progress(status_message, f"Step 1: Joining Accounts", index, total_accounts)
            await asyncio.sleep(random.uniform(1.5, 3.0))

    # 3. Auto-Add Sub-Bots via Admin Alt Account
    added_bots = 0
    total_bots = len(sub_bots)

    if sub_bots and sessions:
        await status_message.edit_text(f"Syncing Step 2/2: Auto-Adding Sub-Bots to channel...")

        admin_client, _ = await find_admin_account(sessions, int(channel_id), clean_input)

        if admin_client:
            for b_idx, token in enumerate(sub_bots, start=1):
                bot_username = get_bot_username_http(token)
                if bot_username:
                    res = await add_single_bot_to_channel(admin_client, int(channel_id), bot_username, clean_input)
                    if res:
                        added_bots += 1

                await run_bot_progress(status_message, "Step 2: Auto-Adding Sub-Bots", b_idx, total_bots)
                await asyncio.sleep(random.uniform(1.5, 3.0))

            await admin_client.disconnect()

    return True, (
        f"Channel Sync Complete!\n\n"
        f"• Channel: {channel_title} ({channel_id})\n"
        f"• Alt Accounts Joined: {joined_accounts}/{total_accounts}\n"
        f"• Sub-Bots Auto-Added: {added_bots}/{total_bots}\n\n"
        f"Ready for automated engagement."
    )


async def sync_all_channels_and_members(status_message: Message) -> Tuple[int, int, int]:
    """
    UNIVERSAL MASTER FULL SYNC:
    1. Iterates over all registered channels and auto-joins missing Alt Accounts.
    2. Uses Admin Alt Account to auto-promote missing Sub-Bots.
    """
    sessions = db.get_all_sessions()
    sub_bots = db.get_all_bot_tokens()
    channels = db.get_monitored_channels()

    if not channels:
        return 0, 0, 0

    total_channels = len(channels)
    total_alts_joined = 0
    total_bots_promoted = 0

    total_steps = total_channels * (len(sessions) + len(sub_bots)) if (sessions or sub_bots) else 1
    current_step = 0

    for ch_id, ch_info in channels.items():
        target_chat_id = int(ch_id)
        ch_link = ch_info.get("link")
        join_target = ch_link if (ch_link and ("t.me/+" in ch_link or "joinchat" in ch_link)) else target_chat_id

        # 1. Join missing alt accounts
        for acc_idx, session_str in enumerate(sessions, start=1):
            joiner = Client(f"sync_j_{random.randint(100,999)}", api_id=config.API_ID, api_hash=config.API_HASH, session_string=session_str, in_memory=True)
            try:
                await joiner.connect()
                await joiner.join_chat(join_target)
                await joiner.disconnect()
                total_alts_joined += 1
            except UserAlreadyParticipant:
                try:
                    await joiner.disconnect()
                except Exception:
                    pass
                total_alts_joined += 1
            except Exception as e:
                try:
                    await joiner.disconnect()
                except Exception:
                    pass
                print(f"[Sync Join Warning] Account #{acc_idx} in channel {ch_id}: {e}")

            current_step += 1
            await run_bot_progress(status_message, "Universal Sync: Accounts & Bots", current_step, total_steps)
            await asyncio.sleep(random.uniform(1.2, 2.5))

        # 2. Promote missing sub-bots
        if sub_bots and sessions:
            admin_client, _ = await find_admin_account(sessions, target_chat_id, ch_link)
            if admin_client:
                for token in sub_bots:
                    bot_username = get_bot_username_http(token)
                    if bot_username:
                        res = await add_single_bot_to_channel(admin_client, target_chat_id, bot_username, ch_link)
                        if res:
                            total_bots_promoted += 1

                    current_step += 1
                    await run_bot_progress(status_message, "Universal Sync: Accounts & Bots", current_step, total_steps)
                    await asyncio.sleep(random.uniform(1.2, 2.5))

                await admin_client.disconnect()
            else:
                current_step += len(sub_bots)
                print(f"[Admin Notice] Alt account is not an Admin in channel {target_chat_id}. Make at least 1 Alt account an admin in channel settings.")

    return total_channels, total_alts_joined, total_bots_promoted

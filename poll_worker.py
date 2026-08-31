"""
Channel Poll Monitor & Bulk Voting Engine
Compatible with Python 3.11
Fixed: Peer ID Resolution Cache for Bulk Voting
"""

import asyncio
import random
from typing import Tuple
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserNotParticipant, PeerIdInvalid

import config
import database as db
from ui_animations import run_bot_progress


async def resolve_voting_chat(client: Client, chat_id: int, channel_link: str = None):
    """
    Ensures the channel peer is cached in memory before voting.
    """
    try:
        return await client.get_chat(chat_id)
    except (PeerIdInvalid, Exception):
        if channel_link:
            try:
                return await client.get_chat(channel_link)
            except Exception:
                pass
        return None


async def notify_admin_about_poll(main_bot: Client, message: Message) -> None:
    """
    Alerts all registered Admins in private DM with interactive option buttons.
    """
    poll = message.poll
    if not poll:
        return

    channel_title = message.chat.title or "Monitored Channel"
    question_text = poll.question
    
    buttons = []
    for idx, option in enumerate(poll.options):
        btn_text = f"🗳 Option {idx + 1}: {option.text}"
        callback_payload = f"pv_{message.chat.id}_{message.id}_{idx}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_payload)])

    buttons.append([InlineKeyboardButton("❌ Dismiss Poll", callback_data="btn_refresh")])
    markup = InlineKeyboardMarkup(buttons)

    text = (
        "╔═════════════════════════════════╗\n"
        "   📊 **NEW CHANNEL POLL DETECTED** \n"
        "╚═════════════════════════════════╝\n\n"
        f"🎯 **Target Channel:** `{channel_title}`\n"
        f"❓ **Question:** `{question_text}`\n"
        f"🔢 **Total Options:** `{len(poll.options)}`\n\n"
        "👇 _Tap an option below to cast bulk votes from all alt accounts:_"
    )

    for admin_id in config.ADMIN_IDS:
        try:
            await main_bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=markup
            )
        except Exception as err:
            print(f"[Admin Notify Error] {err}")


async def execute_bulk_poll_votes(
    status_message: Message,
    chat_id: int,
    message_id: int,
    option_index: int
) -> Tuple[int, int]:
    """
    Executes bulk poll voting with Peer caching and safe delays.
    """
    database_data = db.get_db()
    sessions = database_data.get("sessions", [])
    total_accounts = len(sessions)
    
    if total_accounts == 0:
        return 0, 0

    # Get stored channel link if available
    channel_info = database_data.get("channels", {}).get(str(chat_id), {})
    channel_link = channel_info.get("link")

    success_votes = 0
    min_delay, max_delay = db.get_delay_settings()
    target_chat_id = int(chat_id)

    shuffled_sessions = list(sessions)
    random.shuffle(shuffled_sessions)

    for current_idx, session_str in enumerate(shuffled_sessions, start=1):
        user_client = Client(
            name=f"voter_{random.randint(1000, 9999)}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=session_str,
            in_memory=True
        )

        try:
            await user_client.connect()

            # 1. Resolve & Cache Peer first
            await resolve_voting_chat(user_client, target_chat_id, channel_link)

            # 2. Cast Vote
            await user_client.vote_poll(
                chat_id=target_chat_id,
                message_id=message_id,
                options=[option_index]
            )
            await user_client.disconnect()
            success_votes += 1
            print(f"✅ [Poll Vote] Account #{current_idx} voted on option {option_index + 1}")
        except UserNotParticipant:
            try:
                # If not member, join and vote
                target = channel_link if channel_link else target_chat_id
                await user_client.join_chat(target)
                await user_client.vote_poll(
                    chat_id=target_chat_id,
                    message_id=message_id,
                    options=[option_index]
                )
                await user_client.disconnect()
                success_votes += 1
                print(f"✅ [Poll Vote] Account #{current_idx} joined & voted!")
            except Exception as e:
                try:
                    await user_client.disconnect()
                except Exception:
                    pass
                print(f"❌ [Vote Join Error] Account #{current_idx}: {e}")
        except FloodWait as e:
            try:
                await user_client.disconnect()
            except Exception:
                pass
            print(f"⚠️ [Vote FloodWait] Waiting {e.value}s")
            await asyncio.sleep(e.value)
        except Exception as err:
            try:
                await user_client.disconnect()
            except Exception:
                pass
            print(f"❌ [Vote Error] Account #{current_idx}: {err}")

        # Update Live Progress Bar in Telegram Chat
        await run_bot_progress(
            message=status_message,
            action_title=f"Broadcasting Votes (Option {option_index + 1})",
            current=current_idx,
            total=total_accounts
        )

        # Anti-flood safe delay
        await asyncio.sleep(random.uniform(min_delay, max_delay))

    return success_votes, total_accounts
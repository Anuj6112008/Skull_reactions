"""
Bulk Session Importer & Validator Engine
Compatible with Python 3.11
Features: .txt File Parser, Direct Text Parser, Account Verification & Direct Supabase Sync
"""

import asyncio
import random
from typing import List, Tuple
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import (
    AuthKeyUnregistered,
    UserDeactivated,
    SessionRevoked,
    FloodWait
)

import config
import database as db
from ui_animations import run_bot_progress


def parse_sessions_from_raw_text(raw_text: str) -> List[str]:
    """
    Extracts, trims, and filters Pyrogram session strings from any raw text or .txt file content.
    """
    lines = raw_text.strip().splitlines()
    valid_sessions = []
    
    for line in lines:
        cleaned = line.strip()
        # Filter out empty lines, comments, or short invalid strings
        if cleaned and not cleaned.startswith("#") and len(cleaned) > 40:
            valid_sessions.append(cleaned)
            
    return valid_sessions


async def verify_and_save_session(session_str: str) -> Tuple[bool, str]:
    """
    Connects to Telegram using the session string, extracts user details,
    and saves them directly into Supabase accounts table.
    """
    temp_client = Client(
        name=f"verify_{random.randint(10000, 99999)}",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=session_str,
        in_memory=True
    )
    
    try:
        await temp_client.connect()
        me = await temp_client.get_me()
        
        phone_num = str(me.phone_number or f"+{me.id}")
        first_name = me.first_name or "Telegram User"
        user_id = int(me.id)
        
        await temp_client.disconnect()
        
        # Save directly into Supabase Cloud
        db.save_account(
            phone=phone_num,
            session_string=session_str,
            first_name=first_name,
            user_id=user_id
        )
        print(f"✅ [Supabase Synced] Account: {first_name} ({phone_num})")
        return True, f"Account: {first_name} ({phone_num})"
        
    except (AuthKeyUnregistered, UserDeactivated, SessionRevoked):
        try:
            await temp_client.disconnect()
        except Exception:
            pass
        return False, "Session revoked / expired on Telegram"
        
    except FloodWait as e:
        try:
            await temp_client.disconnect()
        except Exception:
            pass
        await asyncio.sleep(e.value)
        return False, f"FloodWait {e.value}s"
        
    except Exception as e:
        try:
            await temp_client.disconnect()
        except Exception:
            pass
        return False, str(e)


async def process_bulk_sessions_import(
    status_message: Message, 
    session_list: List[str]
) -> Tuple[int, int, int]:
    """
    Iterates over all parsed sessions, verifies each, updates the live in-chat progress,
    and saves verified accounts to Supabase.
    """
    total_found = len(session_list)
    if total_found == 0:
        return 0, 0, 0

    valid_count = 0
    invalid_count = 0

    for idx, session_str in enumerate(session_list, start=1):
        is_valid, _ = await verify_and_save_session(session_str)
        
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1

        # Live dynamic Telegram UI Progress Bar
        await run_bot_progress(
            message=status_message,
            action_title="Importing & Syncing Sessions to Supabase",
            current=idx,
            total=total_found
        )
        
        # Safe delay between account logins to avoid rate limits
        await asyncio.sleep(random.uniform(1.2, 2.5))

    return total_found, valid_count, invalid_count

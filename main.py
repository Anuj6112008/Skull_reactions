"""
Main Telegram Bot Controller & Dashboard Engine
Compatible with Python 3.11 (PyDroid 3 / Linux / Windows)
UI: Ultra-Clean Single Emoji Corporate Design + 1-Click Universal Auto-Sync
"""

import asyncio
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from pyrogram.errors import MessageNotModified, QueryIdInvalid

import config
import database as db
from ui_animations import run_bot_spinner
from auth_handler import auth_system
from channel_manager import add_and_sync_channel, sync_all_channels_and_members
from reaction_worker import dispatch_safe_reactions
from poll_worker import notify_admin_about_poll, execute_bulk_poll_votes

# Initialize Main Controller Bot
app = Client(
    name="controller_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

admin_input_states: Dict[int, Dict[str, Any]] = {}


# --- ACCESS CONTROL FILTER ---

def is_authorized_admin(_, __, message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in config.ADMIN_IDS)

admin_only = filters.create(is_authorized_admin)


# --- DASHBOARD GENERATOR (CLEAN SINGLE EMOJI) ---

def build_admin_dashboard() -> tuple[str, InlineKeyboardMarkup]:
    data = db.get_db()
    channels = data.get("channels", {})
    sessions = data.get("sessions", [])
    sub_bots = data.get("bot_tokens", [])
    reactions = data.get("allowed_reactions", config.DEFAULT_REACTIONS)
    min_d = data.get("min_delay", config.MIN_DELAY)
    max_d = data.get("max_delay", config.MAX_DELAY)

    dashboard_text = (
        "╔═════════════════════════════════╗\n"
        "   🚀 **ENGAGEMENT MASTER PANEL** \n"
        "╚═════════════════════════════════╝\n\n"
        f"🟢 **Engine Status:** `ONLINE & ACTIVE`\n"
        f"👤 **Linked User Accounts:** `{len(sessions)} accounts`\n"
        f"🤖 **Linked Sub-Bots:** `{len(sub_bots)} bots`\n"
        f"📢 **Monitored Channels:** `{len(channels)} channels`\n"
        f"🛡 **Anti-Flood Delays:** `{min_d}s - {max_d}s`\n"
        f"🎭 **Active Reactions:** {' '.join(reactions[:7])}\n\n"
        "👇 _Select an option below to manage engine:_"
    )

    # Clean Single-Emoji Button Layout
    buttons = [
        [
            InlineKeyboardButton("➕ Add Channel", callback_data="btn_add_channel"),
            InlineKeyboardButton("📢 Monitored Channels", callback_data="btn_view_channels")
        ],
        [
            InlineKeyboardButton("👤 Add Alt Account", callback_data="btn_add_account"),
            InlineKeyboardButton("🤖 Add Sub-Bot", callback_data="btn_add_bot")
        ],
        [
            InlineKeyboardButton("⚡ Full Auto-Sync (Alts + Bots)", callback_data="btn_full_sync")
        ],
        [
            InlineKeyboardButton("🎭 Reaction Settings", callback_data="btn_set_reactions"),
            InlineKeyboardButton("⚙️ Delay Settings", callback_data="btn_adjust_delays")
        ],
        [
            InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="btn_refresh")
        ]
    ]

    return dashboard_text, InlineKeyboardMarkup(buttons)


# --- SAFE UI HELPERS ---

async def safe_edit_text(target: Message | CallbackQuery, text: str, reply_markup=None):
    try:
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=reply_markup)
        else:
            await target.edit_text(text, reply_markup=reply_markup)
    except MessageNotModified:
        pass
    except Exception as e:
        print(f"[UI Edit Warning] {e}")


async def safe_answer_query(query: CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        if text:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
    except (QueryIdInvalid, Exception):
        pass


# --- START COMMAND ---

@app.on_message(filters.command("start") & filters.private & admin_only)
async def handle_start_cmd(client: Client, message: Message) -> None:
    status_msg = await message.reply_text("⚡ `Booting Engagement Panel...`")
    await run_bot_spinner(status_msg, "Loading Dashboard...", duration_sec=1.0)
    
    text, markup = build_admin_dashboard()
    await safe_edit_text(status_msg, text, reply_markup=markup)


# --- CALLBACK QUERY ROUTER ---

@app.on_callback_query(admin_only)
async def handle_callback_router(client: Client, query: CallbackQuery) -> None:
    action = query.data
    user_id = query.from_user.id

    await safe_answer_query(query)

    if action == "btn_refresh":
        text, markup = build_admin_dashboard()
        await safe_edit_text(query, text, reply_markup=markup)

    # ONE-CLICK MASTER FULL SYNC
    elif action == "btn_full_sync":
        await safe_answer_query(query, "Starting Full Sync across all channels...", show_alert=False)
        status_msg = await query.message.reply_text("⚡ `Starting Universal Auto-Sync (Accounts + Bots)...`")
        
        channels_count, alts_count, bots_count = await sync_all_channels_and_members(status_msg)
        
        await safe_edit_text(
            status_msg,
            f"✅ **Universal Auto-Sync Completed!**\n\n"
            f"• **Channels Synced:** `{channels_count}` channels\n"
            f"• **Alt Accounts Joined:** `{alts_count}` successful joins\n"
            f"• **Sub-Bots Promoted:** `{bots_count}` bot promotions\n\n"
            f"🛡 _All accounts & bots are fully synchronized!_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="btn_refresh")]])
        )

    elif action == "btn_add_channel":
        admin_input_states[user_id] = {"step": "WAITING_CHANNEL_INPUT"}
        await safe_edit_text(
            query,
            "📢 **Add Monitored Channel**\n\n"
            "Send one of the following:\n"
            "1. **Public Channel:** `@channel_username`\n"
            "2. **Private Channel:** `https://t.me/+xxxxxx` (Invite link)\n"
            "3. **Channel ID:** `-1001234567890`\n\n"
            "⚠️ **Important:** Add this main bot as Admin in the channel!\n\n"
            "Type /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_refresh")]])
        )

    elif action == "btn_view_channels":
        channels = db.get_monitored_channels()
        buttons = []

        if not channels:
            msg_text = "📢 **Monitored Channels**\n\n_No channels added yet._"
        else:
            msg_text = "📢 **Active Monitored Channels:**\n\n"
            for ch_id, ch_data in channels.items():
                title = ch_data.get("title", "Channel")
                msg_text += f"• **{title}** (`{ch_id}`)\n"
                buttons.append([InlineKeyboardButton(f"❌ Remove: {title[:20]}", callback_data=f"delch_{ch_id}")])

        buttons.append([InlineKeyboardButton("➕ Add Another Channel", callback_data="btn_add_channel")])
        buttons.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="btn_refresh")])

        await safe_edit_text(query, msg_text, reply_markup=InlineKeyboardMarkup(buttons))

    elif action.startswith("delch_"):
        target_ch_id = action.replace("delch_", "")
        db.remove_channel(target_ch_id)
        await safe_answer_query(query, "Channel removed successfully!", show_alert=True)
        
        channels = db.get_monitored_channels()
        buttons = []
        msg_text = "📢 **Active Monitored Channels:**\n\n"
        if not channels:
            msg_text = "📢 **Monitored Channels**\n\n_No channels added yet._"
        else:
            for ch_id, ch_data in channels.items():
                title = ch_data.get("title", "Channel")
                msg_text += f"• **{title}** (`{ch_id}`)\n"
                buttons.append([InlineKeyboardButton(f"❌ Remove: {title[:20]}", callback_data=f"delch_{ch_id}")])

        buttons.append([InlineKeyboardButton("➕ Add Another Channel", callback_data="btn_add_channel")])
        buttons.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="btn_refresh")])

        await safe_edit_text(query, msg_text, reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "btn_add_account":
        admin_input_states[user_id] = {"step": "WAITING_PHONE_NUMBER"}
        await safe_edit_text(
            query,
            "👤 **Add Telegram User Account (Alt)**\n\n"
            "Send phone number with country code:\n"
            "**Example:** `+919876543210`\n\n"
            "Type /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_refresh")]])
        )

    elif action == "btn_add_bot":
        admin_input_states[user_id] = {"step": "WAITING_BOT_TOKEN"}
        await safe_edit_text(
            query,
            "🤖 **Add Sub-Bot Token**\n\n"
            "Paste the Bot Token created via @BotFather:\n\n"
            "Type /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_refresh")]])
        )

    elif action == "btn_set_reactions":
        admin_input_states[user_id] = {"step": "WAITING_REACTIONS_LIST"}
        current = " ".join(db.get_reactions())
        await safe_edit_text(
            query,
            f"🎭 **Configure Positive Reactions**\n\n"
            f"**Current Emojis:** {current}\n\n"
            "Send the new emojis separated by spaces.\n"
            "**Example:** `👍 🔥 ❤️ 🥰 🎉 🤩 ⚡️ 👏`\n\n"
            "Type /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_refresh")]])
        )

    elif action == "btn_adjust_delays":
        admin_input_states[user_id] = {"step": "WAITING_DELAYS"}
        min_d, max_d = db.get_delay_settings()
        await safe_edit_text(
            query,
            f"⚙️ **Adjust Anti-Flood Safe Delays**\n\n"
            f"**Current Delays:** `{min_d}s to {max_d}s`\n\n"
            "Send minimum and maximum seconds separated by space.\n"
            "**Example:** `1.5 2.5`\n\n"
            "Type /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_refresh")]])
        )

    # --- POLL VOTING TRIGGER ---
    elif action.startswith("pv_"):
        parts = action.split("_")
        target_chat_id = int(parts[1])
        target_msg_id = int(parts[2])
        chosen_opt_idx = int(parts[3])

        status_msg = await query.message.reply_text("⚡ `Preparing voting workers...`")

        success, total = await execute_bulk_poll_votes(
            status_message=status_msg,
            chat_id=target_chat_id,
            message_id=target_msg_id,
            option_index=chosen_opt_idx
        )

        await safe_edit_text(
            status_msg,
            f"✅ **Bulk Voting Finished!**\n\n"
            f"• **Option Selected:** `Option {chosen_opt_idx + 1}`\n"
            f"• **Successful Votes:** `{success}/{total}` accounts\n"
            f"• **Protection:** `Completed safely without freezes` 🛡",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="btn_refresh")]])
        )


# --- TEXT & INPUT STATE HANDLER ---

@app.on_message(filters.text & filters.private & admin_only)
async def handle_text_inputs(client: Client, message: Message) -> None:
    user_id = message.from_user.id
    input_text = message.text.strip()

    if input_text == "/cancel":
        admin_input_states.pop(user_id, None)
        await auth_system.cleanup(user_id)
        text, markup = build_admin_dashboard()
        return await message.reply_text("❌ Action cancelled.", reply_markup=markup)

    state = admin_input_states.get(user_id, {}).get("step")

    # 1. Channel Input
    if state == "WAITING_CHANNEL_INPUT":
        status_msg = await message.reply_text("⏳ `Verifying channel & syncing accounts + bots...`")
        success, response_msg = await add_and_sync_channel(client, input_text, status_msg)
        admin_input_states.pop(user_id, None)
        await safe_edit_text(status_msg, response_msg)
        text, markup = build_admin_dashboard()
        await message.reply_text(text, reply_markup=markup)

    # 2. Phone Number Input
    elif state == "WAITING_PHONE_NUMBER":
        status_msg = await message.reply_text("⏳ `Requesting Telegram login code...`")
        success, response_msg = await auth_system.request_otp(user_id, input_text)
        
        if success:
            admin_input_states[user_id] = {"step": "WAITING_OTP_CODE"}
            await safe_edit_text(
                status_msg,
                "📩 **Verification Code Sent!**\n\n"
                "Please enter the OTP code you received on Telegram.\n"
                "_(Tip: Put spaces like `1 2 3 4 5` if Telegram blocks code sending)_"
            )
        else:
            admin_input_states.pop(user_id, None)
            await safe_edit_text(status_msg, f"❌ {response_msg}")

    # 3. OTP Code Input
    elif state == "WAITING_OTP_CODE":
        status_msg = await message.reply_text("⏳ `Verifying OTP...`")
        status_code, result_str = await auth_system.submit_otp(user_id, input_text)

        if status_code == "SUCCESS":
            db.add_session(result_str)
            admin_input_states.pop(user_id, None)
            await safe_edit_text(status_msg, "✅ **User Account successfully logged in and linked!**")
            text, markup = build_admin_dashboard()
            await message.reply_text(text, reply_markup=markup)
        elif status_code == "2FA_REQUIRED":
            admin_input_states[user_id] = {"step": "WAITING_2FA_PASSWORD"}
            await safe_edit_text(
                status_msg,
                "🔐 **2-Step Verification Password Required**\n\n"
                "Please enter your account's 2FA cloud password:"
            )
        else:
            await safe_edit_text(status_msg, f"❌ {result_str}\n\nPlease try entering the OTP code again:")

    # 4. 2FA Password Input
    elif state == "WAITING_2FA_PASSWORD":
        status_msg = await message.reply_text("⏳ `Verifying 2FA password...`")
        status_code, result_str = await auth_system.submit_2fa(user_id, input_text)

        if status_code == "SUCCESS":
            db.add_session(result_str)
            admin_input_states.pop(user_id, None)
            await safe_edit_text(status_msg, "✅ **2FA Verified! Account successfully linked.**")
            text, markup = build_admin_dashboard()
            await message.reply_text(text, reply_markup=markup)
        else:
            await safe_edit_text(status_msg, f"❌ {result_str}\n\nPlease re-enter your 2FA password:")

    # 5. Sub-Bot Token Input
    elif state == "WAITING_BOT_TOKEN":
        status_msg = await message.reply_text("⏳ `Verifying Sub-Bot Token...`")
        try:
            temp_bot = Client("tmp_verifier", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=input_text, in_memory=True)
            await temp_bot.connect()
            me = await temp_bot.get_me()
            await temp_bot.disconnect()
            
            db.add_bot_token(input_text)
            admin_input_states.pop(user_id, None)
            await safe_edit_text(status_msg, f"✅ **Sub-Bot linked!**\n\n• **Username:** @{me.username}\n• **Name:** {me.first_name}")
        except Exception as e:
            admin_input_states.pop(user_id, None)
            await safe_edit_text(status_msg, f"❌ **Invalid Bot Token:** `{e}`")

        text, markup = build_admin_dashboard()
        await message.reply_text(text, reply_markup=markup)

    # 6. Reaction Emojis Input
    elif state == "WAITING_REACTIONS_LIST":
        emoji_list = input_text.split()
        if emoji_list:
            db.set_reactions(emoji_list)
            admin_input_states.pop(user_id, None)
            await message.reply_text(f"✅ **Reactions updated:** {' '.join(emoji_list)}")
            text, markup = build_admin_dashboard()
            await message.reply_text(text, reply_markup=markup)
        else:
            await message.reply_text("❌ Invalid input. Please enter valid emojis separated by spaces.")

    # 7. Delay Settings Input
    elif state == "WAITING_DELAYS":
        try:
            parts = input_text.split()
            min_val = float(parts[0])
            max_val = float(parts[1])
            if min_val < 0.5 or max_val < min_val:
                raise ValueError
            data = db.get_db()
            data["min_delay"] = min_val
            data["max_delay"] = max_val
            db.save_db(data)
            admin_input_states.pop(user_id, None)
            await message.reply_text(f"✅ **Delays updated:** `{min_val}s to {max_val}s`")
            text, markup = build_admin_dashboard()
            await message.reply_text(text, reply_markup=markup)
        except Exception:
            await message.reply_text("❌ Invalid format. Please send two numbers (e.g., `1.5 2.5`):")


# --- GLOBAL POST & POLL LISTENER ---

@app.on_message()
async def global_event_listener(client: Client, message: Message) -> None:
    if not message.chat:
        return

    registered_channels = db.get_monitored_channels()
    chat_id_str = str(message.chat.id)
    chat_id_clean = chat_id_str.replace("-100", "")

    is_monitored = False
    for saved_id in registered_channels.keys():
        if saved_id == chat_id_str or saved_id.replace("-100", "") == chat_id_clean:
            is_monitored = True
            break

    if not is_monitored:
        return

    print(f"🔥 [Event Detected] Chat: '{message.chat.title}' (ID: {message.chat.id}), Msg ID: {message.id}")

    # 1. Handle Polls
    if message.poll:
        print(f"📊 Poll detected: '{message.poll.question}' -> Notifying Admin...")
        await notify_admin_about_poll(client, message)
        return

    # 2. Handle All Post Types (Auto-Reactions)
    print(f"⚡ Dispatching reactions to Post ID: {message.id}...")
    asyncio.create_task(dispatch_safe_reactions(message.chat.id, message.id))


# --- ENTRY POINT ---

if __name__ == "__main__":
    db.init_db()
    print("══════════════════════════════════════════════")
    print(" 🚀 Telegram Engagement Master Bot is running")
    print(" 🛡 Python 3.11 Compatible | Safe Anti-Freeze")
    print("══════════════════════════════════════════════")
    app.run()
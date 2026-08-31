"""
Live In-Chat UI Animations & Progress Loaders
Compatible with Python 3.11
"""

import asyncio
from pyrogram.types import Message
from pyrogram.errors import MessageNotModified, FloodWait

# Aesthetic spinner frames for in-chat loading effects
SPINNER_FRAMES: list[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Smooth pulse symbols
PULSE_FRAMES: list[str] = ["⚡", "✨", "💫", "🌟", "⚡"]


async def run_bot_spinner(message: Message, task_title: str, duration_sec: float = 1.8) -> None:
    """
    Renders a live spinning animation directly in the Telegram chat message.
    """
    end_time = asyncio.get_event_loop().time() + duration_sec
    frame_index = 0

    while asyncio.get_event_loop().time() < end_time:
        frame = SPINNER_FRAMES[frame_index % len(SPINNER_FRAMES)]
        try:
            await message.edit_text(
                f"{frame} **{task_title}**\n"
                f"└─ `Processing request, please wait...`"
            )
        except MessageNotModified:
            pass
        except FloodWait as e:
            await asyncio.sleep(e.value)
            break
        except Exception:
            break

        frame_index += 1
        await asyncio.sleep(0.18)


async def run_bot_progress(message: Message, action_title: str, current: int, total: int) -> None:
    """
    Renders a live dynamic progress bar with percentage in the Telegram chat.
    """
    if total <= 0:
        return

    percentage = int((current / total) * 100)
    filled_blocks = int((current / total) * 10)
    empty_blocks = 10 - filled_blocks
    
    progress_bar = "🟩" * filled_blocks + "⬜" * empty_blocks

    text = (
        f"🚀 **{action_title}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Progress: `[{progress_bar}]` **{percentage}%**\n"
        f"• Status: `{current}/{total}` Accounts Finished\n"
        f"• Protection: `🛡 Anti-Flood safe delay active`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        await message.edit_text(text)
    except MessageNotModified:
        pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass


async def run_pulse_animation(message: Message, base_text: str, repeats: int = 3) -> None:
    """
    Renders a subtle glowing pulse animation on a message.
    """
    for frame in PULSE_FRAMES[:repeats]:
        try:
            await message.edit_text(f"{frame} **{base_text}** {frame}")
            await asyncio.sleep(0.25)
        except (MessageNotModified, Exception):
            pass
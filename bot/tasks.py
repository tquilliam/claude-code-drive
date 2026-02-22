"""Async task runner with progress updates and ASK_USER flow."""

import asyncio
import time
from typing import Optional
from telegram import Bot, Message
from agent import run_agent
from prompts import build_system_prompt
from database import get_recent_messages, save_message, create_or_get_session
from delivery import deliver_result
from tools import TOOLS
from config import PROGRESS_INTERVAL_SECONDS

# Global queue for user replies to ASK_USER questions
# Key: telegram_id, Value: asyncio.Queue of user responses
_user_reply_queues: dict[int, asyncio.Queue] = {}

ASK_USER_PREFIX = "ASK_USER:"


def enqueue_user_reply(telegram_id: int, text: str):
    """Enqueue a user reply for a pending task."""
    if telegram_id not in _user_reply_queues:
        _user_reply_queues[telegram_id] = asyncio.Queue()
    _user_reply_queues[telegram_id].put_nowait(text)


async def wait_for_user_reply(telegram_id: int, timeout: int = 300) -> Optional[str]:
    """Wait for a user reply with timeout."""
    if telegram_id not in _user_reply_queues:
        _user_reply_queues[telegram_id] = asyncio.Queue()
    try:
        reply = await asyncio.wait_for(_user_reply_queues[telegram_id].get(), timeout=timeout)
        return reply
    except asyncio.TimeoutError:
        return None


async def run_review_task(
    bot: Bot,
    chat_id: int,
    telegram_id: int,
    command: str,
    arguments: str,
    status_message: Message,
):
    """
    Long-running task: run the agentic loop and deliver results.
    """
    last_progress_at = time.monotonic()
    progress_lines: list[str] = [f"Starting {command}..."]

    async def progress_callback(line: str):
        nonlocal last_progress_at
        progress_lines.append(line)
        # Keep only last 5 progress lines
        display = progress_lines[-5:]
        now = time.monotonic()
        if now - last_progress_at >= PROGRESS_INTERVAL_SECONDS:
            last_progress_at = now
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text="Working on your review...\n\n" + "\n".join(f"- {l}" for l in display),
                )
            except Exception:
                pass  # Ignore edit failures (message too old, etc.)

    # Build system prompt
    try:
        system_prompt = build_system_prompt(command, arguments)
    except Exception as e:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=f"Error: {e}",
        )
        return

    # Load conversation history
    history = get_recent_messages(telegram_id, limit=20)

    # Add current user command
    messages = history + [{
        "role": "user",
        "content": f"/{command} {arguments}",
    }]

    conversation_id = create_or_get_session(telegram_id)

    try:
        # Run agent with ASK_USER loop
        while True:
            result_text = await run_agent(
                system_prompt=system_prompt,
                messages=messages,
                tools=TOOLS,
                progress_callback=progress_callback,
            )

            if result_text.strip().startswith(ASK_USER_PREFIX):
                # Extract and send question
                question = result_text.strip()[len(ASK_USER_PREFIX):].strip()
                await bot.send_message(chat_id=chat_id, text=f"🤔 {question}")

                # Wait for user reply
                user_reply = await wait_for_user_reply(telegram_id, timeout=300)
                if user_reply is None:
                    await bot.send_message(chat_id=chat_id, text="No reply received. Task cancelled.")
                    return

                # Append question and answer to messages
                messages.append({"role": "assistant", "content": result_text})
                messages.append({"role": "user", "content": user_reply})
            else:
                # Final result
                break

        # Save to conversation history
        save_message(conversation_id, "user", f"/{command} {arguments}")
        save_message(conversation_id, "assistant", result_text)

        # Deliver result
        await deliver_result(bot, chat_id, result_text, command, arguments)

        # Update status
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text="✅ Review complete.",
        )

    except Exception as e:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=f"❌ Error: {str(e)[:100]}",
        )

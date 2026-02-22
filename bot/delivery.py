"""Result delivery - send summary and file attachments to Telegram."""

import os
import glob
from datetime import date
from telegram import Bot
from config import PROJECT_ROOT

TELEGRAM_TEXT_LIMIT = 3800


async def deliver_result(bot: Bot, chat_id: int, summary_text: str, command: str, arguments: str):
    """
    Send the review results to Telegram.

    1. Send summary text (≤3800 chars) as Markdown message
    2. Find and send output files as document attachments
    """

    # Send summary text
    if len(summary_text) <= TELEGRAM_TEXT_LIMIT:
        await bot.send_message(
            chat_id=chat_id,
            text=summary_text,
            parse_mode="Markdown",
        )
    else:
        # Truncate if needed
        truncated = summary_text[:TELEGRAM_TEXT_LIMIT] + "\n\n...[truncated]"
        await bot.send_message(
            chat_id=chat_id,
            text=truncated,
            parse_mode="Markdown",
        )

    # Find and send output files
    today = date.today().isoformat()
    output_dirs = [
        os.path.join(PROJECT_ROOT, "reviews"),
        os.path.join(PROJECT_ROOT, "social-reviews"),
    ]

    files_to_send = []
    for output_dir in output_dirs:
        if not os.path.isdir(output_dir):
            continue
        pattern = os.path.join(output_dir, "**", f"*{today}*.md")
        matches = glob.glob(pattern, recursive=True)
        files_to_send.extend(matches)

    if not files_to_send:
        await bot.send_message(
            chat_id=chat_id,
            text="📄 *Note*: Full review files will be available in the output folder.",
            parse_mode="Markdown",
        )
        return

    # Send each file as a document
    for filepath in sorted(files_to_send):
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "rb") as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=filename,
                    caption=f"📋 {filename}",
                )
        except Exception as e:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Could not send file {filename}: {e}",
            )

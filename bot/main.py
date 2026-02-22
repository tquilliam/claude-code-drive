"""Telegram bot - main entry point."""

import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import config
import access
import database
from tasks import run_review_task, enqueue_user_reply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
database.init_db()

# Welcome message
WELCOME_MESSAGE = """
🤖 **Welcome to Website Analysis Bot!**

I help you analyze websites using AI-powered SEO, CRO, and content reviews.

**Available Commands:**

📄 `/review_page <url>`
Analyze a single page for SEO, CRO, and content quality
_Example: `/review_page https://example.com`_

📋 `/brief <description>`
Get a general analysis with auto-detection of scope
_Example: `/brief Analyze homepage for SEO issues`_

📊 `/social_review [brand]`
Analyze Meta social media performance (campaigns & organic)
_Example: `/social_review my-brand`_

**How It Works:**
1️⃣ Send a command with your request
2️⃣ Bot analyzes and shows progress updates
3️⃣ Get a summary + detailed report file

**Tips:**
• Detailed results are sent as file attachments
• Reviews typically take 5-10 minutes
• You can use conversation history for context ("do the same for...")

Ready to analyze? Send a command! 🚀
"""


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - show welcome message."""
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="Markdown",
    )


async def check_access(update: Update) -> bool:
    """Check if user is allowed and register them."""
    uid = update.effective_user.id
    username = update.effective_user.username
    database.register_user(uid, username)

    if not access.is_allowed(uid):
        await update.message.reply_text(
            "❌ Sorry, you are not authorised to use this bot."
        )
        return False
    return True


async def cmd_review_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /review_page command."""
    if not await check_access(update):
        return

    args = " ".join(context.args) if context.args else ""
    if not args.strip():
        await update.message.reply_text("Usage: `/review_page <url>`", parse_mode="Markdown")
        return

    status_msg = await update.message.reply_text("⏳ Starting review, please wait...")
    asyncio.create_task(
        run_review_task(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            telegram_id=update.effective_user.id,
            command="review-page",
            arguments=args,
            status_message=status_msg,
        )
    )


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /brief command."""
    if not await check_access(update):
        return

    args = " ".join(context.args) if context.args else ""
    if not args.strip():
        await update.message.reply_text("Usage: `/brief <description>`", parse_mode="Markdown")
        return

    status_msg = await update.message.reply_text("⏳ Processing brief, please wait...")
    asyncio.create_task(
        run_review_task(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            telegram_id=update.effective_user.id,
            command="brief",
            arguments=args,
            status_message=status_msg,
        )
    )


async def cmd_social_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /social_review command."""
    if not await check_access(update):
        return

    args = " ".join(context.args) if context.args else ""
    status_msg = await update.message.reply_text("⏳ Starting social review, please wait...")
    asyncio.create_task(
        run_review_task(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            telegram_id=update.effective_user.id,
            command="social-review",
            arguments=args,
            status_message=status_msg,
        )
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command text messages (for ASK_USER replies)."""
    if not await check_access(update):
        return

    # Enqueue the reply for any pending task
    enqueue_user_reply(update.effective_user.id, update.message.text)


def main():
    """Start the bot."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("review_page", cmd_review_page))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("social_review", cmd_social_review))

    # Message handler for ASK_USER flow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot started. Waiting for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

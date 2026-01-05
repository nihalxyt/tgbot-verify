"""User command handlers."""
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_USER_ID
from database_mysql import Database
from utils.checks import reject_group_command
from utils.messages import (
    get_welcome_message,
    get_about_message,
    get_help_message,
)

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """Handle the /start command."""
    if await reject_group_command(update):
        return

    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    full_name = user.full_name or ""

    # Return early if the user is already initialized.
    if db.user_exists(user_id):
        await update.message.reply_text(
            f"Welcome back, {full_name}!\n"
            "You are already registered.\n"
            "Send /help to see available commands."
        )
        return

    # Handle invite tracking.
    invited_by: Optional[int] = None
    if context.args:
        try:
            invited_by = int(context.args[0])
            if not db.user_exists(invited_by):
                invited_by = None
        except Exception:
            invited_by = None

    # Create user.
    if db.create_user(user_id, username, full_name, invited_by):
        welcome_msg = get_welcome_message(full_name, bool(invited_by))
        await update.message.reply_text(welcome_msg)
    else:
        await update.message.reply_text("Registration failed. Please try again later.")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """Handle the /about command."""
    if await reject_group_command(update):
        return

    await update.message.reply_text(get_about_message())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """Handle the /help command."""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_USER_ID
    await update.message.reply_text(get_help_message(is_admin))


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """Handle the /balance command."""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please register first with /start.")
        return

    await update.message.reply_text(
        f"💰 Credit Balance\n\nCurrent credits: {user['balance']}"
    )


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """Handle the /qd check-in command (temporarily disabled)."""
    user_id = update.effective_user.id

    # Temporarily disable check-in (bug fix in progress).
    # await update.message.reply_text(
    #     "⚠️ Daily check-in is temporarily under maintenance\n\n"
    #     "We found a bug and have temporarily disabled check-ins while we fix it.\n"
    #     "We expect to restore it soon. Thank you for your patience.\n\n"
    #     "💡 You can earn credits in the meantime:\n"
    #     "• Invite friends /invite (+2 credits)\n"
    #     "• Redeem a key /use <key>"
    # )
    # return
    
    # ===== The following code is disabled =====
    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    if not db.user_exists(user_id):
        await update.message.reply_text("Please register first with /start.")
        return

    # Layer 1 check: command handler level.
    if not db.can_checkin(user_id):
        await update.message.reply_text("❌ You have already checked in today. Please try again tomorrow.")
        return

    # Layer 2 check: database level (atomic SQL operation).
    if db.checkin(user_id):
        user = db.get_user(user_id)
        await update.message.reply_text(
            f"✅ Check-in successful!\nCredits earned: +1\nCurrent credits: {user['balance']}"
        )
    else:
        # If the database returns False, the user already checked in today.
        await update.message.reply_text("❌ You have already checked in today. Please try again tomorrow.")


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """Handle the /invite command."""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    if not db.user_exists(user_id):
        await update.message.reply_text("Please register first with /start.")
        return

    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start={user_id}"

    await update.message.reply_text(
        f"🎁 Your personal invite link:\n{invite_link}\n\n"
        "You earn 2 credits for each successful registration."
    )


async def use_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """Handle the /use command (redeem a key)."""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    if not db.user_exists(user_id):
        await update.message.reply_text("Please register first with /start.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /use <key>\n\nExample: /use wandouyu"
        )
        return

    key_code = context.args[0].strip()
    result = db.use_card_key(key_code, user_id)

    if result is None:
        await update.message.reply_text("The key does not exist. Please check and try again.")
    elif result == -1:
        await update.message.reply_text("This key has reached its usage limit.")
    elif result == -2:
        await update.message.reply_text("This key has expired.")
    elif result == -3:
        await update.message.reply_text("You have already used this key.")
    else:
        user = db.get_user(user_id)
        await update.message.reply_text(
            f"Key redeemed successfully!\nCredits earned: {result}\nCurrent credits: {user['balance']}"
        )

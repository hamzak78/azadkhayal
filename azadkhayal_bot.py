"""
Telegram Group Bot for "azadkhayal"
------------------------------------
Features:
1. Welcomes new members when they join the group.
2. Detects and deletes messages containing links or spam patterns.
3. Warns first, then bans repeat offenders (configurable).
4. Never touches admins/owners.

SETUP INSTRUCTIONS
===================
1. Create a bot:
   - Open Telegram, search for "BotFather"
   - Send /newbot and follow the prompts (choose a name + username)
   - Copy the API token BotFather gives you

2. Add the bot to your "azadkhayal" group:
   - Open your group -> Add Member -> search for your bot's username -> add it

3. Make the bot an ADMIN in the group:
   - Group Settings -> Administrators -> Add Admin -> select your bot
   - Required permissions: Delete Messages, Ban Users
   (Without admin rights, it cannot delete messages or ban anyone.)

4. Install dependencies on your machine (not needed on Render):
   pip install python-telegram-bot --upgrade

5. Set your bot token as an environment variable named BOT_TOKEN
   (on Render: Dashboard -> your service -> Environment -> Add Environment Variable),
   then run:
   python azadkhayal_bot.py

   NEVER hardcode your real token in this file, especially if this repo
   is public or shared - anyone with the token can fully control your bot.

CUSTOMIZE
=========
- WELCOME_MESSAGE: edit the greeting text.
- WARN_LIMIT: how many warnings before a ban (default: 1 warning, then ban on 2nd offense).
- SPAM_KEYWORDS: add/remove spam trigger words.
- Whitelisted domains: add any links you DO want to allow (e.g. your own channel).
"""

import os
import re
import logging
from collections import defaultdict

from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    ChatMemberHandler,
    filters,
)

# ------------------- CONFIG -------------------

# Placeholder used only to detect "token not set yet" - never put a real token here.
PLACEHOLDER_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"

BOT_TOKEN = os.environ.get("BOT_TOKEN", PLACEHOLDER_TOKEN)

GROUP_NAME = "azadkhayal"

WELCOME_MESSAGE = (
    "👋 Welcome to *{group_name}*, {mention}!\n\n"
    "Please read the group rules and be respectful.\n"
    "🚫 Sharing links or spam messages will get you banned automatically."
)

# How many warnings a user gets before being banned for spam/links.
# 0 = ban immediately on first offense
# 1 = warn once, ban on second offense
WARN_LIMIT = 1

# Links: matches http(s)://, www., t.me/, telegram links, and bare domains like example.com
LINK_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|\b[a-zA-Z0-9-]+\.(com|net|org|io|xyz|link|click|shop|top|gg|biz)\b)",
    re.IGNORECASE,
)

# Extra spam keyword/phrase triggers (add your own)
SPAM_KEYWORDS = [
    "join my channel",
    "click here",
    "free followers",
    "earn money fast",
    "crypto giveaway",
    "投资", "forex signal", "bet now",
]

# Domains you want to ALLOW even though they look like links (optional)
WHITELISTED_DOMAINS = [
    # "yourwebsite.com",
]

# ------------------- INTERNAL STATE -------------------

# Tracks warning counts per (chat_id, user_id)
warnings = defaultdict(int)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ------------------- HELPERS -------------------

def is_admin_cached(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """Check (best-effort) whether a user is an admin/owner in the chat."""
    admins = context.chat_data.get("_admin_ids")
    return admins is not None and user_id in admins


async def refresh_admin_cache(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        context.chat_data["_admin_ids"] = {a.user.id for a in admins}
    except Exception as e:
        logger.warning(f"Could not fetch admins: {e}")
        context.chat_data["_admin_ids"] = set()


def contains_link(text: str) -> bool:
    if not text:
        return False
    match = LINK_PATTERN.search(text)
    if not match:
        return False
    hit = match.group(0).lower()
    for domain in WHITELISTED_DOMAINS:
        if domain.lower() in hit:
            return False
    return True


def contains_spam_keyword(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in SPAM_KEYWORDS)


# ------------------- HANDLERS -------------------

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets each new member who joins the group."""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        mention = member.mention_html()
        text = WELCOME_MESSAGE.format(group_name=GROUP_NAME, mention=mention)
        await update.message.reply_html(text)


async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes link/spam messages and warns or bans the sender."""
    message = update.message
    if message is None or message.text is None:
        return

    chat_id = message.chat_id
    user = message.from_user

    # Refresh admin list once per chat session (cache it)
    if "_admin_ids" not in context.chat_data:
        await refresh_admin_cache(context, chat_id)

    if is_admin_cached(context, chat_id, user.id):
        return  # never moderate admins

    text = message.text or message.caption or ""

    if contains_link(text) or contains_spam_keyword(text):
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")

        key = (chat_id, user.id)
        warnings[key] += 1

        if warnings[key] > WARN_LIMIT:
            try:
                await context.bot.ban_chat_member(chat_id, user.id)
                await context.bot.send_message(
                    chat_id,
                    f"🚫 {user.mention_html()} has been banned for sending links/spam.",
                    parse_mode=ParseMode.HTML,
                )
                warnings.pop(key, None)
            except Exception as e:
                logger.warning(f"Could not ban user: {e}")
        else:
            remaining = WARN_LIMIT - warnings[key] + 1
            try:
                await context.bot.send_message(
                    chat_id,
                    f"⚠️ {user.mention_html()}, links/spam are not allowed here. "
                    f"Warning {warnings[key]}/{WARN_LIMIT + 1}. Next violation = ban.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.warning(f"Could not send warning: {e}")


# ------------------- MAIN -------------------

def main():
    if not BOT_TOKEN or BOT_TOKEN == PLACEHOLDER_TOKEN:
        raise SystemExit(
            "ERROR: Set your bot token first!\n"
            "Set it as an environment variable named BOT_TOKEN "
            "(on Render: Dashboard -> your service -> Environment), "
            "or run locally with:\n"
            "  BOT_TOKEN=123456:ABC-your-token python azadkhayal_bot.py"
        )

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Welcome new members
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # Moderate all text/caption messages for links & spam
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate_message))
    app.add_handler(MessageHandler(filters.CAPTION, moderate_message))

    logger.info(f"Bot for '{GROUP_NAME}' starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

"""
Telegram Group Bot for "azadkhayal"
------------------------------------
Features:
1. Detects and deletes spam/link messages.
2. Warns user on first offense.
3. Bans on second offense.
4. Never touches admins/owners.
5. No welcome messages.

SETUP:
- Set BOT_TOKEN as an environment variable (e.g. on Render/Railway)
- Make the bot an admin in your group with Delete Messages + Ban Users permissions
- Run: python main.py
"""

import os
import re
import logging
from collections import defaultdict

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")

# How many warnings before ban.
# 0 = ban immediately on first offense
# 1 = warn once, ban on second offense
WARN_LIMIT = 1

# ── Spam keywords ──────────────────────────────────────────────────────────────
SPAM_KEYWORDS = [
    # Crypto / investment scams
    "binance", "bybit", "okx", "coinbase", "crypto", "bitcoin",
    "btc", "usdt", "forex", "trading signal", "crypto signal",
    "invest now", "earn money", "earn daily", "profit guaranteed",
    "passive income", "double your money", "10x returns", "pump group",
    "airdrop", "nft drop", "mint now",

    # Generic spam phrases
    "click here", "click this", "join now", "join our", "join my",
    "join channel", "join group", "subscribe now", "follow me", "follow us",
    "dm me", "dm for", "message me", "contact me", "whatsapp me",
    "free followers", "free members", "100% real", "make money fast",
    "work from home", "limited offer", "act now", "only today",
    "don't miss", "exclusive deal", "giveaway", "prize", "winner",
    "congratulations you", "you have been selected",

    # Promotion / advertising
    "promo", "advertisement", "sponsored", "buy now", "order now",
    "shop now", "discount code", "coupon code", "referral link",
    "ref link", "affiliate",
]

# ── Link patterns ──────────────────────────────────────────────────────────────
LINK_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+"
    r"|\b[a-zA-Z0-9-]+\.(com|net|org|io|xyz|link|click|shop|top|gg|biz|info|co)\b)",
    re.IGNORECASE,
)

# Domains you want to ALLOW even though they look like links (optional).
WHITELISTED_DOMAINS: list[str] = [
    # "azadkhayail.blogspot.com",
]

# ─────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────

warnings: dict[tuple, int] = defaultdict(int)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────

def is_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    admin_ids = context.chat_data.get("_admin_ids")
    return bool(admin_ids and user_id in admin_ids)


async def refresh_admins(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        context.chat_data["_admin_ids"] = {a.user.id for a in admins}
    except Exception as e:
        logger.warning("Could not fetch admins: %s", e)
        context.chat_data.setdefault("_admin_ids", set())


def has_link(text: str) -> bool:
    if not text:
        return False
    match = LINK_PATTERN.search(text)
    if not match:
        return False
    hit = match.group(0).lower()
    return not any(d.lower() in hit for d in WHITELISTED_DOMAINS)


def has_spam(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(kw.lower() in low for kw in SPAM_KEYWORDS)


def get_trigger(text: str) -> str:
    low = text.lower()
    for kw in SPAM_KEYWORDS:
        if kw.lower() in low:
            return f'"{kw}"'
    return "a link"


# ─────────────────────────────────────────
#  HANDLER
# ─────────────────────────────────────────

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    chat_id = message.chat_id
    user = message.from_user

    if "_admin_ids" not in context.chat_data:
        await refresh_admins(context, chat_id)

    if is_admin(context, user.id):
        return

    violated = has_link(text) or has_spam(text)
    if not violated:
        return

    trigger = get_trigger(text)

    try:
        await message.delete()
    except Exception as e:
        logger.warning("Could not delete message: %s", e)

    key = (chat_id, user.id)
    warnings[key] += 1
    warn_num = warnings[key]
    total = WARN_LIMIT + 1

    if warn_num > WARN_LIMIT:
        try:
            await context.bot.ban_chat_member(chat_id, user.id)
            await context.bot.send_message(
                chat_id,
                f"🚫 {user.mention_html()} has been <b>banned</b> for sending spam/links repeatedly.",
                parse_mode=ParseMode.HTML,
            )
            warnings.pop(key, None)
        except Exception as e:
            logger.warning("Could not ban user: %s", e)
    else:
        remaining = total - warn_num
        await context.bot.send_message(
            chat_id,
            f"⚠️ {user.mention_html()}, your message was removed because it contained {trigger}.\n"
            f"Spam and links are <b>not allowed</b> here.\n"
            f"<b>Warning {warn_num}/{total}</b> — {remaining} more violation(s) and you will be banned.",
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────

def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise SystemExit(
            "ERROR: Set your bot token!\n"
            "Run with:  BOT_TOKEN=your_token python main.py"
        )

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate))
    app.add_handler(MessageHandler(filters.CAPTION, moderate))

    logger.info("Azadkhayal moderation bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

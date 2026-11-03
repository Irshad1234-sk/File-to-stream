# config.py
# Saari secret values SIRF Environment Variables se aayengi (Voroa dashboard me set karo).
# Code me kabhi token / password mat likho.

import os
from dotenv import load_dotenv

load_dotenv()


def _get(name, default=""):
    return os.environ.get(name, default).strip()


def get_channel_value(value):
    """Numeric channel ID -> int, username -> string, khali -> 0."""
    value = (value or "").strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return value.lstrip("@")


def _get_int(name, default=0):
    try:
        return int(_get(name, str(default)) or default)
    except ValueError:
        return default


class Config:
    # Telegram API credentials (my.telegram.org se)
    API_ID = _get_int("API_ID")
    API_HASH = _get("API_HASH")

    # Bot credentials (@BotFather se)
    BOT_TOKEN = _get("BOT_TOKEN")
    BOT_USERNAME = _get("BOT_USERNAME").replace("https://t.me/", "").replace("http://t.me/", "").lstrip("@")

    # Owner ka Telegram user ID
    OWNER_ID = _get_int("OWNER_ID")

    # Private storage channel (bot ko admin banao). Example: -1001234567890
    STORAGE_CHANNEL = get_channel_value(_get("STORAGE_CHANNEL"))

    # Website ka public URL, bina last slash ke.
    # Example: https://autofilter-7bb1.getvoroa.com
    BASE_URL = _get("BASE_URL").rstrip("/")

    # MongoDB connection string (password ke saath, <db_username> jaisa placeholder nahi)
    DATABASE_URL = _get("DATABASE_URL")

    # Force subscribe (OPTIONAL). Yeh STORAGE_CHANNEL se ALAG channel hona chahiye.
    # Khali chhodo to force-sub band rahega.
    FORCE_SUB_CHANNEL = get_channel_value(_get("FORCE_SUB_CHANNEL"))
    # Private channel ho to invite link yahan do (https://t.me/+xxxx)
    FORCE_SUB_LINK = _get("FORCE_SUB_LINK")

    @classmethod
    def missing(cls):
        """Zaroori variables jo set nahi hain unki list."""
        need = {
            "API_ID": cls.API_ID,
            "API_HASH": cls.API_HASH,
            "BOT_TOKEN": cls.BOT_TOKEN,
            "STORAGE_CHANNEL": cls.STORAGE_CHANNEL,
            "DATABASE_URL": cls.DATABASE_URL,
            "BASE_URL": cls.BASE_URL,
        }
        return [k for k, v in need.items() if not v]

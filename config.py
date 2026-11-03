# config.py

import os
from dotenv import load_dotenv

# Load .env locally (Voroa par Environment Variables bhi use honge)
load_dotenv()


def get_channel_value(value):
    """Convert numeric channel IDs to int; keep usernames as strings."""
    if not value:
        return 0

    value = value.strip()

    try:
        return int(value)
    except ValueError:
        return value


class Config:
    # Telegram API credentials
    API_ID = int(os.environ.get("API_ID", "38073622").strip() or "0")
    API_HASH = os.environ.get("API_HASH", "bba60563d6c7dfe8d9d4b38381a873d9").strip()

    # Bot credentials
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8701553802:AAERDn4dBmA7QitBVXsV9WRfJ6uGx41f8cE").strip()
    BOT_USERNAME = os.environ.get("BOT_USERNAME", "http://t.me/Movie_download12bot").strip().lstrip("@")

    # Owner
    OWNER_ID = int(os.environ.get("OWNER_ID", "7407461573").strip() or "0")

    # Storage channel
    STORAGE_CHANNEL = get_channel_value(
        os.environ.get("STORAGE_CHANNEL", "-1004302762211")
    )

    # Website / redirect
    BASE_URL = os.environ.get("BASE_URL", "").strip().rstrip("/")
    REDIRECT_BLOGGER_URL = os.environ.get(
        "REDIRECT_BLOGGER_URL", ""
    ).strip()
    BLOGGER_PAGE_URL = os.environ.get(
        "BLOGGER_PAGE_URL", ""
    ).strip()

    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL", "mongodb+srv://<db_username>:5ZhoCsY8EXh7c8C7@cluster0.gex5qt7.mongodb.net/?appName=Cluster0").strip()

    # Force subscribe channel
    FORCE_SUB_CHANNEL = get_channel_value(
        os.environ.get("FORCE_SUB_CHANNEL", "-1004302762211")
    )

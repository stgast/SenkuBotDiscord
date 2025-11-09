import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TOKEN = os.getenv("DISCORD_TOKEN")
    MODERATION_CHANNEL_ID = int(os.getenv("MODERATION_CHANNEL_ID", "0"))
    APPROVED_CHANNEL_ID = int(os.getenv("APPROVED_CHANNEL_ID", "0"))
    MODERATOR_ROLE_ID = int(os.getenv("MODERATOR_ROLE_ID", "0"))
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
    NEWS_LIMIT = int(os.getenv("NEWS_LIMIT", "6"))
    FORUM_CHANNEL_ID = int(os.getenv("FORUM_CHANNEL_ID", "0"))

config = Config()

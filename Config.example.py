# TELEGRAM CONFIGURATION
# Admin ID, for errors alert
import os

TELEGRAM_ADMIN_ID = os.environ["TELEGRAM_ADMIN_ID"]
# Channel Name, for error alert (formatting)
TELEGRAM_CHANNEL_NAME = os.environ["TELEGRAM_CHANNEL_NAME"]
# Channel ID, to send news
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
# Bot token, the bot that send news to the channel
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# MONGODB CONFIGURATION
# MongoDB Connection URI
MONGODB_URI = os.environ["MONGODB_URI"]
# MongoDB Authentication Certificate
MONGODB_CERTIFICATE = os.environ["MONGODB_CERTIFICATE"]
# Database Name
MONGODB_DATABASE = os.environ["MONGODB_DATABASE"]
# Database's Collection Name
MONGODB_COLLECTION = os.environ["MONGODB_COLLECTION"]

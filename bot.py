import asyncio
import nest_asyncio
import datetime
import json
import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import pytz

# Apply nest_asyncio to handle running loops
nest_asyncio.apply()

# Load bot configuration from config/config.json
CONFIG_DIR = "config"
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

with open(CONFIG_FILE, 'r') as config_file:
    config = json.load(config_file)

TOKEN = config.get("TOKEN")
TIMEZONE = config.get("TIMEZONE", "Europe/Berlin")  # Default to 'Europe/Berlin' if not specified
IMAGE_URL = config.get("IMAGE_URL")
BUTTON_URL = config.get("BUTTON_URL")
LOG_LEVEL = config.get("LOG_LEVEL", "INFO").upper()  # Default to INFO if not specified

# Configure logging based on the log level from config
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL, logging.INFO)  # Fallback to INFO if invalid level
)

logger = logging.getLogger(__name__)

# Log the successful retrieval of the token with only first 6 characters visible
if TOKEN:
    redacted_token = TOKEN[:6] + '*' * (len(TOKEN) - 6)
    logger.info(f"Token retrieved successfully: {redacted_token}")
else:
    logger.error("Failed to retrieve bot token from config.")

# Constants
if not IMAGE_URL or not BUTTON_URL:
    logger.error("IMAGE_URL or BUTTON_URL not found in the config file.")
    exit(1)

# Ensure the config directory exists
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

# Path for SQLite database file in the config folder
DATABASE_FILE = os.path.join(CONFIG_DIR, "group_data.db")

# Timezone configuration
try:
    TIMEZONE_OBJ = pytz.timezone(TIMEZONE)
except pytz.UnknownTimeZoneError:
    logger.error(f"Invalid timezone '{TIMEZONE}' in config.json. Defaulting to 'Europe/Berlin'.")
    TIMEZONE_OBJ = pytz.timezone("Europe/Berlin")

# Initialize SQLite connection and create table for storing group ID
def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS group_data (
                        id INTEGER PRIMARY KEY,
                        group_chat_id INTEGER
                      )''')
    conn.commit()
    conn.close()

# Load group chat ID from database
def load_group_id():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT group_chat_id FROM group_data WHERE id=1")
    row = cursor.fetchone()
    conn.close()
    if row:
        logger.info(f"Loaded existing group chat ID: {row[0]}")
        return row[0]
    return None

# Save group chat ID to database
def save_group_id(group_chat_id):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO group_data (id, group_chat_id) VALUES (1, ?)", (group_chat_id,))
    conn.commit()
    conn.close()

# Initialize the group chat ID
init_db()  # Ensure the database and table are set up
GROUP_CHAT_ID = load_group_id()
if GROUP_CHAT_ID is None:
    logger.info("Group chat ID not set. Please set it using /set_group_id.")
else:
    logger.info(f"Group chat ID is already set to: {GROUP_CHAT_ID}")

# Global variable to track if night mode is active
night_mode_active = False

# Get the current time in the desired timezone
def get_current_time():
    return datetime.datetime.now(TIMEZONE_OBJ)

# Define a command handler function
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.message.from_user.id} used /start")
    await update.message.reply_text('Hello! I am your bot. How can I help you?')

# Command to set the group ID
async def set_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global GROUP_CHAT_ID
    GROUP_CHAT_ID = update.message.chat_id
    save_group_id(GROUP_CHAT_ID)
    logger.info(f"Group chat ID set to: {GROUP_CHAT_ID} by user {update.message.from_user.id}")
    await update.message.reply_text(f"Group chat ID set to: {GROUP_CHAT_ID}")

# Define a function to welcome new members
async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        logger.info(f"New member {member.full_name} joined the group.")
        button = InlineKeyboardButton("StreamNet TV Store", url=BUTTON_URL)
        keyboard = InlineKeyboardMarkup([[button]])
        
        now = get_current_time()
        date_time = now.strftime("%d.%m.%Y %H:%M:%S")
        username = f"@{member.username}" if member.username else member.full_name

        welcome_message = (
            f"\n🎉 Howdy, {member.full_name}!\n\n"
            "Vielen Dank, dass du diesen Service ausgewählt hast ❤️.\n\n"
            f"Username: {username}\n"
            f"Beitritt: {date_time}\n\n"
            "Wir hoffen, du hast eine gute Unterhaltung mit StreamNet TV.\n\n"
            "Bei Fragen oder sonstiges einfach in die verschiedenen Topics reinschreiben."
        )

        await update.message.chat.send_photo(
            photo=IMAGE_URL,
            caption=welcome_message,
            reply_markup=keyboard
        )

# Define a message handler to restrict messages during night mode
async def restrict_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = get_current_time()
    if night_mode_active:
        if not update.message.from_user.is_admin:
            logger.info(f"Deleting message from user {update.message.from_user.id} due to night mode.")
            await update.message.reply_text("❌ Sorry, solange der NACHTMODUS aktiviert ist, kannst du von 00:00 Uhr bis 07:00 Uhr keine Mitteilungen in der Gruppe senden.")
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)

# Background task to check and switch night mode
async def night_mode_checker(context):
    global night_mode_active
    while True:
        now = get_current_time()  # Get the current time in the specified timezone
        if now.hour == 0 and not night_mode_active:
            night_mode_active = True
            logger.info("Night mode activated.")
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff braucht auch mal eine Pause.")
        elif now.hour == 7 and night_mode_active:
            night_mode_active = False
            logger.info("Night mode deactivated.")
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="☀️ ENDE DES NACHTMODUS.\n\n✅ Ab jetzt kannst du wieder Mitteilungen in der Gruppe senden.")
        await asyncio.sleep(300)  # Check every 5 minutes

# Command to enable night mode
async def enable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if not night_mode_active:
        night_mode_active = True
        logger.info(f"Night mode enabled by user {update.message.from_user.id}.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff braucht auch mal eine Pause.")

# Command to disable night mode
async def disable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if night_mode_active:
        night_mode_active = False
        logger.info(f"Night mode disabled by user {update.message.from_user.id}.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="☀️ ENDE DES NACHTMODUS.\n\n✅ Ab jetzt kannst du wieder Mitteilungen in der Gruppe senden.")

async def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    # Register the command handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_group_id", set_group_id))
    application.add_handler(CommandHandler("enable_night_mode", enable_night_mode))
    application.add_handler(CommandHandler("disable_night_mode", disable_night_mode))

    # Register the message handler for new members
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))

    # Register the message handler for general messages (to restrict during night mode)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, restrict_night_mode))

    # Start the night mode checker task
    application.job_queue.run_repeating(night_mode_checker, interval=300, first=0)

    # Start the Bot
    logger.info("Bot started polling.")
    await application.run_polling()

if __name__ == '__main__':
    try:
        logger.info("Starting the bot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped gracefully.")

import asyncio
import nest_asyncio
import datetime
import json
import os
import sqlite3
import logging
import requests
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
TIMEZONE = config.get("TIMEZONE", "Europe/Berlin")
TMDB_API_KEY = config.get("TMDB_API_KEY")
DEFAULT_LANGUAGE = config.get("DEFAULT_LANGUAGE", "en")
IMAGE_URL = config.get("IMAGE_URL")
BUTTON_URL = config.get("BUTTON_URL")
LOG_LEVEL = config.get("LOG_LEVEL", "INFO").upper()

# Configure logging based on the log level from config
logging.basicConfig(
    format='%(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL, logging.INFO)
)

logger = logging.getLogger(__name__)

# Log the successful retrieval of the token with only first 6 characters visible
if TOKEN:
    redacted_token = TOKEN[:6] + '*' * (len(TOKEN) - 6)
    logger.info(f"Token retrieved successfully: {redacted_token}")
else:
    logger.error("Failed to retrieve bot token from config.")

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
                        group_chat_id INTEGER,
                        language TEXT DEFAULT 'en'
                      )''')
    conn.commit()
    conn.close()

# Load group chat ID from database
def load_group_id():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT group_chat_id, language FROM group_data WHERE id=1")
    row = cursor.fetchone()
    conn.close()
    if row:
        logger.info(f"Loaded existing group chat ID: {row[0]} and language: {row[1]}")
        return row[0], row[1]
    return None, DEFAULT_LANGUAGE

# Save group chat ID and language to the database
def save_group_id(group_chat_id, language=DEFAULT_LANGUAGE):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO group_data (id, group_chat_id, language) VALUES (1, ?, ?)",
                   (group_chat_id, language))
    conn.commit()
    conn.close()

# Initialize the group chat ID and language
init_db()  # Ensure the database and table are set up
GROUP_CHAT_ID, LANGUAGE = load_group_id()
if GROUP_CHAT_ID is None:
    logger.info("Group chat ID not set. Please set it using /set_group_id.")
else:
    logger.info(f"Group chat ID is already set to: {GROUP_CHAT_ID}")

# Global variable to track if night mode is active
night_mode_active = False

# Mutex lock to prevent overlapping long-running operations
task_lock = asyncio.Lock()

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
    save_group_id(GROUP_CHAT_ID, LANGUAGE)
    logger.info(f"Group chat ID set to: {GROUP_CHAT_ID} by user {update.message.from_user.id}")
    await update.message.reply_text(f"Group chat ID set to: {GROUP_CHAT_ID}")

# Command to set the language for TMDb responses
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LANGUAGE
    if len(context.args) > 0:
        LANGUAGE = context.args[0]
        save_group_id(GROUP_CHAT_ID, LANGUAGE)
        logger.info(f"Language set to: {LANGUAGE} by user {update.message.from_user.id}")
        await update.message.reply_text(f"Language set to: {LANGUAGE}")
    else:
        await update.message.reply_text("Please provide a language code, e.g., 'en', 'de', 'fr'.")

# TMDb API request
def search_tmdb(query, category="movie", language="en"):
    url = f"https://api.themoviedb.org/3/search/{category}"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": language
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        results = response.json().get('results', [])
        if results:
            return results[0]  # Return the first result
    logger.error(f"Failed to fetch TMDb data: {response.status_code} {response.text}")
    return None

# Format TMDb result with movie or TV show details
def format_tmdb_result(result, category="movie"):
    title = result.get('title', result.get('name', 'Unknown Title'))
    overview = result.get('overview', 'No description available.')
    release_date = result.get('release_date', result.get('first_air_date', 'Unknown'))
    poster_path = result.get('poster_path', None)
    
    message = f"*{title}*\n\n"
    message += f"📅 Release Date: {release_date}\n\n"
    message += f"📝 Overview:\n{overview}"
    
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
    return message, poster_url

# Command to search for a movie
async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Please provide a movie name after the command, like: /search_movie Inception")
        return

    async with task_lock:
        result = search_tmdb(query, category="movie", language=LANGUAGE)
        if result:
            message, poster_url = format_tmdb_result(result, category="movie")
            if poster_url:
                await update.message.reply_photo(photo=poster_url, caption=message, parse_mode="Markdown")
            else:
                await update.message.reply_text(message, parse_mode="Markdown")
        else:
            await update.message.reply_text("Sorry, I couldn't find any results for your query.")

# Command to search for a TV show
async def search_tv_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Please provide a TV show name after the command, like: /search_tv_show Breaking Bad")
        return

    async with task_lock:
        result = search_tmdb(query, category="tv", language=LANGUAGE)
        if result:
            message, poster_url = format_tmdb_result(result, category="tv")
            if poster_url:
                await update.message.reply_photo(photo=poster_url, caption=message, parse_mode="Markdown")
            else:
                await update.message.reply_text(message, parse_mode="Markdown")
        else:
            await update.message.reply_text("Sorry, I couldn't find any results for your query.")

# Command to enable night mode
async def enable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    async with task_lock:
        if not night_mode_active:
            night_mode_active = True
            logger.info(f"Night mode enabled by user {update.message.from_user.id}")
            await update.message.reply_text("🌙 Nachtmodus aktiviert.")
        else:
            await update.message.reply_text("Night mode is already active.")

# Command to disable night mode
async def disable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    async with task_lock:
        if night_mode_active:
            night_mode_active = False
            logger.info(f"Night mode disabled by user {update.message.from_user.id}")
            await update.message.reply_text("☀️ Nachtmodus deaktiviert.")
        else:
            await update.message.reply_text("Night mode is already deactivated.")

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
        is_admin = update.message.from_user.is_admin
        if not is_admin:
            logger.info(f"Deleting message from non-admin user {update.message.from_user.id} due to night mode.")
            await update.message.reply_text("❌ Sorry, solange der NACHTMODUS aktiviert ist, kannst du von 00:00 Uhr bis 07:00 Uhr keine Mitteilungen in der Gruppe oder in den Topics senden.")
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)

# Background task to check and switch night mode
async def night_mode_checker(context):
    async with task_lock:
        logger.info("Night mode checker started.")
        now = get_current_time()
        if now.hour == 0 and not night_mode_active:
            night_mode_active = True
            logger.info("Night mode activated.")
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff braucht auch mal eine Pause.")
        elif now.hour == 7 and night_mode_active:
            night_mode_active = False
            logger.info("Night mode deactivated.")
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="☀️ ENDE DES NACHTMODUS.\n\n✅ Ab jetzt kannst du wieder Mitteilungen in der Gruppe senden.")
        logger.info("Night mode checker finished.")
        await asyncio.sleep(300)  # Check every 5 minutes

async def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    # Register the command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_group_id", set_group_id))
    application.add_handler(CommandHandler("set_language", set_language))
    application.add_handler(CommandHandler("enable_night_mode", enable_night_mode))
    application.add_handler(CommandHandler("disable_night_mode", disable_night_mode))
    application.add_handler(CommandHandler("search_movie", search_movie))
    application.add_handler(CommandHandler("search_tv_show", search_tv_show))

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

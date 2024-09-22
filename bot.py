import asyncio
import nest_asyncio
import datetime
import json
import os
import sqlite3
import logging
import aiohttp  # Use aiohttp for non-blocking HTTP requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import pytz

# Apply nest_asyncio to handle running loops
nest_asyncio.apply()

# Load bot configuration from config/config.json
CONFIG_DIR = "config"
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found.")

with open(CONFIG_FILE, 'r') as config_file:
    config = json.load(config_file)

TOKEN = config.get("TOKEN")
TIMEZONE = config.get("TIMEZONE", "Europe/Berlin")
IMAGE_URL = config.get("IMAGE_URL")
BUTTON_URL = config.get("BUTTON_URL")
LOG_LEVEL = config.get("LOG_LEVEL", "INFO").upper()
TMDB_API_KEY = config.get("TMDB_API_KEY")

# Configure logging
logging.basicConfig(
    format='%(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL, logging.INFO)
)

logger = logging.getLogger(__name__)

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

# Initialize SQLite connection and create table for storing group ID and language
def init_db():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS group_data (
                            id INTEGER PRIMARY KEY,
                            group_chat_id INTEGER,
                            language TEXT DEFAULT 'en'
                          )''')
        conn.commit()

# Load group chat ID and language from database
def load_group_id():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT group_chat_id, language FROM group_data WHERE id=1")
        row = cursor.fetchone()
    if row:
        logger.info(f"Loaded existing group chat ID: {row[0]}, language: {row[1]}")
        return row[0], row[1]
    return None, None

# Save group chat ID and language to database
def save_group_id(group_chat_id, language):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO group_data (id, group_chat_id, language) VALUES (1, ?, ?)", (group_chat_id, language))
        conn.commit()

# Initialize the group chat ID and language
init_db()  # Ensure the database and table are set up
GROUP_CHAT_ID, LANGUAGE = load_group_id()
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
    if update.message.chat.type in ['group', 'supergroup']:
        GROUP_CHAT_ID = update.message.chat_id
        save_group_id(GROUP_CHAT_ID, LANGUAGE)
        logger.info(f"Group chat ID set to: {GROUP_CHAT_ID} by user {update.message.from_user.id}")
        await update.message.reply_text(f"Group chat ID set to: {GROUP_CHAT_ID}")
    else:
        await update.message.reply_text("❌ This command can only be used in a group chat.")

# Command to set the language
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LANGUAGE
    if context.args and len(context.args) == 1:
        LANGUAGE = context.args[0]
        if len(LANGUAGE) != 2:
            await update.message.reply_text("❌ Please specify a valid two-letter language code (e.g., 'en', 'de').")
            return
        save_group_id(GROUP_CHAT_ID, LANGUAGE)
        logger.info(f"Language set to: {LANGUAGE} by user {update.message.from_user.id}")
        await update.message.reply_text(f"Language set to: {LANGUAGE}")
    else:
        await update.message.reply_text("❌ Please specify a language code (e.g., 'en', 'de').")

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

# Search for a movie using TMDB API with aiohttp (non-blocking)
async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await search_media(update, context, "movie")

# Search for a TV show using TMDB API with aiohttp (non-blocking)
async def search_tv_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await search_media(update, context, "tv")

# Generic function to search for a movie or TV show
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type: str) -> None:
    try:
        if not context.args:
            await update.message.reply_text(f"Please provide a {media_type} title.")
            return

        title = " ".join(context.args)
        logger.info(f"Searching for {media_type}: {title}")

        url = f"https://api.themoviedb.org/3/search/{media_type}?api_key={TMDB_API_KEY}&query={title}&language={LANGUAGE}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(f"HTTP error {response.status} from TMDb API.")
                media_data = await response.json()

        if not media_data['results']:
            await update.message.reply_text(f"No results found for that {media_type} title.")
            return

        # Get the first result
        media = media_data['results'][0]
        title_key = 'name' if media_type == 'tv' else 'title'
        poster_url = f"https://image.tmdb.org/t/p/w500{media['poster_path']}" if media['poster_path'] else None
        rating = media.get('vote_average', 'N/A')

        message = (
            f"**Title:** {media[title_key]}\n"
            f"**Release Date:** {media.get('first_air_date' if media_type == 'tv' else 'release_date', 'N/A')}\n"
            f"**Rating:** {rating} / 10\n"
            f"**Summary:** {media['overview']}"
        )

        # Truncate the message if it exceeds the maximum length
        if len(message) > 1024:
            message = message[:1021] + '...'

        if poster_url:
            await update.message.reply_photo(photo=poster_url, caption=message, parse_mode="Markdown")
        else:
            await update.message.reply_text(message)

    except aiohttp.ClientError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        await update.message.reply_text("❌ There was an error fetching data from TMDb. Please try again later.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again later.")

# Define a message handler to restrict messages during night mode
async def restrict_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if update.message.chat_id != GROUP_CHAT_ID:
        return

    user_id = update.message.from_user.id
    chat_member = await update.message.chat.get_member(user_id)

    if night_mode_active and not chat_member.is_chat_admin():
        logger.info(f"Message restricted during night mode for user {user_id}.")
        await update.message.delete()

# Background task to check and activate night mode
async def night_mode_checker(application) -> None:
    global night_mode_active
    while True:
        now = get_current_time()
        # Night mode from 00:00 to 07:00
        night_mode_active = now.hour >= 0 and now.hour < 7
        if night_mode_active:
            logger.info("Night mode is active. Messages will be restricted.")
        else:
            logger.info("Night mode is inactive. Messages are allowed.")

        # Check every 5 minutes
        await asyncio.sleep(300)

# Enable night mode command
async def enable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if update.message.chat_id != GROUP_CHAT_ID:
        await update.message.reply_text("❌ This command can only be used in the group chat.")
        return

    night_mode_active = True
    logger.info(f"Night mode enabled by user {update.message.from_user.id}.")
    await update.message.reply_text("✅ Night mode has been enabled.")

# Disable night mode command
async def disable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if update.message.chat_id != GROUP_CHAT_ID:
        await update.message.reply_text("❌ This command can only be used in the group chat.")
        return

    night_mode_active = False
    logger.info(f"Night mode disabled by user {update.message.from_user.id}.")
    await update.message.reply_text("✅ Night mode has been disabled.")

# Initialize the bot application
application = ApplicationBuilder().token(TOKEN).build()

# Add command and message handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("set_group_id", set_group_id))
application.add_handler(CommandHandler("set_language", set_language))
application.add_handler(CommandHandler("enable_night_mode", enable_night_mode))
application.add_handler(CommandHandler("disable_night_mode", disable_night_mode))
application.add_handler(CommandHandler("search_movie", search_movie))
application.add_handler(CommandHandler("search_tv_show", search_tv_show))  # Added search TV show command
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, restrict_night_mode))

# Start background tasks
asyncio.ensure_future(night_mode_checker(application))

# Start the bot
logger.info("Starting the bot...")
application.run_polling()

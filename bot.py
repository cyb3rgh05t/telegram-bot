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

TOKEN = config.get("bot").get("TOKEN")
TIMEZONE = config.get("bot").get("TIMEZONE", "Europe/Berlin")
IMAGE_URL = config.get("welcome").get("IMAGE_URL")
BUTTON_URL = config.get("welcome").get("BUTTON_URL")
LOG_LEVEL = config.get("bot").get("LOG_LEVEL", "INFO").upper()
TMDB_API_KEY = config.get("tmdb").get("API_KEY")
SONARR_URL = config.get("sonarr").get("URL")
SONARR_API_KEY = config.get("sonarr").get("API_KEY")
SONARR_QUALITY_PROFILE_NAME = config.get("sonarr").get("QUALITY_PROFILE_NAME")
SONARR_ROOT_FOLDER_PATH = config.get("sonarr").get("ROOT_FOLDER_PATH")
RADARR_URL = config.get("radarr").get("URL")
RADARR_API_KEY = config.get("radarr").get("API_KEY")
RADARR_QUALITY_PROFILE_NAME = config.get("radarr").get("QUALITY_PROFILE_NAME")
RADARR_ROOT_FOLDER_PATH = config.get("radarr").get("ROOT_FOLDER_PATH")
LANGUAGE = config.get("tmdb").get("DEFAULT_LANGUAGE")

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
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS group_data (
                        id INTEGER PRIMARY KEY,
                        group_chat_id INTEGER,
                        language TEXT DEFAULT 'en'
                      )''')
    conn.commit()
    conn.close()

# Load group chat ID and language from database
def load_group_id():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT group_chat_id, language FROM group_data WHERE id=1")
    row = cursor.fetchone()
    conn.close()
    if row:
        logger.info(f"Loaded existing group chat ID: {row[0]}, language: {row[1]}")
        return row[0], row[1]
    return None, None

# Save group chat ID and language to database
def save_group_id(group_chat_id, language):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO group_data (id, group_chat_id, language) VALUES (1, ?, ?)", (group_chat_id, language))
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

# Get the current time in the desired timezone
def get_current_time():
    return datetime.datetime.now(TIMEZONE_OBJ)

async def add_media_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    media_info = context.user_data.get('media_info')

    if media_info:
        title = media_info['title']
        media_type = media_info['media_type']

        if update.message.text.lower() == 'sonarr':
            await add_series_to_sonarr(title)
            await update.message.reply_text(f"'{title}' has been added to Sonarr.")
        elif update.message.text.lower() == 'radarr':
            await add_movie_to_radarr(title)
            await update.message.reply_text(f"'{title}' has been added to Radarr.")
        else:
            await update.message.reply_text("Please reply with 'Sonarr' or 'Radarr'.")

        # Clear the media_info after processing
        context.user_data.pop('media_info', None)
    else:
        await update.message.reply_text("No media information found. Please search again.")

# Function to get quality profile ID by name from Sonarr
async def get_quality_profile_id(sonarr_url, api_key, profile_name):
    response = requests.get(f"{sonarr_url}/api/v3/qualityprofile", params={"apikey": api_key})
    response.raise_for_status()
    profiles = response.json()
    for profile in profiles:
        if profile['name'] == profile_name:
            return profile['id']
    return None

# Function to add a series to Sonarr
async def add_series_to_sonarr(series_name):
    quality_profile_id = await get_quality_profile_id(SONARR_URL, SONARR_API_KEY, SONARR_QUALITY_PROFILE_NAME)
    if quality_profile_id is None:
        logger.error("Quality profile not found in Sonarr.")
        return

    data = {
        "title": series_name,
        "qualityProfileId": quality_profile_id,
        "rootFolderPath": SONARR_ROOT_FOLDER_PATH,
        "seasonFolder": True,
        "tvdbId": 12345  # Example ID, replace as needed
    }

    response = requests.post(f"{SONARR_URL}/api/v3/series", json=data, params={"apikey": SONARR_API_KEY})
    response.raise_for_status()
    logger.info(f"Series '{series_name}' added to Sonarr.")

# Function to get quality profile ID by name from Radarr
async def get_radarr_quality_profile_id(radarr_url, api_key, profile_name):
    try:
        response = requests.get(f"{radarr_url}/api/v3/qualityprofile", params={"apikey": api_key})
        response.raise_for_status()  # Raise an error for bad responses
        profiles = response.json()
        
        for profile in profiles:
            if profile['name'] == profile_name:
                return profile['id']
                
        logger.warning(f"Quality profile '{profile_name}' not found in Radarr.")
        return None
        
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while fetching quality profiles: {http_err}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return None

# Function to add a movie to Radarr
async def add_movie_to_radarr(movie_name):
    quality_profile_id = await get_radarr_quality_profile_id(RADARR_URL, RADARR_API_KEY, RADARR_QUALITY_PROFILE_NAME)
    if quality_profile_id is None:
        logger.error("Quality profile not found for Radarr.")
        return

    data = {
        "title": movie_name,
        "qualityProfileId": quality_profile_id,
        "rootFolderPath": RADARR_ROOT_FOLDER_PATH,
        "isAvailable": True
    }

    response = requests.post(f"{RADARR_URL}/api/v3/movie", json=data, params={"apikey": RADARR_API_KEY})
    response.raise_for_status()
    logger.info(f"Movie '{movie_name}' added to Radarr.")


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

# Command to set the language
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LANGUAGE
    if context.args:
        LANGUAGE = context.args[0]
        save_group_id(GROUP_CHAT_ID, LANGUAGE)
        logger.info(f"Language set to: {LANGUAGE} by user {update.message.from_user.id}")
        await update.message.reply_text(f"Language set to: {LANGUAGE}")
    else:
        await update.message.reply_text("Please specify a language code (e.g., 'en', 'de').")

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

# Search for a movie or TV show using TMDB API
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not context.args:
            await update.message.reply_text("Please provide a title to search.")
            return

        title = " ".join(context.args)
        logger.info(f"Searching for media: {title}")
        
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language={LANGUAGE}"
        
        # Make the API request
        response = requests.get(url)
        
        # Check if the API key is invalid
        if response.status_code == 401:
            logger.error("Invalid TMDB API key.")
            await update.message.reply_text("❌ Invalid TMDB API key. Please contact the administrator.")
            return

        # Handle any other HTTP error
        response.raise_for_status()
        
        media_data = response.json()

        # Check if results are empty
        if not media_data['results']:
            await update.message.reply_text(f"No results found for the title '{title}'. Please try another title.")
            return

        # Get the first result
        media = media_data['results'][0]
        poster_url = f"https://image.tmdb.org/t/p/w500{media['poster_path']}" if media['poster_path'] else None
        rating = media.get('vote_average', 0)
        stars = '⭐' * int(rating) + '☆' * (5 - int(rating))

        media_type = media['media_type']
        message = (
            f"🎬**Title:** {media['title'] if media_type == 'movie' else media['name']}\n\n"
            f"📅**Release Date:** {media['release_date'] if media_type == 'movie' else media['first_air_date']}\n\n"
            f"⭐**Rating:** {stars} ({rating}/10)\n\n"
            f"📝**Summary:** {media['overview']}"
        )

        # Truncate the message if it exceeds the maximum length
        if len(message) > 1024:
            message = message[:1021] + '...'

        # Send the result with a poster image if available
        if poster_url:
            await update.message.reply_photo(photo=poster_url, caption=message, parse_mode="Markdown")
        else:
            await update.message.reply_text(message)

        # Ask if the user wants to add the media to Sonarr or Radarr
        if media_type in ['tv', 'movie']:
            await update.message.reply_text(
                f"Do you want to add this {'TV show' if media_type == 'tv' else 'movie'} to Sonarr or Radarr? Reply with 'Sonarr' or 'Radarr'."
            )
            context.user_data['media_info'] = {
                'title': media['title'] if media_type == 'movie' else media['name'],
                'media_type': media_type
            }

    except requests.exceptions.HTTPError as http_err:
        # Handle specific HTTP errors (e.g., 403 Forbidden, 404 Not Found)
        logger.error(f"HTTP error occurred: {http_err}")
        if response.status_code == 404:
            await update.message.reply_text("❌ The requested resource was not found. Please try again with a different title.")
        elif response.status_code == 403:
            await update.message.reply_text("❌ Access denied to the requested resource. Please check your API permissions.")
        else:
            await update.message.reply_text("❌ An HTTP error occurred while fetching data from TMDb. Please try again later.")
    except requests.exceptions.ConnectionError:
        # Handle network errors
        logger.error("A connection error occurred while contacting TMDb.")
        await update.message.reply_text("❌ A network error occurred. Please check your internet connection and try again.")
    except requests.exceptions.Timeout:
        # Handle timeout errors
        logger.error("The request to TMDb timed out.")
        await update.message.reply_text("❌ The request to TMDb timed out. Please try again later.")
    except requests.exceptions.RequestException as e:
        # Handle any other errors (generic requests error)
        logger.error(f"An error occurred: {e}")
        await update.message.reply_text("❌ An error occurred while fetching data. Please try again later.")
    except Exception as e:
        # Catch any other general errors
        logger.error(f"An unexpected error occurred: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again later.")


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
is_night_mode_checking = False  # Flag to track if the job is already running

async def night_mode_checker(context):
    global night_mode_active

    logger.info("Night mode checker running...")
    
    now = get_current_time()  # Get the current time in the specified timezone

    # Check for night mode activation
    if now.hour == 0 and not night_mode_active:
        night_mode_active = True
        logger.info("Night mode activated.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff braucht auch mal eine Pause.")
        
    # Check for night mode deactivation
    elif now.hour == 7 and night_mode_active:
        night_mode_active = False
        logger.info("Night mode deactivated.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="☀️ ENDE DES NACHTMODUS.\n\n✅ Ab jetzt kannst du wieder Mitteilungen in der Gruppe senden.")



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
    application.add_handler(CommandHandler("set_language", set_language))
    application.add_handler(CommandHandler("enable_night_mode", enable_night_mode))
    application.add_handler(CommandHandler("disable_night_mode", disable_night_mode))
    application.add_handler(CommandHandler("search", search_media))

    # Register the message handler for new members
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))

    # Register the message handler for general messages (to restrict during night mode)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, restrict_night_mode))

    # Register the message handler for user responses to add media
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_media_response))


    # Start the night mode checker task with max_instances set to 1
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
    except Exception as e:
        logger.error(f"An unexpected error occurred during startup: {e}")

import asyncio
import nest_asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os
import sqlite3
import re
import logging
import requests
import time
import aiohttp
from telegram.constants import ChatAction
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import signal
import sys

# Check ist conig.json is present..
CONFIG_DIR = "config"
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

if not os.path.isfile(CONFIG_FILE):
    print(f"ERROR: '{CONFIG_FILE}' not found. Please create the configuration file before starting the bot.")
    sys.exit(1)  # Exit with status code 1

# Function to redact sensitive information like tokens and API keys
def redact_sensitive_info(value, visible_chars=4):
    if isinstance(value, str) and len(value) > visible_chars * 2:
        return f"{value[:visible_chars]}{'*' * (len(value) - visible_chars * 2)}{value[-visible_chars:]}"
    return value

# Apply nest_asyncio to handle running loops
nest_asyncio.apply()

# Global reference for the application instance
application = None

# Shutdown handler to gracefully close the event loop
async def shutdown(signal_name):
    logger.info(f"Received {signal_name}, shutting down the bot...")
    if application:
        await application.shutdown()  # Shutdown Telegram application safely
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)  # Wait for all tasks to finish
    await asyncio.sleep(0.1)  # Give some time for tasks to properly finish
    logger.info("Bot has been shut down successfully.")

# Function to load version and author info from a file
def load_version_info(file_path):
    version_info = {}
    try:
        with open(file_path, 'r') as file:
            for line in file:
                key, value = line.strip().split(': ', 1)  # Split on first colon and space
                version_info[key] = value
    except Exception as e:
        logger.error(f"Failed to load version info: {e}")
    return version_info

# Function to check and log paths
async def check_and_log_paths():
    # Check if config directory exists
    logger.info(f"Checking directories.....")
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        await log_message_async("")
        logger.warning(f"Config directory '{CONFIG_DIR}' not found.")
        logger.info(f"Creating config directory....")
        logger.info(f"Directory {CONFIG_DIR} created.")
        await log_message_async("")
    else:
        logger.info(f"Config directory '{CONFIG_DIR}' already exists.")
    
    # Check if database directory exists
    if not os.path.exists(DATABASE_DIR):
        os.makedirs(DATABASE_DIR)
        await log_message_async("")
        logger.warning(f"Database directory '{DATABASE_DIR}' not found.")
        logger.info(f"Creating database directory....")
        logger.info(f"Directory {DATABASE_DIR} created.")
        await log_message_async("")
    else:
        logger.info(f"Config directory '{DATABASE_DIR}' already exists.")

    # Check if database file exists
    if not os.path.exists(DATABASE_FILE):
        logger.warning(f"Database file '{DATABASE_FILE}' does not exist. It will be created automatically.")
    else:
        logger.info(f"Database file '{DATABASE_FILE}' already exists.")

# Load bot configuration from config/config.json
CONFIG_DIR = "config"
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

# Path for SQLite database file in the backup folder
DATABASE_DIR = "database"
DATABASE_FILE = os.path.join(DATABASE_DIR, "group_data.db")

with open(CONFIG_FILE, 'r') as config_file:
    config = json.load(config_file)

# BOT
TOKEN = config.get("bot").get("TOKEN")
TIMEZONE = config.get("bot").get("TIMEZONE", "Europe/Berlin")
LOG_LEVEL = config.get("bot").get("LOG_LEVEL", "INFO").upper()
# WELCOME
IMAGE_URL = config.get("welcome").get("IMAGE_URL")
BUTTON_URL = config.get("welcome").get("BUTTON_URL")
# TMDB
TMDB_API_KEY = config.get("tmdb").get("API_KEY")
DEFAULT_LANGUAGE = config.get("tmdb").get("DEFAULT_LANGUAGE")
# SONARR
SONARR_URL = config.get("sonarr").get("URL")
SONARR_API_KEY = config.get("sonarr").get("API_KEY")
SONARR_QUALITY_PROFILE_NAME = config.get("sonarr").get("QUALITY_PROFILE_NAME")
SONARR_ROOT_FOLDER_PATH = config.get("sonarr").get("ROOT_FOLDER_PATH")
# RADARR
RADARR_URL = config.get("radarr").get("URL")
RADARR_API_KEY = config.get("radarr").get("API_KEY")
RADARR_QUALITY_PROFILE_NAME = config.get("radarr").get("QUALITY_PROFILE_NAME")
RADARR_ROOT_FOLDER_PATH = config.get("radarr").get("ROOT_FOLDER_PATH")
# COMMANDS
START_COMMAND = config.get("commands").get("START", "start")
WELCOME_COMMAND = config.get("commands").get("WELCOME", "welcome")
NIGHT_MODE_ENABLE_COMMAND = config.get("commands").get("NIGHT_MODE_ENABLE", "enable_night_mode")
NIGHT_MODE_DISABLE_COMMAND = config.get("commands").get("NIGHT_MODE_DISABLE", "disable_night_mode")
TMDB_LANGUAGE_COMMAND = config.get("commands").get("TMDB_LANGUAGE", "set_language")
SET_GROUP_ID_COMMAND = config.get("commands").get("SET_GROUP_ID", "set_group_id")
HELP_COMMAND = config.get("commands").get("HELP", "help")
SEARCH_COMMAND = config.get("commands").get("SEARCH", "search")

# Set LOG_LEVEL dynamically or use a default value if not set (e.g., 'INFO')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Create the root logger and set its level
logger = logging.getLogger("custom_logger")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# Create console handler with detailed format
console_handler = logging.StreamHandler()
console_format = logging.Formatter('[%(asctime)s] [%(levelname)s]   %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(console_format)
logger.addHandler(console_handler)

# Create an asyncio lock for sequential logging
log_lock = asyncio.Lock()

# Modify the log_message function to use the asyncio lock
async def log_message_async(message):
    """Log a message with asyncio lock to maintain order."""
    async with log_lock:
        print(message)
        sys.stdout.flush()  # Ensure the message is flushed to the console immediately


def log_message(message):
    """Print a plain text message without log level or metadata."""
    #print(f"DEBUG: log_message called with: {message}")  # Debug print
    print(message, flush=True)  # Actual message print


# Log all config entries, redacting sensitive information
async def log_config_entries(config):
    sensitive_keys = ['TOKEN', 'API_KEY', 'SECRET', 'KEY']  # Keys to redact
    await log_message_async("=====================================================")
    await log_message_async("")
    logger.info("Logging all configuration entries:")
    await log_message_async(f"")
    
    for section, entries in config.items():
        if isinstance(entries, dict):
            logger.info(f"Section [{section}]:")
            for key, value in entries.items():
                if any(sensitive_key in key.upper() for sensitive_key in sensitive_keys):
                    value = redact_sensitive_info(value)
                logger.info(f"  {key}: {value}")
        else:
            logger.info(f"{section}: {entries}")
    await log_message_async("")
    await log_message_async("=====================================================")

def configure_bot(TOKEN, TIMEZONE="Europe/Berlin"):
    """
    Configures the bot by logging the token and setting up the timezone.

    Parameters:
    - TOKEN (str): The bot token.
    - TIMEZONE (str): Timezone string for the bot. Defaults to 'Europe/Berlin'.

    Returns:
    - TIMEZONE_OBJ (ZoneInfo): Configured timezone object.
    """
    # Log the successful retrieval of the token with only the first and last 4 characters visible
    if TOKEN:
        redacted_token = redact_sensitive_info(TOKEN)
        logger.info(f"Token retrieved: {redacted_token}")
    else:
        logger.error(f"Failed to retrieve bot token from config. <-----")
        raise ValueError("Bot token is missing or invalid.")

    # Timezone configuration
    try:
        TIMEZONE_OBJ = ZoneInfo(TIMEZONE)
        logger.info(f"Timezone is set to '{TIMEZONE}'.")
    except Exception as e:
        log_message("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.error(f"Invalid timezone '{TIMEZONE}' in config.json. <-----")
        log_message("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.error(f"Defaulting to 'Europe/Berlin'. Error: {e}")
        TIMEZONE_OBJ = ZoneInfo("Europe/Berlin")

    return TIMEZONE_OBJ

# Initialize SQLite connection and create table for storing group ID and language
def init_db():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        # Create the table without a default value
        cursor.execute('''CREATE TABLE IF NOT EXISTS group_data (
                            id INTEGER PRIMARY KEY,
                            group_chat_id INTEGER,
                            language TEXT
                          )''')
        
        # Check if the column is empty and update with the dynamic default value
        default_language = config.get("tmdb").get("DEFAULT_LANGUAGE")
        cursor.execute('''UPDATE group_data SET language = ? WHERE language IS NULL''', (default_language,))
        
        conn.commit()

# Load group chat ID and language from database
def load_group_id():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT group_chat_id, language FROM group_data WHERE id=1")
        row = cursor.fetchone()
    if row:
        return row[0], row[1]
    return None, DEFAULT_LANGUAGE

# Log group_id and language if present
def log_group_id():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT group_chat_id, language FROM group_data WHERE id=1")
        row = cursor.fetchone()
    if row:
        logger.info(f"Loaded existing Group Chat ID: {row[0]}")
        logger.info(f"Loaded existing Tmdb Language: {row[1]}")
        log_message("=====================================================")
        return row[0], row[1]
    return None, DEFAULT_LANGUAGE

LANGUAGE = DEFAULT_LANGUAGE

# Save group chat ID and language to database
def save_group_id(group_chat_id, language):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO group_data (id, group_chat_id, language) VALUES (1, ?, ?)", (group_chat_id, language))
        conn.commit()

# Global variable to track if night mode is active
night_mode_active = False
# Define global locks
night_mode_lock = asyncio.Lock()
task_lock = asyncio.Lock()

# Timezone configuration
try:
    TIMEZONE_OBJ = ZoneInfo(TIMEZONE)
except Exception as e:
    TIMEZONE_OBJ = ZoneInfo("Europe/Berlin")

# Get the current time in the desired timezone
def get_current_time():
    return datetime.now(TIMEZONE_OBJ)

# Avoid issues with special characters in MarkdownV2
# Function to escape special characters for MarkdownV2
def escape_markdown_v2(text):
    escape_chars = r'([_*\[\]()~`>#+\-=|{}.!])'
    return re.sub(escape_chars, r'\\\1', text)

# Function to check if the series is already in Sonarr
async def check_series_in_sonarr(series_tvdb_id):
    """Check if the series is already in Sonarr by TVDB ID."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SONARR_URL}/api/v3/series", params={"apikey": SONARR_API_KEY}) as response:
                series_list = await response.json()

        for series in series_list:
            if series['tvdbId'] == series_tvdb_id:
                logger.info(f"Series '{series['title']}' already exists in Sonarr (TVDB ID: {series['tvdbId']})")
                return True
        return False

    except aiohttp.ClientError as http_err:
        logger.error(f"HTTP error while checking Sonarr: {http_err}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while checking Sonarr: {e}")
        return False

# Function to check if the movie is already in Radarr
async def check_movie_in_radarr(movie_tmdb_id):
    """Check if the movie is already in Radarr by TMDb ID."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{RADARR_URL}/api/v3/movie", params={"apikey": RADARR_API_KEY}) as response:
                movie_list = await response.json()

        for movie in movie_list:
            if movie['tmdbId'] == movie_tmdb_id:
                logger.info(f"Movie '{movie['title']}' already exists in Radarr.")
                return True
        return False

    except aiohttp.ClientError as http_err:
        logger.error(f"HTTP error while checking Radarr: {http_err}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while checking Radarr: {e}")
        return False

# Add media to Sonarr or Radarr after user confirmation
async def add_media_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    media_info = context.user_data.get('media_info')
    
    if media_info:
        title = media_info['title']
        media_type = media_info['media_type']

        # Show typing indicator while adding the media
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible

        # Check whether the update is from a normal message or a callback query
        #if update.message:
        #    status_message = await update.message.reply_text("👀 Anfrage läuft, bitte warten...")
        #else:
        #    status_message = await update.callback_query.message.reply_text("👀 Anfrage läuft, bitte warten...")

        # Handle TV shows (Sonarr) or movies (Radarr)
        if media_type == 'tv':
            await add_series_to_sonarr(title, update, context)
            #await status_message.edit_text(f"Die Serie *{title}* wurde angefragt.", parse_mode="Markdown")
        elif media_type == 'movie':
            await add_movie_to_radarr(title, update, context)
            #await status_message.edit_text(f"Der Film *{title}* wurde angefragt.", parse_mode="Markdown")
        else:
        # If no media_info found, send a message about the missing metadata
         if update.message:
            await update.message.reply_text("Unerwarteter Fehler aufgetreten. Bitte versuche es erneut.")
         else:
            await update.callback_query.message.reply_text("Unerwarteter Fehler aufgetreten. Bitte versuche es erneut.")

        # Clear media_info after adding the media
        context.user_data.pop('media_info', None)
    else:
        # If no media_info found, send a message about the missing metadata
        if update.message:
            await update.message.reply_text("Keine Metadaten Ergebnisse gefunden. Bitte versuche es erneut.")
        else:
            await update.callback_query.message.reply_text("Keine Metadaten Ergebnisse gefunden. Bitte versuche es erneut.")

# Function to fetch additional details of the movie/TV show from TMDb
async def fetch_media_details(media_type, media_id):
    """Fetch detailed media information including poster, rating, summary, etc."""
    url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&language={LANGUAGE}"
    logger.info(f"Fetching details from URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            media_details = await response.json()

    logger.info(f"Details fetched successfully for media_id: {media_id}")
    return media_details

def rating_to_stars(rating):
    """Convert a TMDb rating (out of 10) to a 10-star emoji string."""
    # Convert the rating to a 5-star scale
    stars = (rating / 10) * 10

    # Determine the number of full stars, half stars, and empty stars
    full_stars = int(stars)  # Full stars
    half_star = 1 if stars - full_stars >= 0.5 else 0  # Half star
    empty_stars = 10 - full_stars - half_star  # Empty stars

    # Build the star emoji string
    star_display = "⭐" * full_stars + "✨" * half_star + "★" * empty_stars
    return star_display

def extract_year_from_input(selected_title):
    """Extract the year from the user's input and ensure the format is correct."""
    # Use regex to find a year in parentheses, even if the parentheses are incomplete
    match = re.search(r'\((\d{4})', selected_title)
    if match:
        # Ensure the closing parenthesis is present and return the title up to the year
        return f"{selected_title[:match.end()]})"
    return selected_title  # If no year is found, return the original title

# Handle the user's media selection and display media details before confirming
async def handle_media_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    # Get the user's selected media from user_data
    media = context.user_data.get('selected_media')
    if not media:
        await update.callback_query.message.reply_text("Ungültige Auswahl. Bitte versuche es erneut.")
        logger.error("No selected media found in user data.")
        return

    # Show the typing indicator while the bot is working
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible

    # Send a progress message
    status_message = await update.callback_query.message.reply_text("📄 Metadaten werden geladen, bitte warten...")

    media_title = media['title'] if media['media_type'] == 'movie' else media['name']
    media_type = media['media_type']
    media_id = media['id']

    # Fetch additional media details from TMDb
    try:
        media_details = await fetch_media_details(media_type, media_id)
        logger.info(f"Fetched media details for {media_title} (TMDb ID: {media_id})")
    except Exception as e:
        await status_message.edit_text("Fehler beim Laden der Metadaten. Bitte versuche es später erneut.")
        logger.error(f"Failed to fetch media details: {e}")
        return

    # Convert rating to stars using the helper function
    rating = media_details.get('vote_average', 0)
    star_rating = rating_to_stars(rating)

    # Extract the year from the release date for the detailed message as well
    full_release_date = media_details.get('release_date', media_details.get('first_air_date', 'N/A'))
    release_year_detailed = full_release_date[:4] if full_release_date != 'N/A' else 'N/A'

    # Generate the TMDb URL
    tmdb_url = f"https://www.themoviedb.org/{'movie' if media_type == 'movie' else 'tv'}/{media_id}"

    # Prepare the message with media details, star rating, and the TMDb URL
    message = (
        f"🎬 *{media_title}* ({release_year_detailed}) \n\n"
        f"{star_rating} - {rating}/10\n\n"
        f"{media_details.get('overview', 'No summary available.')}\n\n"
        f"[Weitere Infos bei TMDb]({tmdb_url})"  # Adding the TMDb URL link at the bottom
    )

    # Send media details regardless of existence in Sonarr/Radarr
    if media_details.get('poster_path'):
        poster_url = f"https://image.tmdb.org/t/p/w500{media_details['poster_path']}"
        await status_message.edit_text(text="🎬 Metadaten geladen!", parse_mode="Markdown")
        await update.callback_query.message.reply_photo(photo=poster_url, caption=message, parse_mode="Markdown")
    else:
        await status_message.edit_text(text=message, parse_mode="Markdown")

    # Now check if the media already exists in Radarr or Sonarr
    # Send status message that it's checking if the media exists
    checking_status_message = await update.callback_query.message.reply_text("👀 Überprüfe, ob der Titel bereits vorhanden ist...")

    if media_type == 'movie':
        if await check_movie_in_radarr(media_id):
            await checking_status_message.edit_text(
                text=f"✅ Der Film *{media_title}* ist bereits bei StreamNet TV vorhanden.", 
                parse_mode="Markdown"
            )
        else:
            # Update the status message to indicate the media is being added
            await checking_status_message.edit_text("‼️ Titel wurde nicht gefunden...")

            # Ask the user whether they want to add the media
            await ask_to_add_media(update, context, media_title, 'movie')

            # Store media information for later confirmation
            context.user_data['media_info'] = {'title': media_title, 'media_type': 'movie'}
    elif media_type == 'tv':
        external_ids_url = f"https://api.themoviedb.org/3/tv/{media_id}/external_ids?api_key={TMDB_API_KEY}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(external_ids_url) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to fetch external IDs, status code: {response.status}")
                    external_ids_data = await response.json()
        except Exception as e:
            await checking_status_message.edit_text(
                text=f"🆘 Fehler beim Abrufen der TVDB ID für die Serie *{media_title}*. {str(e)}", 
                parse_mode="Markdown"
            )
            logger.error(f"Error fetching external IDs for series '{media_title}': {e}")
            return

        tvdb_id = external_ids_data.get('tvdb_id')
        if not tvdb_id:
            await checking_status_message.edit_text(
                text=f"🆘 Keine TVDB ID gefunden für die Serie *{media_title}*.", 
                parse_mode="Markdown"
            )
            logger.error(f"No TVDB ID found for the series '{media_title}'")
            return

        if await check_series_in_sonarr(tvdb_id):
            await checking_status_message.edit_text(
                text=f"✅ Die Serie *{media_title}* ist bereits bei StreamNet TV vorhanden.", 
                parse_mode="Markdown"
            )
        else:
            # Update the status message to indicate the media is being added
            await checking_status_message.edit_text("‼️ Titel wurde nicht gefunden...")

            # Ask the user whether they want to add the media
            await ask_to_add_media(update, context, media_title, 'tv')

            # Store media information for later confirmation
            context.user_data['media_info'] = {'title': media_title, 'media_type': 'tv', 'tvdb_id': tvdb_id}

# Search for a movie or TV show using TMDB API with multiple results handling
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not context.args:
            await update.message.reply_text("Bitte ergänze den Befehl mit einem Film oder Serien Titel (e.g., /search Inception).")
            return

        title = " ".join(context.args)
        logger.info(f"Searching for media: {title}")

        # Show the typing indicator while the bot is working
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible

        # Send a progress message
        status_message = await update.message.reply_text("🔍 Suche nach Ergebnissen, bitte warten....")

        # Actual processing logic (searching media)
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language={LANGUAGE}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(f"Rate limited by TMDb. Retrying after {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                    async with session.get(url) as retry_response:
                        media_data = await retry_response.json()
                else:
                    media_data = await response.json()

        if not media_data['results']:
            await status_message.edit_text(
                text=f"🆘 Keine Ergebnisse gefunden für *{title}*. Bitte versuche einen anderen Titel.",
                parse_mode="Markdown"
            )
            return

        # If more than one result is found, show a list to the user
        if len(media_data['results']) > 1:
            media_titles = []
            keyboard = []
            for i, media in enumerate(media_data['results']):
                media_type = media['media_type']
                media_title = media['title'] if media_type == 'movie' else media['name']
                release_date = media.get('release_date', media.get('first_air_date', 'N/A'))
                release_year = release_date[:4] if release_date != 'N/A' else 'N/A'
                
                # Use the index to generate callback data for InlineKeyboard
                media_titles.append(f"{media_title} ({release_year})")
                keyboard.append([InlineKeyboardButton(f"{media_title} ({release_year})", callback_data=f"select_media_{i}")])

            # Create the InlineKeyboardMarkup with the list of results
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await status_message.edit_text(
                 "Mehrere Ergebnisse gefunden, bitte wähle den richtigen Film oder Serie aus:",
                 reply_markup=reply_markup
            )

            # Store media results in user data for later selection
            context.user_data['media_options'] = media_data['results']
            logger.info(f"Media options stored: {len(media_data['results'])} results")
            return

        # If only one result, continue with displaying details and confirmation
        media = media_data['results'][0]
        await handle_media_selection(update, context, media)

    except aiohttp.ClientError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        await status_message.edit_text("🆘 Ein HTTP Fehler ist beim laden der Metadaten von TMDB aufgetreten. Bitte versuche es später erneut.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await status_message.edit_text("🆘 Ein unerwarteter Fehler ist aufgetreten. Bitte versuche es später erneut.")

# Handle user's confirmation (yes/no)
async def handle_user_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    media_info = context.user_data.get('media_info')

    if media_info:

        # Show typing indicator while adding the movie
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        # Allow the typing indicator to be shown for a short period
        await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible


        if update.message.text.lower() == 'yes':
            await add_media_response(update, context)
        elif update.message.text.lower() == 'no':
            await update.message.reply_text("Anfrage beendet. Der Titel wurde nicht angefordert.")
            context.user_data.pop('media_info', None)
        else:
            await update.message.reply_text("Bitte antworte mit 'yes' oder 'no'.")
    else:
        await update.message.reply_text("Kein Film oder Serie angegeben. Bitte suche zuerst nach einem Film oder Serie.")

# Function to ask the user whether they want to add media
async def ask_to_add_media(update: Update, context: ContextTypes.DEFAULT_TYPE, media_title: str, media_type: str):

    # Show typing indicator while adding the movie
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible

    # Create "Yes" and "No" buttons
    keyboard = [
        [
            InlineKeyboardButton("Ja", callback_data=f"add_{media_type}_yes"),
            InlineKeyboardButton("Nein", callback_data=f"add_{media_type}_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    media_title_escaped = escape_markdown_v2(media_title)

    # Check if the message is coming from a callback query or a normal update
    if update.message:
        # This handles a regular message update
        await update.message.reply_text(
            f"Willst du *{media_title}* anfragen?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        # This handles a callback query
        await update.callback_query.message.reply_text(
            f"Willst du *{media_title}* anfragen?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

# Handle the user's choice when they press an InlineKeyboard button
async def handle_add_media_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Extract the media index from callback data (e.g., "select_media_0")
    callback_data = query.data
    if callback_data.startswith("select_media_"):
        media_index = int(callback_data.split("_")[-1])
        media_options = context.user_data.get('media_options', None)

        if media_options and 0 <= media_index < len(media_options):
            # Proceed with the selected media
            context.user_data['selected_media'] = media_options[media_index]
            await handle_media_selection(update, context)
        else:
            await query.edit_message_text("Ungültige Auswahl. Bitte versuche es erneut.")
            logger.error("Media selection did not match any option.")
    else:
        # Handle other types of callbacks (e.g., yes/no for adding media)
        media_info = context.user_data.get('media_info')

        if media_info:
            media_title = media_info['title']
            media_type = media_info['media_type']

            if callback_data == f"add_{media_type}_yes":
                await add_media_response(update, context)
            elif callback_data == f"add_{media_type}_no":
                await query.edit_message_text(f"Anfrage von *{media_title}* wurde abgebrochen.", parse_mode="Markdown")
                context.user_data.pop('media_info', None)

# Message handler for general text
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    # Show typing indicator while adding the movie
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    # Allow the typing indicator to be shown for a short period
    await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible


    if context.user_data.get('media_info'):
        # Handle user confirmation for adding media to Sonarr or Radarr
        await handle_user_confirmation(update, context)
    elif context.user_data.get('media_options'):
        # Handle media selection if options were provided
        await handle_media_selection(update, context)
    else:
        # Handle other general messages
        if night_mode_active or await night_mode_checker(context):
            await restrict_night_mode(update, context)

# Function to get quality profile ID by name from Sonarr
async def get_quality_profile_id(sonarr_url, api_key, profile_name):
    try:
        response = requests.get(f"{sonarr_url}/api/v3/qualityprofile", params={"apikey": api_key})
        response.raise_for_status()
        profiles = response.json()

        for profile in profiles:
            if profile['name'] == profile_name:
                return profile['id']
    
        logger.warning(f"Quality profile '{profile_name}' not found in Sonarr.")
        return None
  
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while fetching quality profiles: {http_err}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return None

# Function to add a series to Sonarr
async def add_series_to_sonarr(series_name, update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Show typing indicator while adding the series
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible

    # Determine where to send the status message (handling both update.message and update.callback_query)
    if update.message:
        status_message = await update.message.reply_text("🎬 Serien Anfrage läuft, bitte warten...")
    else:
        status_message = await update.callback_query.message.reply_text("🎬 Serien Anfrage läuft, bitte warten...")

    # First, get the TMDb ID for the series
    tmdb_url = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={series_name}"
    async with aiohttp.ClientSession() as session:
        async with session.get(tmdb_url) as tmdb_response:
            tmdb_data = await tmdb_response.json()

    if not tmdb_data['results']:
        logger.error(f"No TMDb results found for the series '{series_name}'")
        await status_message.edit_text(f"🆘 Keine TMDB Ergebnisse für die Serie *{series_name}* gefunden.", parse_mode="Markdown")
        return

    # Use the first search result for simplicity
    series_tmdb_id = tmdb_data['results'][0]['id']

    # Use TMDb ID to get TVDB ID (Sonarr uses TVDB)
    external_ids_url = f"https://api.themoviedb.org/3/tv/{series_tmdb_id}/external_ids?api_key={TMDB_API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.get(external_ids_url) as external_ids_response:
            external_ids_data = await external_ids_response.json()

    tvdb_id = external_ids_data.get('tvdb_id')
    if not tvdb_id:
        logger.error(f"No TVDB ID found for the series '{series_name}'")
        await status_message.edit_text(f"🆘 Keine TVDB ID für die Serie *{series_name}* gefunden.", parse_mode="Markdown")
        return

    # Check if the series is already in Sonarr
    if await check_series_in_sonarr(tvdb_id):
        logger.info(f"Series '{series_name}' already exists in Sonarr, skipping addition.")
        await status_message.edit_text(f"✅ Die Serie *{series_name}* ist bereits bei StreamNet TV vorhanden.", parse_mode="Markdown")
        return

    # Proceed with adding the series if it's not found in Sonarr
    quality_profile_id = await get_quality_profile_id(SONARR_URL, SONARR_API_KEY, SONARR_QUALITY_PROFILE_NAME)
    if quality_profile_id is None:
        logger.error("Quality profile not found in Sonarr.")
        await status_message.edit_text("🆘 Quality Profil in Sonarr nicht gefunden.")
        return

    data = {
        "title": series_name,
        "qualityProfileId": quality_profile_id,
        "rootFolderPath": SONARR_ROOT_FOLDER_PATH,
        "seasonFolder": True,
        "tvdbId": tvdb_id,
        "monitored": True,
        "addOptions": {
            "searchForMissingEpisodes": True  # Attempt to trigger search via addOptions
        }
    }
     
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{SONARR_URL}/api/v3/series", json=data, params={"apikey": SONARR_API_KEY}) as response:
            if response.status == 201:
                logger.info(f"Series '{series_name}' added to Sonarr successfully.")

                series_id = (await response.json()).get('id')

                if not (await response.json()).get('addOptions', {}).get('searchForMissingEpisodes', False):
                    logger.info(f"Triggering manual search for series '{series_name}'.")
                    search_data = {"name": "SeriesSearch", "seriesId": series_id}
                    async with session.post(f"{SONARR_URL}/api/v3/command", json=search_data, params={"apikey": SONARR_API_KEY}) as search_response:
                        if search_response.status == 201:
                            logger.info(f"Manual search for series '{series_name}' started.")
                            await status_message.edit_text(f"✅ Die Serie *{series_name}* wurde angefragt. Manuelle Suche wurde gestartet.", parse_mode="Markdown")
                        else:
                            logger.error(f"Failed to start manual search for series '{series_name}'. Status code: {search_response.status_code}")
                            await status_message.edit_text(f"🆘 Suche für die Serie *{series_name}* gescheitert.", parse_mode="Markdown")
                else:
                    logger.info(f"Search for series '{series_name}' started automatically.")
                    await status_message.edit_text(f"✅ Die Serie *{series_name}* wurde angefragt und die Suche wurde gestartet.", parse_mode="Markdown")
            else:
                logger.error(f"Failed to add series '{series_name}' to Sonarr. Status code: {response.status}")
                await status_message.edit_text(f"🆘 Anfragen der Serie *{series_name}* gescheitert.\nStatus code: *{response.status_code}*", parse_mode="Markdown")

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
async def add_movie_to_radarr(movie_name, update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Show typing indicator while adding the movie
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(0.5)  # Small delay to make sure the typing action is visible

    # Determine where to send the status message (handling both update.message and update.callback_query)
    if update.message:
        status_message = await update.message.reply_text("🎬 Film Anfrage läuft, bitte warten...")
    else:
        status_message = await update.callback_query.message.reply_text("🎬 Film Anfrage läuft, bitte warten...")

    # First, get the TMDb ID for the movie
    tmdb_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    async with aiohttp.ClientSession() as session:
        async with session.get(tmdb_url) as tmdb_response:
            tmdb_data = await tmdb_response.json()

    if not tmdb_data['results']:
        logger.error(f"No TMDb results found for the movie '{movie_name}'")
        await status_message.edit_text(f"🆘 Keine TMDB Ergebnisse für den Film *{movie_name}* gefunden.", parse_mode="Markdown")
        return

    # Use the first search result for simplicity
    movie_tmdb_id = tmdb_data['results'][0]['id']

    # Check if the movie is already in Radarr
    if await check_movie_in_radarr(movie_tmdb_id):
        logger.info(f"Movie '{movie_name}' already exists in Radarr, skipping addition.")
        await status_message.edit_text(f"✅ Der Film *{movie_name}* ist bereits bei StreamNet TV vorhanden.", parse_mode="Markdown")
        return

    # Proceed with adding the movie if it's not found in Radarr
    quality_profile_id = await get_radarr_quality_profile_id(RADARR_URL, RADARR_API_KEY, RADARR_QUALITY_PROFILE_NAME)
    if quality_profile_id is None:
        logger.error("Quality profile not found in Radarr.")
        await status_message.edit_text("🆘 Quality Profil in Radarr nicht gefunden.")
        return

    data = {
        "title": movie_name,
        "qualityProfileId": quality_profile_id,
        "rootFolderPath": RADARR_ROOT_FOLDER_PATH,
        "tmdbId": movie_tmdb_id,
        "monitored": True,
        "addOptions": {
            "searchForMovie": True  # Attempt to trigger search via addOptions
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{RADARR_URL}/api/v3/movie", json=data, params={"apikey": RADARR_API_KEY}) as response:
            if response.status == 201:
                logger.info(f"Movie '{movie_name}' added to Radarr successfully.")

                movie_id = (await response.json()).get('id')

                if not (await response.json()).get('addOptions', {}).get('searchForMovie', False):
                    logger.info(f"Triggering manual search for movie '{movie_name}'.")
                    search_data = {"name": "MoviesSearch", "movieIds": [movie_id]}
                    async with session.post(f"{RADARR_URL}/api/v3/command", json=search_data, params={"apikey": RADARR_API_KEY}) as search_response:
                        if search_response.status == 201:
                            logger.info(f"Manual search for movie '{movie_name}' started.")
                            await status_message.edit_text(f"✅ Der Film *{movie_name}* wurde angefragt. Manuelle Suche wurde gestartet.", parse_mode="Markdown")
                        else:
                            logger.error(f"Failed to start manual search for movie '{movie_name}'. Status code: {search_response.status_code}")
                            await status_message.edit_text(f"🆘 Suche für den Film *{movie_name}* gescheitert.", parse_mode="Markdown")
                else:
                    logger.info(f"Search for movie '{movie_name}' started automatically.")
                    await status_message.edit_text(f"✅ Der Film *{movie_name}* wurde angefragt und die Suche wurde gestartet.", parse_mode="Markdown")
            else:
                logger.error(f"Failed to add movie '{movie_name}' to Radarr. Status code: {response.status}")
                await status_message.edit_text(f"🆘 Anfragen des Films *{movie_name}* gescheitert.\nStatus code: *{response.status_code}*", parse_mode="Markdown")

# Command to set the group ID
async def set_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global GROUP_CHAT_ID
    GROUP_CHAT_ID = update.message.chat_id
    save_group_id(GROUP_CHAT_ID, LANGUAGE)
    logger.info(f"Group chat ID set to: {GROUP_CHAT_ID} by user {update.message.from_user.id}")
    await update.message.reply_text(f"Group chat ID set to: {GROUP_CHAT_ID}")

# Enable or disable night mode
async def enable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if not night_mode_active:
        night_mode_active = True
        logger.info(f"Night mode enabled by user {update.message.from_user.id}.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff Team braucht auch mal eine Pause 😴😪🥱💤🛌🏼")

async def disable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if night_mode_active:
        night_mode_active = False
        logger.info(f"Night mode disabled by user {update.message.from_user.id}.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="☀️ ENDE DES NACHTMODUS.\n\n✅ Ab jetzt kannst du wieder Mitteilungen in der Gruppe senden.")

# Night mode checker
async def night_mode_checker(context):
    global night_mode_active
    now = get_current_time()
    logger.info(f"Current time (UTC+2): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Night mode checker started")
    if now.hour == 0 and not night_mode_active:
        night_mode_active = True
        logger.info("Night mode activated at midnight.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, 
                                       text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff Team braucht auch mal eine Pause 😴😪🥱💤🛌🏼")
    elif now.hour == 7 and night_mode_active:
        night_mode_active = False
        logger.info("Night mode deactivated at 7:00 AM.")
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, 
                                       text="☀️ ENDE DES NACHTMODUS.\n\n✅ Ab jetzt kannst du wieder Mitteilungen in der Gruppe senden.")
    logger.info(f"Night mode checker finished")

# Restrict messages during night mode
async def restrict_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = get_current_time()
    if night_mode_active:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin = member.status in ('administrator', 'creator')
        if not is_admin:
            logger.info(f"Deleting message from non-admin user {update.message.from_user.id} due to night mode.")
            await update.message.reply_text("🆘 Sorry, solange der NACHTMODUS aktiviert ist (00:00 - 07:00 Uhr), kannst du keine Mitteilungen in der Gruppe oder in den Topics senden.")
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)

# Command to set the language for TMDB searches
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LANGUAGE
    if context.args:
        language_code = context.args[0]
        if len(language_code) == 2:
            LANGUAGE = language_code
            save_group_id(GROUP_CHAT_ID, LANGUAGE)
            logger.info(f"Language set to: {LANGUAGE} by user {update.message.from_user.id}")
            await update.message.reply_text(f"TMDB Language gesetzt: {LANGUAGE}")
        else:
            await update.message.reply_text("Ungültiger Language Code. Bitte benutze Language Code (e.g., 'en', 'de').")
    else:
        await update.message.reply_text("Bitte gebe einen TMDB Language Code ein (e.g., 'en', 'de').")

# Function to welcome new members
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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Help command function
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Hier sind die Befehle, die du verwenden kannst:\n\n"
        "/start  - Willkommensnachricht\n"
        #"/welcome [user]  - Manuelle Willkommensnachricht beim Beitritt (standard: auto)\n"
        "/set_group_id  - Setze die Gruppen-ID (für den Nachtmodus)\n"
        "/set_language [code]  - TMDB-Sprache für Mediensuche (standard: eng)\n"
        "/enable_night_mode  - Aktiviere den Nachtmodus\n"
        "/disable_night_mode - Deaktiviere den Nachtmodus\n"
        "/search [title] - Suche nach einem Film oder einer TV-Show\n\n"
        "Um einen Befehl auszuführen, tippe ihn einfach in den Chat ein oder kopiere und füge ihn ein."
    )
    await update.message.reply_text(help_text)

# Start bot function
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()} !"
        "\n\n"
        "Willkommen bei StreamNet TV\n"
        "Ich bin Mr.StreamNet - der Butler des Hauses.\n\n"
        "Ich stehe dir zur Verfügung, um deine Medienanfragen zu verwalten und vieles Mehr.\n"
        'Wenn du Hilfe benötigst, benutze/klicke auf den Befehl  /help .',
        reply_markup=ReplyKeyboardRemove()
    )

def print_logo():
    logo = r"""
 
███╗   ███╗██████╗    ███████╗████████╗██████╗ ███████╗ █████╗ ███╗   ███╗███╗   ██╗███████╗████████╗
████╗ ████║██╔══██╗   ██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔══██╗████╗ ████║████╗  ██║██╔════╝╚══██╔══╝
██╔████╔██║██████╔╝   ███████╗   ██║   ██████╔╝█████╗  ███████║██╔████╔██║██╔██╗ ██║█████╗     ██║   
██║╚██╔╝██║██╔══██╗   ╚════██║   ██║   ██╔══██╗██╔══╝  ██╔══██║██║╚██╔╝██║██║╚██╗██║██╔══╝     ██║   
██║ ╚═╝ ██║██║  ██║██╗███████║   ██║   ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║██║ ╚████║███████╗   ██║   
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   

    """
    print(logo)

# Main Function
async def main() -> None:
    global application

    # Print the logo at startup
    print_logo()
    sys.stdout.flush()  # Ensure the logo output is flushed to the console
    
    try:
        # Load version info and log it
        version_info = load_version_info('version.txt')

        # Log bot information asynchronously to ensure order
        if version_info:
           await log_message_async("=====================================================")
           await log_message_async("")
           await log_message_async(f"Bot Version: {version_info.get('Version', 'Unknown')}")
           await log_message_async(f"Author: {version_info.get('Author', 'Unknown')}")
           await log_message_async("")
           await log_message_async("=====================================================")
           await log_message_async("")
           await log_message_async(f"To support this project, please visit")
           await log_message_async(f"https://github.com/cyb3rgh05t/telegram_bot")
           await log_message_async("")
           await log_message_async("=====================================================")

           # Check and log the paths for config and database
           await check_and_log_paths()

           # Log all configuration entries
           await log_config_entries(config)

           # Log the successful retrieval of the token and timezone
           configure_bot(TOKEN, TIMEZONE="Europe/Berlin")

           # Initialize the group chat ID and language
           init_db()
           GROUP_CHAT_ID = load_group_id()
           if GROUP_CHAT_ID is None:
               await log_message_async("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
               logger.warning("Group Chat ID not set. Please use /set_group_id. <-----")
               await log_message_async("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
           else:
               # Load group chat ID and language from database
               log_group_id()

           application = ApplicationBuilder().token(TOKEN).build()

           # Register the command handlers
           application.add_handler(CommandHandler(START_COMMAND, start))
           application.add_handler(CommandHandler(HELP_COMMAND, help))
           application.add_handler(CommandHandler(WELCOME_COMMAND, welcome_new_members))
           application.add_handler(CommandHandler(SET_GROUP_ID_COMMAND, set_group_id))
           application.add_handler(CommandHandler(TMDB_LANGUAGE_COMMAND, set_language))
           application.add_handler(CommandHandler(NIGHT_MODE_ENABLE_COMMAND, enable_night_mode))
           application.add_handler(CommandHandler(NIGHT_MODE_DISABLE_COMMAND, disable_night_mode))
           application.add_handler(CommandHandler(SEARCH_COMMAND, search_media))

           # Register callback query handlers for buttons
           application.add_handler(CallbackQueryHandler(handle_add_media_callback))

           # Register the message handler for new members
           application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))

           # Start the night mode checker task with max_instances set to 1
           application.job_queue.run_repeating(night_mode_checker, interval=300, first=0)

           # Register the message handler for user confirmation and general messages
           application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

           # Start the Bot
           logger.info("Bot started polling.")
           await application.run_polling()
    except asyncio.CancelledError:
        logger.info("Main function was cancelled.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Shutting down the bot...")

if __name__ == '__main__':
    try:
        log_message("=====================================================")
        logger.info("Starting the bot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        logger.info("Shutting down the bot...")
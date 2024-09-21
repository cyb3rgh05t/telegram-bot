import asyncio
import nest_asyncio
import datetime
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import pytz

# Apply nest_asyncio to handle running loops
nest_asyncio.apply()

# Load bot configuration from config/config.json
with open('config/config.json', 'r') as config_file:
    config = json.load(config_file)
TOKEN = config.get("TOKEN")

# Constants
IMAGE_URL = "https://github.com/cyb3rgh05t/brands-logos/blob/master/StreamNet/tv/streamnet_brands.jpg?raw=true"
BUTTON_URL = "https://t.me/c/1696089108/9291/13417"
STORAGE_FILE = "group_storage.json"
TIMEZONE = pytz.timezone('Europe/Berlin')  # UTC+2 timezone (Berlin is UTC+2 during daylight saving time)

# Load group chat ID from file or initialize
def load_group_id():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            data = json.load(f)
            return data.get("group_chat_id", None)
    return None

# Save group chat ID to file
def save_group_id(group_chat_id):
    with open(STORAGE_FILE, "w") as f:
        json.dump({"group_chat_id": group_chat_id}, f)

# Initialize the group chat ID
GROUP_CHAT_ID = load_group_id()
if GROUP_CHAT_ID is None:
    print("Group chat ID not set. Please set it using /set_group_id.")

# Global variable to track if night mode is active
night_mode_active = False

# Get the current time in the desired timezone
def get_current_time():
    return datetime.datetime.now(TIMEZONE)

# Define a command handler function
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hello! I am your bot. How can I help you?')

# Command to set the group ID
async def set_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global GROUP_CHAT_ID
    GROUP_CHAT_ID = update.message.chat_id
    save_group_id(GROUP_CHAT_ID)
    await update.message.reply_text(f"Group chat ID set to: {GROUP_CHAT_ID}")

# Define a function to welcome new members
async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        button = InlineKeyboardButton("StreamNet TV Store", url=BUTTON_URL)
        keyboard = InlineKeyboardMarkup([[button]])
        
        now = get_current_time()
        date_time = now.strftime("%d.%m.%Y %H:%M:%S")
        username = f"@{member.username}" if member.username else "N/A"
        surname = member.last_name if member.last_name else "N/A"

        welcome_message = (
            "\n"
            f"🎉 Howdy, {member.full_name}!\n\n"
            "Vielen Dank, dass du diesen Service ausgewählt hast ❤️.\n\n"
            f"Username: {username}\n"
            f"Beitritt: {date_time}\n\n"
            "Wir hoffen, du hast eine gute Unterhaltung mit StreamNet TV.\n\n"
            "Bei Fragen oder sonstiges einfach in die verschiedenen Topics reinschreiben. "
            "Je nachdem, um welche Frage es sich handelt, werden wir dir so gut wie möglich helfen."
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
            await update.message.reply_text("❌ Sorry, solange der NACHTMODUS aktiviert ist, kannst du von 00:00 Uhr bis 07:00 Uhr keine Mitteilungen in der Gruppe senden.")
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)

# Background task to check and switch night mode
async def night_mode_checker(context):
    global night_mode_active
    while True:
        now = get_current_time()  # Get the current time in UTC+2
        if now.hour == 0 and not night_mode_active:
            night_mode_active = True
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff braucht auch mal eine Pause.\n\nVon 00:00 Uhr bis 07:00 Uhr kannst du keine Mitteilungen in der Gruppe oder in den Topics senden.")
        elif now.hour == 7 and night_mode_active:
            night_mode_active = False
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="☀️ ENDE DES NACHTMODUS.\n\n✅ Ab jetzt kannst du wieder Mitteilungen in der Gruppe senden.")
        await asyncio.sleep(300)  # Check every 5 minutes

# Command to enable night mode
async def enable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if not night_mode_active:
        night_mode_active = True
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 NACHTMODUS AKTIVIERT.\n\nStreamNet TV Staff braucht auch mal eine Pause.\n\nVon 00:00 Uhr bis 07:00 Uhr kannst du keine Mitteilungen in der Gruppe oder in den Topics senden.")

# Command to disable night mode
async def disable_night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global night_mode_active
    if night_mode_active:
        night_mode_active = False
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
    application.job_queue.run_repeating(night_mode_checker, interval=60, first=0)

    # Start the Bot
    await application.run_polling()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped gracefully.")

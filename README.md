# StreamNet TV Bot

This is a Telegram bot built using `python-telegram-bot` to interact with Sonarr and Radarr for managing TV shows and movies. The bot allows users to search for media, check if it's already in Sonarr/Radarr, and add new series or movies as needed. It also features a "night mode" to restrict non-admin users from sending messages during specific hours.

## Features

- **Media Search**: Search for TV shows and movies via the TMDB API.
- **Sonarr/Radarr Integration**: Add movies or TV series directly to Sonarr or Radarr with a quality profile and root folder path.
- **Night Mode**: Automatically restricts non-admin messages in the group during night hours (00:00 - 07:00) or can be enabled/disabled manually.
- **User Interaction**: Welcomes new members and handles media confirmation requests.
- **Language Support**: Supports different languages for TMDB searches.
- **Group Settings**: Saves group chat ID and language preferences in an SQLite database.

## Table of Contents

- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Commands](#commands)
- [Dependencies](#dependencies)
- [Running the Bot](#running-the-bot)
- [Contributing](#contributing)
- [License](#license)

## Getting Started

### Prerequisites

Before running the bot, ensure that you have the following:
- Python 3.8+
- Telegram bot token from [BotFather](https://core.telegram.org/bots#botfather)
- Sonarr and Radarr APIs set up
- TMDB API key from [The Movie Database](https://www.themoviedb.org/)

### Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/your-username/streamnet-tv-bot.git
    cd streamnet-tv-bot
    ```

2. Install the required dependencies:

    ```bash
    pip install -r requirements.txt
    ```

3. Create a `config.json` file in the `config/` directory:

    ```json
    {
      "bot": {
        "TOKEN": "<your-telegram-bot-token>",
        "TIMEZONE": "Europe/Berlin",
        "LOG_LEVEL": "INFO"
      },
      "welcome": {
        "IMAGE_URL": "<welcome-image-url>",
        "BUTTON_URL": "<button-url>"
      },
      "tmdb": {
        "API_KEY": "<your-tmdb-api-key>",
        "DEFAULT_LANGUAGE": "en"
      },
      "sonarr": {
        "URL": "<your-sonarr-url>",
        "API_KEY": "<your-sonarr-api-key>",
        "QUALITY_PROFILE_NAME": "<sonarr-quality-profile-name>",
        "ROOT_FOLDER_PATH": "<sonarr-root-folder-path>"
      },
      "radarr": {
        "URL": "<your-radarr-url>",
        "API_KEY": "<your-radarr-api-key>",
        "QUALITY_PROFILE_NAME": "<radarr-quality-profile-name>",
        "ROOT_FOLDER_PATH": "<radarr-root-folder-path>"
      }
    }
    ```

4. Initialize the SQLite database (automatically done on first run):

    ```bash
    python bot.py
    ```

## Configuration

The bot requires a `config.json` file in the `config/` directory. This file contains the API tokens, URLs, and preferences for the bot.

Example configuration:

```json
{
  "bot": {
    "TOKEN": "<your-telegram-bot-token>",
    "TIMEZONE": "Europe/Berlin",
    "LOG_LEVEL": "INFO"
  },
  "welcome": {
    "IMAGE_URL": "<welcome-image-url>",
    "BUTTON_URL": "<button-url>"
  },
  "tmdb": {
    "API_KEY": "<your-tmdb-api-key>",
    "DEFAULT_LANGUAGE": "en"
  },
  "sonarr": {
    "URL": "<your-sonarr-url>",
    "API_KEY": "<your-sonarr-api-key>",
    "QUALITY_PROFILE_NAME": "<sonarr-quality-profile-name>",
    "ROOT_FOLDER_PATH": "<sonarr-root-folder-path>"
  },
  "radarr": {
    "URL": "<your-radarr-url>",
    "API_KEY": "<your-radarr-api-key>",
    "QUALITY_PROFILE_NAME": "<radarr-quality-profile-name>",
    "ROOT_FOLDER_PATH": "<radarr-root-folder-path>"
  }
}
```

## Commands

The following commands are available:

- **`/start`**: Initializes the bot and welcomes the user.
- **`/search <title>`**: Searches for a movie or TV show using the TMDB API.
- **`/set_group_id`**: Sets the group chat ID.
- **`/set_language <code>`**: Sets the preferred language for TMDB searches.
- **`/enable_night_mode`**: Enables night mode (00:00 - 07:00).
- **`/disable_night_mode`**: Disables night mode.

### Media Management Commands

- **Search**: Use `/search <title>` to find a TV show or movie.
- **Add Series**: Once a TV series is found, users can add it to Sonarr by confirming with `yes`.
- **Add Movie**: Once a movie is found, users can add it to Radarr by confirming with `yes`.

## Dependencies

- **`python-telegram-bot`**: For handling Telegram API.
- **`requests`**: For making API requests to Sonarr, Radarr, and TMDB.
- **`nest_asyncio`**: To handle event loops.
- **`pytz`**: For handling timezone conversions.
- **`SQLite3`**: For storing group ID and language settings.

Install dependencies via:

```bash
pip install -r requirements.txt
```
## Running the Bot

To run the bot:

```bash
python bot.py
```
The bot will start polling and waiting for commands on Telegram.

## Contributing

If you wish to contribute to the project, feel free to fork the repository, make your changes, and submit a pull request. Contributions, issues, and feature requests are welcome!

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/new-feature`).
3. Commit your changes (`git commit -am 'Add new feature'`).
4. Push to the branch (`git push origin feature/new-feature`).
5. Open a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

        
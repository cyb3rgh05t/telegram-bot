# <p align="center">Mr.StreamNet</p>
  
A multifunctional and fully customisable Telegram Bot.


## 🧐 Key Features:  

1. **Database Handling** 

    - Stores group chat ID and language preference.

1. **Tmdb Integration**

    - Fetches movie/show details and artwork based on user queries.

2. **Language Support**

    - Allows changing language for TMDb responses.

3. **Night Mode**

   - Restricts messages during specified hours with admin exceptions.

4. **Welcome User Message** 

   - Sends a welcome message when a user joins the group/channel.


## 🧑🏻‍💻 Commands

| Commands | Usage | Description |
| -------- | -------- | -------- |
| Set Group ID   | `/set_group_id`    | Sets the Telegram Group ID    |
| Set Language    | `/set_language`    | Sets language (e.g.` /set_language de`)   |
| Search Movies/Shows    | `/search_movie` or  `/search_tv_show`    | Search for movie or show `/search_movie <movie_name>` or `/search_tv_show <show_name>`    |
|    |    |    |
|     |     |   |
        


## 🧑🏻‍💻 Config
```json
{
    "TOKEN": "7482615128:AAGJXub995gswG4GfQW4567fGHJLKGFDD23457",
    "TIMEZONE": "Europe/Berlin",
    "IMAGE_URL": "",
    "BUTTON_URL": "",
    "LOG_LEVEL": "INFO",
    "TMDB_API_KEY": "e7d2628727fa893e3853958fjefjjkk56",
    "DEFAULT_LANGUAGE": "de"
}
```

### Explanation of Fields

`TOKEN` - Your Telegram bot token.

`TMDB_API_KEY` - Your TMDb API key to fetch movie/show data.

`TIMEZONE` - The timezone your bot should use (e.g., "Europe/Berlin").

`DEFAULT_LANGUAGE` - The default language for TMDb responses (e.g., "en" for English, "de" for German).

`IMAGE_URL` - A default image URL to use in welcome messages.

`BUTTON_URL`  - A URL for a button in welcome messages (e.g., a store link).

`LOG_LEVEL` - The logging level (e.g., "INFO", "DEBUG").


        
# Use the official Python image as a base image
FROM python:3.12-slim

# Owner 
LABEL maintainer=cyb3rgh05t
LABEL org.opencontainers.image.source https://github.com/cyb3rgh05t/telegram-bot

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port for the Django panel 
EXPOSE 5555

# Command to run both the bot and the Django server
CMD ["sh", "-c", "python bot.py & python panel/manage.py runserver 0.0.0.0:5555"]

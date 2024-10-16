from django.shortcuts import render, get_object_or_404, redirect
from .models import Post
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from pathlib import Path
import json
import requests
import os
import sqlite3
import logging

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Use a relative path for the config.json file
CONFIG_DIR = os.path.join(BASE_DIR.parent, "config")

DATABASE_DIR = os.path.join(BASE_DIR.parent, "database")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DATABASE_FILE = os.path.join(DATABASE_DIR, "group_data.db")

# Get an instance of the logger
logger = logging.getLogger(__name__)


# Load group chat ID from the database
def load_group_chat_id():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT group_chat_id FROM group_data WHERE id=1")
        row = cursor.fetchone()
    if row:
        return row[0]  # Return only the group_chat_id
    return None  # Return None if not found


group_chat_id = load_group_chat_id()

# Load configuration from config.json
with open(CONFIG_FILE, "r") as config_file:
    config = json.load(config_file)

# BOT
TOKEN = config.get("bot").get("TOKEN")
# TOPICS
TOPICS = config.get("topics", {})


def index(request):
    posts = Post.objects.all()
    return render(request, "index.html", {"posts": posts})


@csrf_protect  # Keep CSRF protection enabled
def api_posts(request):
    if request.method == "GET":
        posts = Post.objects.all()
        data = [{"id": post.id, "content": post.content} for post in posts]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        data = json.loads(request.body)
        post_id = data["id"]
        new_content = data["content"]
        post = get_object_or_404(Post, id=post_id)
        post.content = new_content
        post.save()
        return JsonResponse({"status": "success"})


def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if request.method == "POST":
        original_content = post.content  # Save the original content
        post.content = request.POST["content"]

        # Check if a new image is uploaded; if not, keep the existing one
        if request.FILES.get("image"):
            post.image = request.FILES["image"]
        else:
            # Retain the existing image (no change)
            post.image = post.image

        # Update pinned status based on the checkbox
        post.pinned = request.POST.get("pinned") == "True"  # Update pinned status

        # Update topic_id based on the selection
        post.topic_id = request.POST.get(
            "topic"
        )  # Update topic_id based on the form input

        # Save the updated post
        post.save()

        # Prepare the message to send to Telegram
        update_message = (
            f"📝 Post Aktualisiert!\n\n"
            f"Originaler Post: {original_content}\n\n"
            f"Neuer Post: {post.content}"
        )

        # Debugging: logger.info available threads
        logger.info("Available THREADS in TOPICS:", TOPICS)  # Debugging
        logger.info("Post Topic ID:", post.topic_id)  # Debugging

        # Retrieve the thread information by matching the topic_id
        thread_info = next(
            (info for key, info in TOPICS.items() if key == post.topic_id), None
        )
        if thread_info:
            chat_id = thread_info["chat_id"]
            message_thread_id = thread_info["message_thread_id"]

            # Prepare the correct image path
            image_path = (
                post.image.path if post.image else None
            )  # Use the full path of the existing image

            # Send the update to Telegram as a reply
            send_to_telegram(
                update_message,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                pinned=post.pinned,
                image_path=image_path,
            )
        else:
            logger.info("Thread information not found in TOPICS based on topic_id.")

        messages.success(request, "Post updated and sent to Telegram!")
        return redirect("index")

    # Pass the image URL to the template
    image_url = (
        post.image.url if post.image else None
    )  # Retrieve the URL for the existing image
    return render(
        request, "edit.html", {"post": post, "topics": TOPICS, "image_url": image_url}
    )


def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    post.delete()  # Delete the post from the database
    messages.success(request, "Post deleted successfully!")
    return redirect(
        "index"
    )  # Redirect back to the post listing or wherever appropriate


def create_post(request):
    if request.method == "POST":
        content = request.POST["content"]
        image = request.FILES.get("image")  # Get the uploaded image
        selected_thread = request.POST.get("thread")  # Retrieve the selected thread

        # Check if the pinned checkbox is present and set the pinned status accordingly
        pinned = (
            request.POST.get("pinned") == "True"
        )  # Check for 'True' to confirm pin status

        # Debugging statement
        logger.info("Create Post - Content:", content)
        logger.info("Create Post - Image:", image)
        logger.info(
            "Create Post - Pinned Status:", pinned
        )  # Debugging the pinned status
        logger.info("Create Post - Selected Thread:", selected_thread)

        # Get the thread information from the configuration
        thread_info = TOPICS.get(selected_thread)

        if thread_info:
            chat_id = thread_info["chat_id"]
            message_thread_id = thread_info.get(
                "message_thread_id", None
            )  # Get message_thread_id if available

            # Create a new post, saving the topic_id (chat_id)
            post = Post(content=content, image=image, pinned=pinned, topic_id=chat_id)
            post.save()

            # Prepare the image path if there is an image
            image_path = f"{settings.MEDIA_ROOT}/images/{image.name}" if image else None

            # Send to Telegram, using the selected topic's `message_thread_id`
            send_to_telegram(
                content, image_path, chat_id, message_thread_id, pinned=pinned
            )  # Pass the pinned status and the image path

            messages.success(request, "Post created and sent to Telegram!")
            return redirect("index")
        else:
            messages.error(request, "Invalid thread selected!")
            return redirect("create_post")

    return render(
        request, "create_post.html", {"threads": TOPICS}
    )  # Pass threads to the template


TELEGRAM_BOT_TOKEN = TOKEN
CHAT_ID = load_group_chat_id()


def send_to_telegram(
    content, image_path=None, chat_id=None, message_thread_id=None, pinned=False
):
    if image_path:
        # Send the photo with caption
        with open(image_path, "rb") as photo:
            url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            data_photo = {
                "chat_id": chat_id,  # Use the retrieved chat_id
                "caption": content,
                "parse_mode": "Markdown",
                "message_thread_id": message_thread_id,  # Include message_thread_id
            }
            response_photo = requests.post(
                url_photo, files={"photo": photo}, data=data_photo
            )
            result_photo = response_photo.json()

            if response_photo.status_code == 200:
                message_id = result_photo["result"]["message_id"]
                logger.info("Photo sent successfully, message ID:", message_id)

                # Pin the message only if pinned is True
                if pinned:
                    url_pin = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage"
                    data_pin = {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "disable_notification": False,
                    }
                    pin_response = requests.post(url_pin, data=data_pin)
                    pin_result = pin_response.json()

                    # Debugging output for pinning response
                    logger.info(
                        f"Attempting to pin message ID {message_id} in chat {chat_id}."
                    )
                    logger.info("Pin Data:", data_pin)
                    logger.info(
                        "Pin Response:", pin_result
                    )  # Log the pinning response  # Log the pinning response

                    if pin_response.status_code != 200:
                        logger.info(
                            f"Error pinning message (status code {pin_response.status_code}):",
                            pin_result,
                        )
                    else:
                        logger.info("Message pinned successfully.")
            else:
                logger.info("Error sending photo:", result_photo)

    else:
        # Send the message
        url_send = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data_send = {
            "chat_id": chat_id,  # Use the retrieved chat_id
            "text": content,
            "parse_mode": "Markdown",
            "message_thread_id": message_thread_id,  # Include message_thread_id
        }
        response_send = requests.post(url_send, data=data_send)
        result_send = response_send.json()

        if response_send.status_code == 200:
            message_id = result_send["result"]["message_id"]
            logger.info("Message sent successfully, message ID:", message_id)

            # Pin the message only if pinned is True
            if pinned:
                url_pin = (
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage"
                )
                data_pin = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "disable_notification": False,
                }
                pin_response = requests.post(url_pin, data=data_pin)
                pin_result = pin_response.json()

                # Debugging output for pinning response
                logger.info("Pin Response:", pin_result)  # Log the pinning response

                if pin_response.status_code != 200:
                    logger.info(
                        f"Error pinning message (status code {pin_response.status_code}):",
                        pin_result,
                    )
                else:
                    logger.info("Message pinned successfully.")
        else:
            logger.info(
                "Error sending message:", result_send
            )  # Print error if sending message failed

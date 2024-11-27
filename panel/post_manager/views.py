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

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Use a relative path for the config.json file
CONFIG_DIR = os.path.join(BASE_DIR.parent, "config")

DATABASE_DIR = os.path.join(BASE_DIR.parent, "database")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DATABASE_FILE = os.path.join(DATABASE_DIR, "group_data.db")


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

        # Check if a new file (image/video) is uploaded; if not, keep the existing one
        if request.FILES.get("file"):
            post.file = request.FILES["file"]
        else:
            post.file = post.file

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

        # Retrieve the thread information by matching the topic_id
        thread_info = next(
            (info for key, info in TOPICS.items() if key == post.topic_id), None
        )
        if thread_info:
            chat_id = thread_info["chat_id"]
            message_thread_id = thread_info["message_thread_id"]

            # Prepare the correct file path
            file_path = (
                post.file.path if post.file else None
            )  # Use the full path of the existing file

            # Send the update to Telegram as a reply
            send_to_telegram(
                update_message,
                file_path=file_path,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                pinned=post.pinned,
            )
        else:
            print("Thread information not found in TOPICS based on topic_id.")

        messages.success(request, "Post updated and sent to Telegram!")
        return redirect("index")

    # Pass the file URL to the template
    file_url = (
        post.file.url if post.file else None
    )  # Retrieve the URL for the existing file (image/video)
    return render(
        request, "edit.html", {"post": post, "topics": TOPICS, "file_url": file_url}
    )


def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    post.delete()  # Delete the post from the database
    messages.success(request, "Post deleted successfully!")
    return redirect("index")


def create_post(request):
    if request.method == 'POST':
        content = request.POST.get('content')
        file = request.FILES.get('file')  # Handle file upload
        selected_thread = request.POST.get('thread')
        pinned = request.POST.get('pinned') == 'True'  # Handle pinned checkbox

        # Get the topic info
        thread_info = TOPICS.get(selected_thread)

        if thread_info:
            chat_id = thread_info['chat_id']
            message_thread_id = thread_info.get('message_thread_id', None)

            # Create a new post object (without file saved yet)
            post = Post(content=content, pinned=pinned, topic_id=chat_id)

            if file:
                post.file = file  # Save the uploaded file (image or video)
            
            post.save()  # Save the post to the database (this will also save the file)

            # After the post is saved, you can access the path of the file
            file_path = post.file.path if post.file else None  # Access the file path from the saved post object

            # Now you can send the content and file to Telegram as needed
            send_to_telegram(content, file_path=file_path, chat_id=chat_id, message_thread_id=message_thread_id, pinned=pinned)

            messages.success(request, "Post created and sent to Telegram!")
            return redirect('index')
        else:
            messages.error(request, "Invalid thread selected!")
            return redirect('create_post')

    return render(request, 'create_post.html', {'threads': TOPICS})



# Telegram Bot Token and Chat ID
TELEGRAM_BOT_TOKEN = TOKEN
CHAT_ID = load_group_chat_id()


def send_to_telegram(
    content, file_path=None, chat_id=None, message_thread_id=None, pinned=False
):
    if file_path:
        file_extension = file_path.split('.')[-1].lower()

        if file_extension in ['mp4', 'mov', 'avi']:  # Check if it's a video file
            url_send = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
            files = {"video": open(file_path, "rb")}
            data = {
                "chat_id": chat_id,
                "caption": content,
                "parse_mode": "Markdown",
                "message_thread_id": message_thread_id,
            }
        else:
            url_send = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {"photo": open(file_path, "rb")}
            data = {
                "chat_id": chat_id,
                "caption": content,
                "parse_mode": "Markdown",
                "message_thread_id": message_thread_id,
            }

        response = requests.post(url_send, files=files, data=data)
        result = response.json()

        if response.status_code == 200:
            message_id = result["result"]["message_id"]
            print(f"File sent successfully, message ID: {message_id}")

            if pinned:
                url_pin = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage"
                data_pin = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "disable_notification": False,
                }
                pin_response = requests.post(url_pin, data=data_pin)
                print("Pin Response:", pin_response.json())
        else:
            print("Error sending file:", result)
    else:
        # Send the text message if no file is provided
        url_send = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data_send = {
            "chat_id": chat_id,
            "text": content,
            "parse_mode": "Markdown",
            "message_thread_id": message_thread_id,
        }
        response_send = requests.post(url_send, data=data_send)
        result_send = response_send.json()

        if response_send.status_code == 200:
            message_id = result_send["result"]["message_id"]
            print("Message sent successfully, message ID:", message_id)

            if pinned:
                url_pin = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage"
                data_pin = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "disable_notification": False,
                }
                pin_response = requests.post(url_pin, data=data_pin)
                print("Pin Response:", pin_response.json())

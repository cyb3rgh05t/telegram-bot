from django.shortcuts import render, get_object_or_404, redirect
from .models import Post
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
import json
import requests
import os
import sqlite3

CONFIG_DIR = '/app/config'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

# Path for SQLite database file in the backup folder
DATABASE_DIR = '/app/database'
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
with open(CONFIG_FILE, 'r') as config_file:
    config = json.load(config_file)

# BOT
TOKEN = config.get("bot").get("TOKEN")

def index(request):
    posts = Post.objects.all()
    return render(request, 'index.html', {'posts': posts})

@csrf_protect  # Keep CSRF protection enabled
def api_posts(request):
    if request.method == 'GET':
        posts = Post.objects.all()
        data = [{"id": post.id, "content": post.content} for post in posts]
        return JsonResponse(data, safe=False)

    elif request.method == 'POST':
        data = json.loads(request.body)
        post_id = data['id']
        new_content = data['content']
        post = get_object_or_404(Post, id=post_id)
        post.content = new_content
        post.save()
        return JsonResponse({"status": "success"})
    
def edit_post(request, post_id):
    # Retrieve the post to edit
    post = get_object_or_404(Post, id=post_id)

    if request.method == 'POST':
        # Handle the POST request to update the post
        new_content = request.POST.get('content')  # Get the updated content from the form
        post.content = new_content
        post.save()

        # Return a success response if it's an AJAX request
        if request.is_ajax():
            return JsonResponse({"status": "success"})

        # Redirect to the index or another page if it’s a normal POST request
        return redirect('index')

    # If it's a GET request, render the edit form
    return render(request, 'edit.html', {'post': post})

def create_post(request):
    if request.method == 'POST':
        content = request.POST['content']
        image = request.FILES.get('image')  # Get the uploaded image
        post = Post(content=content, image=image)
        post.save()

        # Prepare the image path
        image_path = f"{settings.MEDIA_ROOT}/images/{image.name}" if image else None
        
        # Send to Telegram
        send_to_telegram(content, image_path)

        messages.success(request, 'Post created and sent to Telegram!')
        return redirect('index')

    return render(request, 'create_post.html')

TELEGRAM_BOT_TOKEN = TOKEN
CHAT_ID = load_group_chat_id()

def send_to_telegram(content, image_path=None):
    if image_path:
        # Step 1: Send the photo with caption
        with open(image_path, 'rb') as photo:
            url_photo = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'
            data_photo = {
                'chat_id': CHAT_ID,
                'caption': content,  # Use content as the caption
                'parse_mode': 'Markdown'
            }
            response_photo = requests.post(url_photo, files={'photo': photo}, data=data_photo)
            result_photo = response_photo.json()

            # Check if the photo was sent successfully
            if response_photo.status_code == 200:
                message_id = result_photo['result']['message_id']  # Get the sent message ID
                
                # Step 2: Pin the message
                url_pin = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage'
                data_pin = {
                    'chat_id': CHAT_ID,
                    'message_id': message_id,
                    'disable_notification': False  # Optional
                }
                requests.post(url_pin, data=data_pin)

    else:
        # Step 1: Send the message
        url_send = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        data_send = {
            'chat_id': CHAT_ID,
            'text': content,
            'parse_mode': 'Markdown',
            'disable_notification': False  # Optional
        }

        response_send = requests.post(url_send, data=data_send)
        result_send = response_send.json()

        # Check if the message was sent successfully
        if response_send.status_code == 200:
            message_id = result_send['result']['message_id']  # Get the sent message ID
            
            # Step 2: Pin the message
            url_pin = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage'
            data_pin = {
                'chat_id': CHAT_ID,
                'message_id': message_id,
                'disable_notification': False  # Optional
            }

            requests.post(url_pin, data=data_pin)


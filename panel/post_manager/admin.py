from django.contrib import admin
from django import forms
from .models import Post
from .views import send_to_telegram  # Import your send_to_telegram function
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Use a relative path for the config.json file
CONFIG_DIR = os.path.join(BASE_DIR.parent, "config")

DATABASE_DIR = os.path.join(BASE_DIR.parent, "database")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DATABASE_FILE = os.path.join(DATABASE_DIR, "group_data.db")

with open(CONFIG_FILE) as config_file:
    config = json.load(config_file)

# Get the topics as a dictionary from config.json
TOPICS = config["topics"]
TOPIC_CHOICES = [(k, k) for k in TOPICS.keys()]  # Use topic names for choices


# Admin action to mark posts as pinned
@admin.action(description="Mark selected posts as pinned")
def make_pinned(modeladmin, request, queryset):
    queryset.update(pinned=True)


# Admin action to mark posts as unpinned
@admin.action(description="Mark selected posts as unpinned")
def make_unpinned(modeladmin, request, queryset):
    queryset.update(pinned=False)


# Admin action to send posts to Telegram
@admin.action(description="Send selected posts to Telegram")
def send_posts_to_telegram(modeladmin, request, queryset):
    for post in queryset:
        # Retrieve the topic name based on topic_id (chat_id)
        topic_name = None
        for name, topic_info in TOPICS.items():
            if topic_info["chat_id"] == post.topic_id:
                topic_name = name
                break

        if topic_name:
            topic_info = TOPICS.get(topic_name)
            chat_id = topic_info["chat_id"]
            message_thread_id = topic_info.get("message_thread_id")

            # Send the post to Telegram
            send_to_telegram(
                content=post.content,
                chat_id=chat_id,
                pinned=post.pinned,
                image_path=post.image.path if post.image else post.file.path if post.file else None,
                message_thread_id=message_thread_id,
            )

    modeladmin.message_user(request, "Selected posts were sent to Telegram successfully!")


# Register Post model in the Django admin interface
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("content", "get_topic_name", "pinned")  # Display content, topic name, and pinned status
    search_fields = ("content", "topic_id")
    list_filter = ("pinned", "topic_id")
    actions = [make_pinned, make_unpinned, send_posts_to_telegram]  # Add actions for pinning/unpinning and sending to Telegram
    fields = ("content", "image", "file", "topic_id", "pinned")  # Include fields for images and videos

    # Customize the form for selecting topics
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "topic_id":
            kwargs["widget"] = forms.Select(choices=TOPIC_CHOICES)  # Use a dropdown for selecting topics
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    # Display the human-readable topic name in the admin list
    def get_topic_name(self, obj):
        for topic_name, topic_info in TOPICS.items():
            if topic_info["chat_id"] == obj.topic_id:
                return topic_name
        return obj.topic_id  # Fallback to chat_id if no match is found

    get_topic_name.short_description = "Topic"

    # Ensure the post is saved before sending to Telegram
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # Retrieve the correct topic (chat_id and message_thread_id) from the config
        topic_name = self.get_topic_name(obj)  # Get the topic name from the object
        topic_info = TOPICS.get(topic_name)  # Retrieve the topic info from TOPICS

        if topic_info:
            chat_id = topic_info["chat_id"]
            message_thread_id = topic_info.get("message_thread_id")

            # Send the post to Telegram with the correct file (image or video)
            send_to_telegram(
                content=obj.content,
                chat_id=chat_id,
                pinned=obj.pinned,
                image_path=obj.image.path if obj.image else obj.file.path if obj.file else None,
                message_thread_id=message_thread_id,
            )

        self.message_user(request, "Post sent to Telegram successfully!")

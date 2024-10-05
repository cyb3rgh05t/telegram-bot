from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('edit/<int:post_id>/', views.edit_post, name='edit_post'),
    path('create_post/', views.create_post, name='create_post'),  # Add this line
    path('api/posts/', views.api_posts, name='api_posts'),  # Add this line
]

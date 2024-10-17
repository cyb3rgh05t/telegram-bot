from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", admin.site.urls),
    path("postmanager/", include("post_manager.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# Serve media files when DEBUG is True
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

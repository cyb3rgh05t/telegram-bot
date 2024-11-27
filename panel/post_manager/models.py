from django.db import models

class Post(models.Model):
    content = models.TextField()
    image = models.ImageField(upload_to='images/', null=True, blank=True)
    file = models.FileField(upload_to='files/', null=True, blank=True)  # Field for video files
    pinned = models.BooleanField(default=False)
    topic_id = models.CharField(max_length=255)

    def __str__(self):
        return self.content
